"""
eBay UK sold price lookup using the eBay Finding API.

Uses findCompletedItems to get recent sold prices for a search query,
then returns a trimmed mean to use as the comparison price.
"""

import logging
import re
import time
from typing import List, Optional

import requests

import config

log = logging.getLogger(__name__)

_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"

_NOISE_RE = re.compile(
    r"\b("
    r"for sale|cheap|bargain|must go|quick sale|ono|or near offer|"
    r"collection only|local pickup|pick up|good condition|great condition|"
    r"vgc|excellent|spares|repair|faulty|broken|damaged|unwanted|"
    r"job lot|bundle|joblot"
    r")\b",
    re.IGNORECASE,
)


def get_average_sold_price(title: str) -> Optional[float]:
    """
    Return a trimmed-mean sold price from eBay UK for the given listing title.
    Returns None if fewer than 2 results are found even after a shortened retry.
    """
    prices = _fetch_prices(title)

    if len(prices) < 2:
        short = " ".join(_clean(title).split()[:5])
        if short and short != _clean(title):
            log.debug(f"eBay: retrying with shorter query: {short!r}")
            prices = _fetch_prices(short, delay=2.0)

    if not prices:
        return None

    return _trimmed_mean(prices)


def _fetch_prices(query: str, max_results: int = 25, delay: float = 1.5) -> List[float]:
    clean = _clean(query)
    if not clean:
        return []

    if not config.EBAY_APP_ID:
        log.error("EBAY_APP_ID not set — cannot look up sold prices")
        return []

    time.sleep(delay)

    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": config.EBAY_APP_ID,
        "RESPONSE-DATA-FORMAT": "JSON",
        "GLOBAL-ID": "EBAY-GB",
        "keywords": clean,
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "paginationInput.entriesPerPage": max_results,
        "sortOrder": "EndTimeSoonest",
    }

    try:
        resp = requests.get(_FINDING_URL, params=params, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"eBay Finding API failed for {clean!r}: {e}")
        return []

    try:
        data = resp.json()
        items = (
            data["findCompletedItemsResponse"][0]
            ["searchResult"][0]
            .get("item", [])
        )
    except (KeyError, IndexError, ValueError) as e:
        log.warning(f"eBay Finding API unexpected response for {clean!r}: {e}")
        return []

    prices: List[float] = []
    for item in items:
        try:
            price_str = (
                item["sellingStatus"][0]["convertedCurrentPrice"][0]["__value__"]
            )
            price = float(price_str)
            if price > 0:
                prices.append(price)
        except (KeyError, IndexError, ValueError):
            continue

    log.debug(f"eBay sold: {len(prices)} prices for {clean!r}")
    return prices


def _trimmed_mean(prices: List[float]) -> float:
    prices = sorted(prices)
    if len(prices) >= 6:
        trim = max(1, len(prices) // 10)
        prices = prices[trim:-trim]
    return round(sum(prices) / len(prices), 2)


def _clean(title: str) -> str:
    cleaned = _NOISE_RE.sub("", title)
    return re.sub(r"\s{2,}", " ", cleaned).strip()
