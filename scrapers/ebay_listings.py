"""
eBay UK active-listings fetcher using the official eBay Browse API.

Requires EBAY_APP_ID and EBAY_CERT_ID in .env (from developer.ebay.com).
No browser or scraping involved — clean API calls only.
"""

import base64
import logging
import time
from typing import Dict, List, Optional

import requests

import config

log = logging.getLogger(__name__)

_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_SCOPE = "https://api.ebay.com/oauth/api_scope"

CATEGORY_NAMES: Dict[int, str] = {
    293: "Sound & Vision",
    58058: "Computing",
    15032: "Mobile Phones",
    625: "Cameras & Photography",
    1249: "Video Games & Consoles",
    220: "Toys & Games",
    1: "Collectibles",
}

_cached_token: Optional[str] = None
_token_expiry: float = 0.0


def _get_token() -> Optional[str]:
    global _cached_token, _token_expiry

    if _cached_token and time.time() < _token_expiry - 60:
        return _cached_token

    if not config.EBAY_APP_ID or not config.EBAY_CERT_ID:
        log.error("EBAY_APP_ID and EBAY_CERT_ID must be set in .env")
        return None

    credentials = base64.b64encode(
        f"{config.EBAY_APP_ID}:{config.EBAY_CERT_ID}".encode()
    ).decode()

    try:
        resp = requests.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": _SCOPE},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _cached_token = data["access_token"]
        _token_expiry = time.time() + data["expires_in"]
        log.info("eBay API token obtained")
        return _cached_token
    except Exception as e:
        log.error(f"eBay token request failed: {e}")
        return None


def browse_categories(
    category_ids: List[int],
    min_price: float = 5.0,
    max_price: float = 500.0,
    pages_per_cat: int = 2,
    bin_only: bool = True,
) -> List[Dict]:
    """
    Fetch newly-listed eBay UK items across all given category IDs via the Browse API.
    Returns deduplicated listings.
    """
    token = _get_token()
    if not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
        "Content-Type": "application/json",
    }

    filters = [
        f"price:[{int(min_price)}..{int(max_price)}]",
        "priceCurrency:GBP",
        "itemLocationCountry:GB",
    ]
    if bin_only:
        filters.append("buyingOptions:{FIXED_PRICE}")

    filter_str = ",".join(filters)
    limit = 200
    all_listings: List[Dict] = []
    seen_ids: set = set()

    for cat_id in category_ids:
        cat_name = CATEGORY_NAMES.get(cat_id, str(cat_id))
        log.info(f"eBay API: scanning '{cat_name}' (cat {cat_id})")

        for page_num in range(pages_per_cat):
            offset = page_num * limit
            try:
                resp = requests.get(
                    _SEARCH_URL,
                    headers=headers,
                    params={
                        "category_ids": cat_id,
                        "filter": filter_str,
                        "sort": "newlyListed",
                        "limit": limit,
                        "offset": offset,
                    },
                    timeout=20,
                )
                resp.raise_for_status()
            except Exception as e:
                log.warning(f"eBay API request failed (cat {cat_id}, page {page_num + 1}): {e}")
                break

            data = resp.json()
            items = data.get("itemSummaries", [])

            if not items:
                log.debug(f"  page {page_num + 1}: no results")
                break

            new_count = 0
            for item in items:
                item_id = item.get("itemId", "")
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                title = item.get("title", "").strip()
                price_info = item.get("price", {})
                price_str = price_info.get("value", "")
                url = item.get("itemWebUrl", "")

                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    continue

                if not title or not url or not price:
                    continue

                all_listings.append({
                    "title": title,
                    "price": price,
                    "url": url,
                    "item_id": item_id,
                    "source": "ebay_listing",
                })
                new_count += 1

            log.info(f"  page {page_num + 1}: {new_count} new items")

            if len(items) < limit:
                break  # last page

            time.sleep(1)

        time.sleep(1)

    log.info(f"eBay API total: {len(all_listings)} items across {len(category_ids)} categories")
    return all_listings
