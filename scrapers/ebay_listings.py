"""
eBay UK active-listings browser.

Fetches newly-listed Buy It Now items in specified categories within a
price range, returning them in the same dict format used by the Gumtree
scraper so the same comparison + alert pipeline handles both sources.
"""

import logging
import re
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Human-readable names used in log output
CATEGORY_NAMES: Dict[int, str] = {
    # Electronics
    293: "Sound & Vision",
    58058: "Computing",
    15032: "Mobile Phones",
    625: "Cameras & Photography",
    # Video Games & Consoles
    1249: "Video Games & Consoles",
    # Toys, Games & Collectibles
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

    for cat_id in category_ids:
        cat_name = CATEGORY_NAMES.get(cat_id, str(cat_id))
        log.info(f"eBay listings: scanning '{cat_name}' (cat {cat_id})")

        for page_num in range(1, pages_per_cat + 1):
            items = _fetch_page(cat_id, page_num, min_price, max_price, bin_only)
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

    log.info(f"eBay listings total: {len(all_listings)} items across {len(category_ids)} categories")
    return all_listings


# ── Internal ─────────────────────────────────────────────────────────────────

def _fetch_page(
    cat_id: int,
    page: int,
    min_price: float,
    max_price: float,
    bin_only: bool,
) -> List[Dict]:
    params = {
        "_sacat": cat_id,
        "_sop": 10,           # sort: newly listed
        "_udlo": int(min_price),
        "_udhi": int(max_price),
        "LH_PrefLoc": 1,      # UK sellers only
        "_pgn": page,
    }
    if bin_only:
        params["LH_BIN"] = 1  # Buy It Now only

    try:
        time.sleep(1.5)
        resp = requests.get(
            "https://www.ebay.co.uk/sch/i.html",
            params=params,
            headers=_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"eBay listings fetch failed (cat {cat_id}, page {page}): {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
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
        # Price ranges indicate auction bids — skip (ambiguous final price)
        if " to " in price_text.lower():
            continue

        price = _parse_price(price_text)
        if not price or price < min_price or price > max_price:
            continue

        href = link_el.get("href", "")
        item_id = _extract_item_id(href)
        if not item_id:
            continue

        # Canonical URL: strip tracking query params
        clean_url = f"https://www.ebay.co.uk/itm/{item_id}"

        listings.append({
            "title": title,
            "price": price,
            "url": clean_url,
            "item_id": item_id,
            "source": "ebay_listing",
            "category_id": cat_id,
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
