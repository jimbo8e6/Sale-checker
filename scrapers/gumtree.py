"""
Gumtree UK scraper using Playwright (headless Chromium).

Tries two extraction strategies in order:
  1. __NEXT_DATA__ JSON blob embedded in the page (fast, stable)
  2. DOM element walk with multiple CSS selector fallbacks
"""

import json
import logging
import re
import time
from typing import Dict, List, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# CSS selector sets tried in order for the DOM fallback
_CARD_SELECTORS = [
    "article[data-testid='listing-card']",
    "article.listing-maxi",
    "li[data-q='listing']",
    "div[data-q='listing-result']",
    "[class*='natural-listing-maxi']",
    "[class*='ListingCard']",
]
_TITLE_SELECTORS = [
    "h2",
    "[data-q='listing-title']",
    "[class*='listing-title']",
    "a[class*='title']",
]
_PRICE_SELECTORS = [
    "[data-q='price']",
    "[class*='listing-price']",
    "strong[class*='price']",
    "span[class*='price']",
]


def scrape_gumtree(postcode: str, radius_miles: int = 15, max_pages: int = 3) -> List[Dict]:
    """Return a list of listing dicts from Gumtree within radius of postcode."""
    slug = postcode.replace(" ", "").upper()
    base_url = (
        f"https://www.gumtree.com/search"
        f"?search_category=for-sale"
        f"&q="
        f"&search_location={slug}"
        f"&distance={radius_miles}"
        f"&seller_type=private"
    )

    all_listings: List[Dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=_UA,
            viewport={"width": 1440, "height": 900},
            locale="en-GB",
            timezone_id="Europe/London",
        )
        ctx.set_extra_http_headers({
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        })
        page = ctx.new_page()

        # Drop images/fonts/ads to speed up page load
        page.route(
            "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,otf}",
            lambda r: r.abort(),
        )
        page.route("**/ads/**", lambda r: r.abort())
        page.route("**/analytics*", lambda r: r.abort())
        page.route("**/tracking*", lambda r: r.abort())

        seen_urls: set = set()

        for page_num in range(1, max_pages + 1):
            url = base_url + (f"&page={page_num}" if page_num > 1 else "")
            log.debug(f"Fetching Gumtree page {page_num}: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(3_000)
            except PWTimeout:
                log.warning(f"Gumtree page {page_num} timed out")
                break
            except Exception as e:
                log.error(f"Gumtree navigation error (page {page_num}): {e}")
                break

            # Dismiss cookie/consent banner if present
            _dismiss_consent(page)

            # --- Strategy 1: __NEXT_DATA__ ---
            raw_next = page.evaluate(
                "document.getElementById('__NEXT_DATA__')?.textContent ?? null"
            )
            page_listings = _from_next_data(raw_next) if raw_next else []

            # --- Strategy 2: DOM walk ---
            if not page_listings:
                page_listings = _from_dom(page)

            if not page_listings:
                log.info(f"No listings found on Gumtree page {page_num} — stopping pagination")
                break

            # Deduplicate across pages
            new = [l for l in page_listings if l["url"] not in seen_urls]
            for l in new:
                seen_urls.add(l["url"])
            all_listings.extend(new)

            log.info(f"Gumtree page {page_num}: {len(new)} new listings")
            time.sleep(2)

        ctx.close()
        browser.close()

    log.info(f"Gumtree total: {len(all_listings)} listings")
    return all_listings


# ── Helpers ──────────────────────────────────────────────────────────────────

def _dismiss_consent(page) -> None:
    """Click through GDPR / cookie consent dialogs."""
    try:
        for selector in [
            "button:has-text('Accept all')",
            "button:has-text('Accept All')",
            "button:has-text('Accept')",
            "button[id*='accept']",
            "[class*='consent'] button",
        ]:
            btn = page.query_selector(selector)
            if btn:
                btn.click()
                page.wait_for_timeout(1_000)
                return
    except Exception:
        pass


def _from_next_data(raw: str) -> List[Dict]:
    """Walk __NEXT_DATA__ JSON tree looking for listing-shaped objects."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []

    listings: List[Dict] = []
    seen: set = set()

    def walk(obj):
        if isinstance(obj, dict):
            # Listing-shaped: has title + price + some kind of identifier
            has_title = "title" in obj
            has_price = "price" in obj or "displayPrice" in obj
            has_id = "id" in obj or "url" in obj or "vipUrl" in obj or "adId" in obj

            if has_title and has_price and has_id:
                price_raw = obj.get("price") or obj.get("displayPrice") or ""
                if isinstance(price_raw, dict):
                    price_raw = (
                        price_raw.get("displayPrice")
                        or price_raw.get("amount")
                        or ""
                    )
                price = _parse_price(str(price_raw))

                raw_url = obj.get("url") or obj.get("vipUrl") or ""
                if not raw_url and "adId" in obj:
                    raw_url = f"/p/{obj['adId']}"
                url = raw_url if raw_url.startswith("http") else f"https://www.gumtree.com{raw_url}"

                if price and url and url not in seen:
                    seen.add(url)
                    listings.append({
                        "title": str(obj.get("title", "")).strip(),
                        "price": price,
                        "url": url,
                        "source": "gumtree",
                    })
            else:
                for v in obj.values():
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return listings


def _from_dom(page) -> List[Dict]:
    """Extract listings via DOM selectors as a fallback."""
    listings: List[Dict] = []

    cards = []
    for sel in _CARD_SELECTORS:
        cards = page.query_selector_all(sel)
        if cards:
            log.debug(f"Gumtree DOM: matched {len(cards)} cards with '{sel}'")
            break

    for card in cards:
        try:
            title = _first_text(card, _TITLE_SELECTORS)
            price = _first_price(card, _PRICE_SELECTORS)
            link = card.query_selector("a[href]")
            href = link.get_attribute("href") if link else None

            if not title or not price or not href:
                continue

            url = href if href.startswith("http") else f"https://www.gumtree.com{href}"
            listings.append({
                "title": title,
                "price": price,
                "url": url,
                "source": "gumtree",
            })
        except Exception:
            continue

    return listings


def _first_text(element, selectors: List[str]) -> Optional[str]:
    for sel in selectors:
        el = element.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if text:
                return text
    return None


def _first_price(element, selectors: List[str]) -> Optional[float]:
    for sel in selectors:
        el = element.query_selector(sel)
        if el:
            price = _parse_price(el.inner_text())
            if price:
                return price
    return None


def _parse_price(text: str) -> Optional[float]:
    text = text.replace(",", "").strip()
    m = re.search(r"£?([\d]+(?:\.[\d]{1,2})?)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None
