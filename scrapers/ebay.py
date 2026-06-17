"""
eBay UK completed/sold listings scraper (no API key required).

Uses requests + BeautifulSoup against the public eBay search page with
the LH_Sold=1 & LH_Complete=1 filters.
"""

import logging
import re
import time
from typing import List, Optional

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

# Words that pollute eBay searches when taken from local listing titles
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
        # Retry with only the first 5 words — catches very specific titles
        short = " ".join(_clean(title).split()[:5])
        if short and short != _clean(title):
            log.debug(f"eBay: retrying with shorter query: {short!r}")
            prices = _fetch_prices(short, delay=2.0)

    if not prices:
        return None

    return _trimmed_mean(prices)


# ── Internal ─────────────────────────────────────────────────────────────────

def _fetch_prices(query: str, max_results: int = 25, delay: float = 1.5) -> List[float]:
    clean = _clean(query)
    if not clean:
        return []

    url = (
        "https://www.ebay.co.uk/sch/i.html"
        f"?_nkw={requests.utils.quote(clean)}"
        "&LH_Sold=1&LH_Complete=1&_sacat=0&_sop=13"
    )
    log.debug(f"eBay query: {clean!r}")

    time.sleep(delay)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"eBay request failed for {clean!r}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    prices: List[float] = []

    for item in soup.select("li.s-item")[:max_results]:
        price_el = item.select_one("span.s-item__price")
        if not price_el:
            continue

        text = price_el.get_text(strip=True)

        # Price range — take the midpoint
        if " to " in text.lower():
            parts = re.findall(r"[\d,]+\.?\d*", text)
            if len(parts) == 2:
                try:
                    mid = (
                        float(parts[0].replace(",", ""))
                        + float(parts[1].replace(",", ""))
                    ) / 2
                    prices.append(mid)
                except ValueError:
                    pass
            continue

        p = _parse_price(text)
        if p and p > 0:
            prices.append(p)

    log.debug(f"eBay: {len(prices)} prices for {clean!r}")
    return prices


def _trimmed_mean(prices: List[float]) -> float:
    """Mean with top/bottom 10% trimmed to reduce outlier impact."""
    prices = sorted(prices)
    if len(prices) >= 6:
        trim = max(1, len(prices) // 10)
        prices = prices[trim:-trim]
    return round(sum(prices) / len(prices), 2)


def _clean(title: str) -> str:
    cleaned = _NOISE_RE.sub("", title)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _parse_price(text: str) -> Optional[float]:
    m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    if m:
        try:
            return float(m.group().replace(",", ""))
        except ValueError:
            pass
    return None
