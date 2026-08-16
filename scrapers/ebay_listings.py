"""
eBay UK active-listings browser.

Uses Playwright (headless Chromium) to fetch newly-listed Buy It Now items
in specified categories, bypassing eBay's bot-detection on plain HTTP requests.
"""

import logging
import re
import time
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

CATEGORY_NAMES: Dict[int, str] = {
    293: "Sound & Vision",
    58058: "Computing",
    15032: "Mobile Phones",
    625: "Cameras & Photography",
    1249: "Video Games & Consoles",
    220: "Toys & Games",
    1: "Collectibles",
}


def browse_categories(
    category_ids: List[int],
    min_price: float = 5.0,
    max_price: float = 500.0,
    pages_per_cat: int = 2,
    bin_only: bool = True,
) -> List[Dict]:
    """
    Scrape newly-listed eBay UK items across all given category IDs.
    Returns deduplicated listings sorted by category then page order.
    """
    all_listings: List[Dict] = []
    seen_item_ids: set = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=_UA,
            viewport={"width": 1366, "height": 768},
            locale="en-GB",
        )
        ctx.set_extra_http_headers({"Accept-Language": "en-GB,en;q=0.9"})
        page = ctx.new_page()

        # Skip images/fonts to speed up loads
        page.route(
            "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,otf}",
            lambda r: r.abort(),
        )

        _accepted_cookies = False

        for cat_id in category_ids:
            cat_name = CATEGORY_NAMES.get(cat_id, str(cat_id))
            log.info(f"eBay listings: scanning '{cat_name}' (cat {cat_id})")

            for page_num in range(1, pages_per_cat + 1):
                params = (
                    f"_sacat={cat_id}&_sop=10"
                    f"&_udlo={int(min_price)}&_udhi={int(max_price)}"
                    f"&LH_PrefLoc=1&_pgn={page_num}"
                    + ("&LH_BIN=1" if bin_only else "")
                )
                url = f"https://www.ebay.co.uk/sch/i.html?{params}"

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    # Wait for any JS-triggered redirects to settle
                    try:
                        page.wait_for_load_state("networkidle", timeout=8_000)
                    except PWTimeout:
                        pass  # proceed if networkidle takes too long
                    page.wait_for_timeout(1_000)
                except PWTimeout:
                    log.warning(f"eBay page timed out (cat {cat_id}, page {page_num})")
                    break
                except Exception as e:
                    log.warning(f"eBay navigation error (cat {cat_id}, page {page_num}): {e}")
                    break

                # Accept cookie banner once per session
                if not _accepted_cookies:
                    _accepted_cookies = _dismiss_consent(page)

                try:
                    html = page.content()
                except Exception as e:
                    log.warning(f"eBay could not read page content (cat {cat_id}, page {page_num}): {e}")
                    break

                items = _parse_listings(html, min_price, max_price)
                if not items:
                    log.debug(f"  page {page_num}: no results — stopping")
                    break

                new = [i for i in items if i["item_id"] not in seen_item_ids]
                for i in new:
                    seen_item_ids.add(i["item_id"])
                all_listings.extend(new)

                log.debug(f"  page {page_num}: {len(items)} items, {len(new)} new")

                if len(items) < 40:
                    break  # last page reached

                time.sleep(2)

            time.sleep(3)  # courteous gap between categories

        ctx.close()
        browser.close()

    log.info(f"eBay listings total: {len(all_listings)} items across {len(category_ids)} categories")
    return all_listings


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dismiss_consent(page) -> bool:
    try:
        for sel in [
            "button#gdpr-banner-accept",
            "button[aria-label*='Accept']",
            "button:has-text('Accept all')",
            "button:has-text('Accept All')",
        ]:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                page.wait_for_timeout(1_000)
                return True
    except Exception:
        pass
    return False


def _parse_listings(html: str, min_price: float, max_price: float) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    listings: List[Dict] = []

    for item in soup.select("li.s-item"):
        title_el = item.select_one("div.s-item__title, h3.s-item__title")
        price_el = item.select_one("span.s-item__price")
        link_el = item.select_one("a.s-item__link")

        if not title_el or not price_el or not link_el:
            continue

        title = title_el.get_text(strip=True)
        if title.lower() in ("shop on ebay", ""):
            continue

        price_text = price_el.get_text(strip=True)
        if " to " in price_text.lower():
            continue  # price range = auction, skip

        price = _parse_price(price_text)
        if not price or price < min_price or price > max_price:
            continue

        href = link_el.get("href", "")
        item_id = _extract_item_id(href)
        if not item_id:
            continue

        listings.append({
            "title": title,
            "price": price,
            "url": f"https://www.ebay.co.uk/itm/{item_id}",
            "item_id": item_id,
            "source": "ebay_listing",
        })

    return listings


def _extract_item_id(url: str) -> Optional[str]:
    m = re.search(r"/itm/(?:[^/]+/)?(\d{10,})", url)
    return m.group(1) if m else None


def _parse_price(text: str) -> Optional[float]:
    m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    if m:
        try:
            return float(m.group().replace(",", ""))
        except ValueError:
            pass
    return None
