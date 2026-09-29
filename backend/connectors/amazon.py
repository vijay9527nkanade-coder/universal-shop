"""
connectors/amazon.py
====================
Playwright-powered connector for Amazon search results (amazon.in).

Design notes
------------
* Uses the **synchronous** Playwright API so the method signature matches
  ``BaseConnector.search()`` without requiring callers to be async.
  In an async FastAPI route, run this inside ``asyncio.to_thread()`` or
  ``loop.run_in_executor()`` to avoid blocking the event loop.

* Browser context is created fresh per ``search()`` call so the connector
  is stateless and safe to call from multiple threads simultaneously
  (each call gets its own browser context and page).

* Anti-detection measures applied:
    - Realistic User-Agent string
    - Viewport and locale matching a real device
    - Hides ``navigator.webdriver`` via ``init_script``
    - Uses ``networkidle`` wait + explicit element wait before scraping

* All extraction is wrapped in per-card try/except so a single malformed
  card never aborts the whole result list.

* On any unrecoverable error the method logs the exception and returns ``[]``
  rather than propagating, in line with the "fail silently" contract.

Selectors used (stable attribute-based selectors, not volatile class names)
---------------------------------------------------------------------------
Container : [data-component-type="s-search-result"][data-asin]
Name      : h2 span  (first non-empty text inside the h2)
URL       : h2 a.a-link-normal  (href attribute, relative → absolute)
Price     : span.a-price > span.a-offscreen  (screen-reader text: "₹1,299")
Rating    : span[aria-label*="out of 5"]  (aria-label: "4.3 out of 5 stars")
Reviews   : span[aria-label*="ratings"], span[aria-label*="reviews"]
Image     : img.s-image  (src attribute)
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

_BASE_URL = "https://www.amazon.in/s"
_PAGE_LOAD_TIMEOUT = 30_000   # ms — overall page load cap
_SELECTOR_TIMEOUT = 15_000    # ms — wait for first result card
_MAX_RESULTS = 20             # cap per query

# Stable container selector — only organic results carry both attributes
_CONTAINER = '[data-component-type="s-search-result"][data-asin]'

# Stealth User-Agent (Chrome on Windows)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Helper parsers
# ---------------------------------------------------------------------------

def _parse_price(raw: Optional[str]) -> Optional[float]:
    """Strip currency symbols / commas and return a float, or None.

    Handles inputs like "₹1,299.00", "Rs.1,299.00", "$19.99", "1299".
    Currency prefixes ending in a dot (e.g. "Rs.") are handled by
    extracting the last valid decimal number from the cleaned string.
    """
    if not raw:
        return None
    # Remove everything that isn't a digit or a decimal separator
    cleaned = re.sub(r"[^\d.]", "", raw.replace(",", ""))
    if not cleaned:
        return None
    # If multiple dots remain (e.g. ".1299.00" from "Rs.1,299.00"),
    # extract the rightmost decimal number using a regex
    match = re.search(r"\d+(?:\.\d+)?$", cleaned)
    try:
        return float(match.group()) if match else None
    except (ValueError, AttributeError):
        return None


def _parse_rating(raw: Optional[str]) -> Optional[float]:
    """Extract the leading float from strings like '4.3 out of 5 stars'."""
    if not raw:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", raw)
    try:
        return float(match.group(1)) if match else None
    except (ValueError, AttributeError):
        return None


def _parse_review_count(raw: Optional[str]) -> Optional[int]:
    """Extract an integer from strings like '1,234 ratings' or '12K+'."""
    if not raw:
        return None
    # Handle shorthand like "2.3K" or "1M"
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
    except (ValueError, AttributeError):
        return None


def _absolute_url(href: Optional[str], base: str = "https://www.amazon.in") -> Optional[str]:
    """Convert a relative Amazon href to an absolute URL."""
    if not href:
        return None
    if href.startswith("http"):
        return href
    return urllib.parse.urljoin(base, href)


# ---------------------------------------------------------------------------
# Per-card extraction
# ---------------------------------------------------------------------------

def _extract_card(card, base_url: str = "https://www.amazon.in") -> Optional[SearchResult]:
    """Extract a SearchResult from a single Playwright Locator card.

    Returns ``None`` if the card doesn't have the minimum required fields
    (name + product_url).
    """

    # --- Name ---
    try:
        name_el = card.locator("h2 span").first
        name = name_el.inner_text(timeout=2_000).strip()
    except Exception:
        name = ""

    # --- Product URL ---
    try:
        link_el = card.locator("h2 a.a-link-normal").first
        href = link_el.get_attribute("href", timeout=2_000)
        product_url = _absolute_url(href, base_url)
    except Exception:
        product_url = None

    # Both are required — skip card if missing
    if not name or not product_url:
        return None

    # --- Price ---
    # Primary: screen-reader span inside .a-price (most reliable)
    price_raw: Optional[str] = None
    try:
        price_el = card.locator("span.a-price > span.a-offscreen").first
        price_raw = price_el.inner_text(timeout=2_000).strip()
    except Exception:
        pass

    # Fallback: whole + fraction parts
    if not price_raw:
        try:
            whole = card.locator("span.a-price-whole").first.inner_text(timeout=1_000)
            frac = card.locator("span.a-price-fraction").first.inner_text(timeout=1_000)
            price_raw = f"{whole.strip('.')}.{frac.strip()}"
        except Exception:
            pass

    price = _parse_price(price_raw)

    # --- Rating ---
    rating_raw: Optional[str] = None
    try:
        # aria-label="4.3 out of 5 stars"
        rating_el = card.locator('span[aria-label*="out of 5"]').first
        rating_raw = rating_el.get_attribute("aria-label", timeout=2_000)
    except Exception:
        pass

    # Fallback: icon alt text inside the rating widget
    if not rating_raw:
        try:
            rating_raw = card.locator("span.a-icon-alt").first.inner_text(timeout=1_000)
        except Exception:
            pass

    rating = _parse_rating(rating_raw)

    # --- Review count ---
    review_raw: Optional[str] = None
    for sel in (
        'span[aria-label*="ratings"]',
        'span[aria-label*="reviews"]',
        "span.a-size-base.s-underline-text",
        "a span.a-size-base",
    ):
        try:
            el = card.locator(sel).first
            # Prefer aria-label (contains the count as text: "1,234 ratings")
            review_raw = el.get_attribute("aria-label", timeout=1_000)
            if not review_raw:
                review_raw = el.inner_text(timeout=1_000)
            if review_raw:
                break
        except Exception:
            continue

    review_count = _parse_review_count(review_raw)

    # --- Image URL ---
    image_url: Optional[str] = None
    try:
        img_el = card.locator("img.s-image").first
        # Prefer data-src (lazy-loaded) then src
        image_url = img_el.get_attribute("src", timeout=2_000)
    except Exception:
        pass

    return SearchResult(
        name=name,
        price=price,
        rating=rating,
        review_count=review_count,
        image_url=image_url,
        product_url=product_url,
        platform="amazon",
    )


# ---------------------------------------------------------------------------
# Browser initialisation helpers
# ---------------------------------------------------------------------------

def _new_browser(pw: Playwright) -> Browser:
    """Launch a headless Chromium browser with stealth settings."""
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
    """Create a browser context + page that looks like a real Chrome session."""
    context = browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        java_script_enabled=True,
    )
    # Hide automation flag
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return context.new_page()


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class AmazonConnector(BaseConnector):
    """Playwright-powered connector for Amazon India (amazon.in).

    Each call to ``search()`` launches a headless Chromium browser, loads
    the Amazon search results page, extracts up to ``_MAX_RESULTS`` product
    cards, closes the browser, and returns the results.

    Configuration
    -------------
    Subclass and override class attributes to target a different Amazon
    locale or adjust timeouts:

    .. code-block:: python

        class AmazonUSConnector(AmazonConnector):
            platform = "amazon_us"
            BASE_URL = "https://www.amazon.com/s"
    """

    platform = "amazon"

    BASE_URL: str = _BASE_URL
    PAGE_LOAD_TIMEOUT: int = _PAGE_LOAD_TIMEOUT
    SELECTOR_TIMEOUT: int = _SELECTOR_TIMEOUT
    MAX_RESULTS: int = _MAX_RESULTS

    # ------------------------------------------------------------------ #

    def search(self, query: str) -> list[SearchResult]:
        """Search Amazon for *query* and return structured product results.

        Parameters
        ----------
        query:
            Free-text product search string, e.g. ``"wireless headphones"``.

        Returns
        -------
        list[SearchResult]
            Up to ``MAX_RESULTS`` results.  Returns ``[]`` on any error.
        """
        if not query or not query.strip():
            logger.warning("[amazon] Empty query — returning []")
            return []

        url = f"{self.BASE_URL}?{urllib.parse.urlencode({'k': query.strip()})}"
        logger.info("[amazon] Scraping: %s", url)

        try:
            return self._run_scrape(url)
        except Exception:
            logger.exception(
                "[amazon] Unhandled exception while scraping %r — returning []", url
            )
            return []

    # ------------------------------------------------------------------ #
    # Internal scraping logic
    # ------------------------------------------------------------------ #

    def _run_scrape(self, url: str) -> list[SearchResult]:
        results: list[SearchResult] = []

        with sync_playwright() as pw:
            browser = _new_browser(pw)
            try:
                page = _new_page(browser)
                self._navigate(page, url)
                results = self._extract_results(page)
            except PlaywrightTimeoutError:
                logger.warning(
                    "[amazon] Timed out waiting for results on %s — returning []", url
                )
            except Exception:
                logger.exception("[amazon] Scrape failed for %s", url)
            finally:
                browser.close()

        logger.info("[amazon] Returning %d result(s) for URL %s", len(results), url)
        return results

    def _navigate(self, page: Page, url: str) -> None:
        """Navigate to *url* and wait until the first result card is visible."""
        page.goto(url, timeout=self.PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")

        # Check for CAPTCHA / robot-check page
        if any(
            kw in page.title().lower()
            for kw in ("robot", "captcha", "sorry", "automated")
        ):
            logger.warning("[amazon] CAPTCHA / robot-check detected on %s", url)
            raise ConnectorError("amazon", "CAPTCHA detected — aborting scrape")

        # Wait until at least one product card appears
        page.wait_for_selector(_CONTAINER, timeout=self.SELECTOR_TIMEOUT)

    def _extract_results(self, page: Page) -> list[SearchResult]:
        """Iterate product cards and extract SearchResult dicts."""
        cards = page.locator(_CONTAINER)
        total = cards.count()
        logger.debug("[amazon] Found %d product cards", total)

        results: list[SearchResult] = []
        for i in range(min(total, self.MAX_RESULTS)):
            card = cards.nth(i)
            try:
                result = _extract_card(card)
                if result is not None:
                    results.append(result)
            except Exception:
                logger.exception("[amazon] Failed to extract card %d — skipping", i)

        return results
