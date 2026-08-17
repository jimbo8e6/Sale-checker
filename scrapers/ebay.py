"""
eBay UK sold price lookup using the eBay Finding API.

Uses findCompletedItems to get recent sold prices for a search query,
then returns a trimmed mean to use as the comparison price.
"""

import base64
import logging
import re
import time
from typing import List, Optional

import requests

import config

log = logging.getLogger(__name__)

_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_SCOPE = "https://api.ebay.com/oauth/api_scope"

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
        return _cached_token
    except Exception as e:
        log.error(f"eBay token request failed: {e}")
        return None

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

    token = _get_token()
    if not token:
        return []

    time.sleep(delay)

    try:
        resp = requests.get(
            _SEARCH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
            },
            params={
                "q": clean,
                "filter": "soldItemsOnly:true,priceCurrency:GBP",
                "limit": max_results,
            },
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"eBay sold price lookup failed for {clean!r}: {e}")
        return []

    items = resp.json().get("itemSummaries", [])

    prices: List[float] = []
    for item in items:
        try:
            price = float(item["price"]["value"])
            if price > 0:
                prices.append(price)
        except (KeyError, ValueError, TypeError):
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
