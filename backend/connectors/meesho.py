"""
connectors/meesho.py
====================
Playwright-powered connector for Meesho search results (meesho.com).
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

_BASE_URL = "https://www.meesho.com/search"
_PAGE_LOAD_TIMEOUT = 30_000   # ms
_SELECTOR_TIMEOUT = 15_000    # ms
_MAX_RESULTS = 20

# Stable container selector for Meesho items
# Meesho typically wraps the entire product card in an anchor tag pointing to /p/ or /s/p/
_CONTAINER = 'a[href*="/p/"]'

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
    # e.g., "₹ 1,299"
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

def _absolute_url(href: Optional[str], base: str = "https://www.meesho.com") -> Optional[str]:
    if not href:
        return None
    if href.startswith("http"):
        return href
    return urllib.parse.urljoin(base, href)

# ---------------------------------------------------------------------------
# Per-card extraction
# ---------------------------------------------------------------------------

def _extract_card(card, base_url: str = "https://www.meesho.com") -> Optional[SearchResult]:
    """Extract a SearchResult from a single Playwright Locator card."""
    
    # Product URL - Since the container is likely the anchor tag itself
    product_url = None
    try:
        href = card.get_attribute("href", timeout=1_000)
        if href:
            product_url = _absolute_url(href, base_url)
    except Exception:
        pass

    # Name - Try to find the product name (usually a text block or alt text)
    name = ""
    try:
        # Alt text of the image often contains the product name on Meesho
        img_el = card.locator('img[alt]').first
        alt_text = img_el.get_attribute("alt", timeout=1_000)
        if alt_text:
            name = alt_text.strip()
    except Exception:
        pass

    if not name:
        try:
            # Fallback: find the first paragraph tag that has some text
            paragraphs = card.locator('p')
            count = paragraphs.count()
            for idx in range(count):
                text = paragraphs.nth(idx).inner_text(timeout=500).strip()
                # Meesho names are usually the first non-empty paragraph without a rupee symbol
                if text and "₹" not in text:
                    name = text
                    break
        except Exception:
            pass

    if not name or not product_url:
        return None

    # Price
    price_raw = None
    try:
        # Meesho often has headers or paragraphs containing the ₹ symbol for price
        price_el = card.locator(':has-text("₹")').last
        text = price_el.inner_text(timeout=1_000)
        # Find the last occurrence of ₹ and digits
        match = re.search(r"₹\s*([\d,]+)", text)
        if match:
            price_raw = match.group(0)
    except Exception:
        pass

    price = _parse_price(price_raw)

    # Rating & Reviews
    rating_raw = None
    review_raw = None
    try:
        # Rating is usually inside a block with a star icon
        # Looking for numbers like "4.3" and "1234 Reviews"
        all_text = card.inner_text(timeout=1_000)
        
        # Regex for Rating: typically single decimal like 4.1 or 4.5
        rating_match = re.search(r"(\d\.\d)\s*★", all_text)
        if not rating_match:
            # Sometimes it's just the number isolated in a green badge
            rating_match = re.search(r"\b([1-5]\.\d)\b", all_text)
            
        if rating_match:
            rating_raw = rating_match.group(1)
            
        # Regex for Reviews/Ratings count
        review_match = re.search(r"([\d,]+)\s*(?:Ratings|Reviews)", all_text, re.IGNORECASE)
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
        platform="meesho",
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

class MeeshoConnector(BaseConnector):
    """Playwright-powered connector for Meesho (meesho.com)."""

    platform = "meesho"

    BASE_URL: str = _BASE_URL
    PAGE_LOAD_TIMEOUT: int = _PAGE_LOAD_TIMEOUT
    SELECTOR_TIMEOUT: int = _SELECTOR_TIMEOUT
    MAX_RESULTS: int = _MAX_RESULTS

    def search(self, query: str) -> list[SearchResult]:
        if not query or not query.strip():
            logger.warning("[meesho] Empty query — returning []")
            return []

        url = f"{self.BASE_URL}?{urllib.parse.urlencode({'q': query.strip()})}"
        logger.info("[meesho] Scraping: %s", url)

        try:
            return self._run_scrape(url)
        except Exception:
            logger.exception("[meesho] Unhandled exception while scraping %r — returning []", url)
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
                logger.warning("[meesho] Timed out waiting for results on %s — returning []", url)
            except Exception:
                logger.exception("[meesho] Scrape failed for %s", url)
            finally:
                browser.close()

        logger.info("[meesho] Returning %d result(s) for URL %s", len(results), url)
        return results

    def _navigate(self, page: Page, url: str) -> None:
        page.goto(url, timeout=self.PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
        page.wait_for_selector(_CONTAINER, timeout=self.SELECTOR_TIMEOUT)

    def _extract_results(self, page: Page) -> list[SearchResult]:
        cards = page.locator(_CONTAINER)
        total = cards.count()
        logger.debug("[meesho] Found %d product cards", total)

        results: list[SearchResult] = []
        for i in range(min(total, self.MAX_RESULTS)):
            card = cards.nth(i)
            try:
                result = _extract_card(card)
                if result is not None:
                    results.append(result)
            except Exception:
                logger.exception("[meesho] Failed to extract card %d — skipping", i)

        return results
