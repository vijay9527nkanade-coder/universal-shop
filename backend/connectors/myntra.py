"""
connectors/myntra.py
====================
Playwright-powered connector for Myntra search results (myntra.com).
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Optional

from playwright.sync_api import (
    Browser,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from connectors.base import BaseConnector, ConnectorError, SearchResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_URL = "https://www.myntra.com/"
_PAGE_LOAD_TIMEOUT = 30_000   # ms
_SELECTOR_TIMEOUT = 15_000    # ms
_MAX_RESULTS = 20

# Stable container selector for Myntra items
_CONTAINER = 'li.product-base'

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Helper parsers
# ---------------------------------------------------------------------------

def _parse_price(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    # e.g., "Rs. 1299"
    cleaned = re.sub(r"[^\d.]", "", raw.replace(",", ""))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None

def _parse_rating(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", raw)
    try:
        return float(match.group(1)) if match else None
    except ValueError:
        return None

def _parse_review_count(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    raw = raw.strip().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)([KkMm]?)", raw)
    if not match:
        return None
    try:
        num = float(match.group(1))
        suffix = match.group(2).upper()
        if suffix == "K":
            num *= 1_000
        elif suffix == "M":
            num *= 1_000_000
        return int(num)
    except ValueError:
        return None

def _absolute_url(href: Optional[str], base: str = "https://www.myntra.com") -> Optional[str]:
    if not href:
        return None
    if href.startswith("http"):
        return href
    return urllib.parse.urljoin(base, href)

# ---------------------------------------------------------------------------
# Per-card extraction
# ---------------------------------------------------------------------------

def _extract_card(card, base_url: str = "https://www.myntra.com") -> Optional[SearchResult]:
    """Extract a SearchResult from a single Playwright Locator card."""
    
    # Product URL
    product_url = None
    try:
        link_el = card.locator('a').first
        href = link_el.get_attribute("href", timeout=1_000)
        if href:
            product_url = _absolute_url(href, base_url)
    except Exception:
        pass

    # Name - Try to combine brand and product name
    name = ""
    try:
        brand = card.locator('.product-brand').first.inner_text(timeout=1_000).strip()
        product = card.locator('.product-product').first.inner_text(timeout=1_000).strip()
        if brand and product:
            name = f"{brand} - {product}"
        else:
            name = brand or product
    except Exception:
        pass

    # Fallback name extraction from image alt text if missing
    if not name:
        try:
            img_el = card.locator('img').first
            alt_text = img_el.get_attribute("alt", timeout=1_000)
            if alt_text:
                name = alt_text.strip()
        except Exception:
            pass

    if not name or not product_url:
        return None

    # Price
    price_raw = None
    try:
        # Myntra usually shows discounted price and original price. Prefer discounted price.
        price_el = card.locator('.product-discountedPrice').first
        price_raw = price_el.inner_text(timeout=1_000)
    except Exception:
        pass

    if not price_raw:
        try:
            price_el = card.locator('.product-price').first
            price_raw = price_el.inner_text(timeout=1_000)
        except Exception:
            pass

    price = _parse_price(price_raw)

    # Rating & Reviews
    rating_raw = None
    review_raw = None
    try:
        # Myntra rating container
        rating_container = card.locator('.product-ratingsContainer').first
        rating_text = rating_container.inner_text(timeout=1_000)
        
        # E.g., "4.3 | 1.2k"
        if "|" in rating_text:
            parts = rating_text.split("|")
            rating_raw = parts[0].strip()
            review_raw = parts[1].strip()
        else:
            rating_match = re.search(r"(\d\.\d)", rating_text)
            if rating_match:
                rating_raw = rating_match.group(1)
            
            review_match = re.search(r"([\d.,]+[kKmM]?)", rating_text.replace(rating_raw or "", ""))
            if review_match:
                review_raw = review_match.group(1)
    except Exception:
        pass

    rating = _parse_rating(rating_raw)
    review_count = _parse_review_count(review_raw)

    # Image URL
    image_url = None
    try:
        img_el = card.locator("img").first
        image_url = img_el.get_attribute("src", timeout=1_000)
    except Exception:
        pass

    return SearchResult(
        name=name,
        price=price,
        rating=rating,
        review_count=review_count,
        image_url=image_url,
        product_url=product_url,
        platform="myntra",
    )

# ---------------------------------------------------------------------------
# Browser initialisation helpers
# ---------------------------------------------------------------------------

def _new_browser(pw: Playwright) -> Browser:
    return pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
    )

def _new_page(browser: Browser) -> Page:
    context = browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        java_script_enabled=True,
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return context.new_page()

# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class MyntraConnector(BaseConnector):
    """Playwright-powered connector for Myntra (myntra.com)."""

    platform = "myntra"

    BASE_URL: str = _BASE_URL
    PAGE_LOAD_TIMEOUT: int = _PAGE_LOAD_TIMEOUT
    SELECTOR_TIMEOUT: int = _SELECTOR_TIMEOUT
    MAX_RESULTS: int = _MAX_RESULTS

    def search(self, query: str) -> list[SearchResult]:
        if not query or not query.strip():
            logger.warning("[myntra] Empty query — returning []")
            return []

        # Myntra search urls typically use hyphens for spaces
        formatted_query = query.strip().replace(" ", "-")
        url = f"{self.BASE_URL}{urllib.parse.quote(formatted_query)}"
        logger.info("[myntra] Scraping: %s", url)

        try:
            return self._run_scrape(url)
        except Exception:
            logger.exception("[myntra] Unhandled exception while scraping %r — returning []", url)
            return []

    def _run_scrape(self, url: str) -> list[SearchResult]:
        results: list[SearchResult] = []

        with sync_playwright() as pw:
            browser = _new_browser(pw)
            try:
                page = _new_page(browser)
                self._navigate(page, url)
                results = self._extract_results(page)
            except PlaywrightTimeoutError:
                logger.warning("[myntra] Timed out waiting for results on %s — returning []", url)
            except Exception:
                logger.exception("[myntra] Scrape failed for %s", url)
            finally:
                browser.close()

        logger.info("[myntra] Returning %d result(s) for URL %s", len(results), url)
        return results

    def _navigate(self, page: Page, url: str) -> None:
        page.goto(url, timeout=self.PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
        page.wait_for_selector(_CONTAINER, timeout=self.SELECTOR_TIMEOUT)

    def _extract_results(self, page: Page) -> list[SearchResult]:
        cards = page.locator(_CONTAINER)
        total = cards.count()
        logger.debug("[myntra] Found %d product cards", total)

        results: list[SearchResult] = []
        for i in range(min(total, self.MAX_RESULTS)):
            card = cards.nth(i)
            try:
                result = _extract_card(card)
                if result is not None:
                    results.append(result)
            except Exception:
                logger.exception("[myntra] Failed to extract card %d — skipping", i)

        return results
