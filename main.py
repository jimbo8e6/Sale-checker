"""
Sale Checker — local arbitrage scanner.

Scrapes Gumtree for items near a postcode, checks eBay UK sold prices,
and sends a Telegram alert for anything with 100%+ markup potential.

Usage:
    python main.py            # run once then loop every CHECK_INTERVAL_MINUTES
    python main.py --once     # single run then exit (good for cron)

Setup:
    1. cp .env.example .env
    2. Fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
    3. pip install -r requirements.txt
    4. playwright install chromium
    5. python main.py
"""

import argparse
import logging
import sys
import time

import schedule

import config
from database import Database
from notifier.telegram import send_alert
from scrapers.ebay import get_average_sold_price
from scrapers.gumtree import scrape_gumtree

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("sale_checker.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

db = Database(config.DB_PATH)


def run_check() -> None:
    log.info(
        f"--- Check started | {config.POSTCODE}, {config.RADIUS_MILES} mi, "
        f"min markup {config.MIN_MARKUP_PCT:.0f}% ---"
    )

    try:
        listings = scrape_gumtree(config.POSTCODE, config.RADIUS_MILES)
    except Exception as e:
        log.error(f"Gumtree scrape failed: {e}")
        return

    if not listings:
        log.warning("No listings returned from Gumtree — the site may have changed or blocked the scraper")
        return

    for listing in listings:
        url = listing.get("url", "")
        title = listing.get("title", "").strip()
        price = listing.get("price", 0.0)

        if not url or not title or not price:
            continue

        # Price range filter
        if price < config.MIN_PRICE or price > config.MAX_PRICE:
            continue

        # Skip already-processed listings
        if db.is_seen(url):
            continue

        log.info(f"New: {title!r} @ £{price:.2f}")

        ebay_avg = get_average_sold_price(title)

        if ebay_avg is None:
            log.info(f"  No eBay sold data found")
            db.record(url, title, price)
            continue

        markup_pct = ((ebay_avg - price) / price) * 100
        log.info(f"  eBay avg £{ebay_avg:.2f} | markup {markup_pct:.0f}%")

        if markup_pct >= config.MIN_MARKUP_PCT:
            log.info(f"  ALERT — {markup_pct:.0f}% markup on {title!r}")
            alerted = False
            if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
                alerted = send_alert(
                    config.TELEGRAM_BOT_TOKEN,
                    config.TELEGRAM_CHAT_ID,
                    listing,
                    ebay_avg,
                )
            else:
                log.warning("  Telegram not configured — skipping notification")
            db.record(url, title, price, ebay_avg, markup_pct, alerted=alerted)
        else:
            db.record(url, title, price, ebay_avg, markup_pct, alerted=False)

        # Be polite between eBay queries
        time.sleep(2)

    log.info(
        f"--- Check complete | {db.recent_alert_count(24)} alerts in last 24 h ---"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Local arbitrage scanner")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check then exit (useful for cron)",
    )
    args = parser.parse_args()

    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — "
            "deals will be logged but not sent to Telegram"
        )

    log.info(
        f"Sale Checker starting | "
        f"{config.POSTCODE} +{config.RADIUS_MILES} mi | "
        f"£{config.MIN_PRICE}–£{config.MAX_PRICE} | "
        f"min markup {config.MIN_MARKUP_PCT:.0f}%"
    )

    run_check()

    if args.once:
        return

    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(run_check)
    log.info(f"Scheduler running — next check in {config.CHECK_INTERVAL_MINUTES} minutes")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
