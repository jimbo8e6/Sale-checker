"""Telegram notification via Bot API (no library dependency — just requests)."""

import logging
from typing import Dict

import requests

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_alert(bot_token: str, chat_id: str, listing: Dict, ebay_avg: float) -> bool:
    """Send a deal alert to a Telegram chat. Returns True on success."""
    local_price = listing["price"]
    profit = ebay_avg - local_price
    markup_pct = (profit / local_price) * 100
    source = listing.get("source", "")

    if source == "ebay_listing":
        header = "*eBay Flip Opportunity*"
        price_label = "Listed at:"
    else:
        header = "*Local Deal — Gumtree*"
        price_label = "Local price:"

    text = (
        f"{header}\n\n"
        f"*{_escape(listing['title'])}*\n\n"
        f"{price_label}    *£{local_price:.2f}*\n"
        f"eBay avg sold: £{ebay_avg:.2f}\n"
        f"Potential profit: *£{profit:.2f}* ({markup_pct:.0f}% markup)\n\n"
        f"{listing['url']}"
    )

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }

    try:
        resp = requests.post(
            _API.format(token=bot_token),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        log.info(f"Telegram alert sent: {listing['title']!r}")
        return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def _escape(text: str) -> str:
    """Escape Markdown special characters in item titles."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text
