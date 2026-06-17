"""
Sale Checker — arbitrage scanner.

Sources:
  • Gumtree  — private listings within RADIUS_MILES of POSTCODE
  • eBay UK  — newly-listed Buy It Now items in configured categories

Both sources are checked against eBay UK sold prices.
Alerts fire via Telegram when markup >= MIN_MARKUP_PCT (default 100%).

Usage:
    python main.py            # run both checks then loop every CHECK_INTERVAL_MINUTES
    python main.py --once     # single pass then exit (good for cron)
    python main.py --source gumtree   # only run Gumtree check in the loop
    python main.py --source ebay      # only run eBay listings check in the loop

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
from typing import Dict, List

import schedule

import config
from database import Database
from notifier.telegram import send_alert
from scrapers.ebay import get_average_sold_price
from scrapers.ebay_listings import browse_categories
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


# ── Shared processing ─────────────────────────────────────────────────────────

def _process(listings: List[Dict], tag: str) -> None:
    """
    For each listing:
      - skip if already seen or outside price range
      - look up eBay sold average
      - alert + record if markup threshold met
    """
    for listing in listings:
        url = listing.get("url", "")
        title = listing.get("title", "").strip()
        price = listing.get("price", 0.0)

        if not url or not title or not price:
            continue
        if price < config.MIN_PRICE or price > config.MAX_PRICE:
            continue
        if db.is_seen(url):
            continue

        log.info(f"[{tag}] New: {title!r} @ £{price:.2f}")

        ebay_avg = get_average_sold_price(title)

        if ebay_avg is None:
            log.info("  No eBay sold data — skipping")
            db.record(url, title, price)
        else:
            markup_pct = ((ebay_avg - price) / price) * 100
            log.info(f"  eBay avg £{ebay_avg:.2f} | markup {markup_pct:.0f}%")

            if markup_pct >= config.MIN_MARKUP_PCT:
                log.info(f"  ALERT — {markup_pct:.0f}% markup!")
                alerted = False
                if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
                    alerted = send_alert(
                        config.TELEGRAM_BOT_TOKEN,
                        config.TELEGRAM_CHAT_ID,
                        listing,
                        ebay_avg,
                    )
                else:
                    log.warning("  Telegram not configured — deal logged only")
                db.record(url, title, price, ebay_avg, markup_pct, alerted=alerted)
            else:
                db.record(url, title, price, ebay_avg, markup_pct, alerted=False)

        time.sleep(2)  # rate-limit eBay sold-price queries


# ── Gumtree check ─────────────────────────────────────────────────────────────

def run_gumtree_check() -> None:
    log.info(
        f"=== Gumtree check | {config.POSTCODE} +{config.RADIUS_MILES} mi ==="
    )
    try:
        listings = scrape_gumtree(config.POSTCODE, config.RADIUS_MILES)
    except Exception as e:
        log.error(f"Gumtree scrape failed: {e}")
        return

    if not listings:
        log.warning("No listings returned from Gumtree — site may have changed or blocked the scraper")
        return

    _process(listings, "Gumtree")
    log.info(f"=== Gumtree check done | {db.recent_alert_count(24)} alerts today ===")


# ── eBay listings check ───────────────────────────────────────────────────────

def run_ebay_check() -> None:
    cat_count = len(config.EBAY_CATEGORY_IDS)
    log.info(
        f"=== eBay listings check | {cat_count} categories | "
        f"{'BIN only' if config.EBAY_BIN_ONLY else 'BIN + auctions'} ==="
    )
    try:
        listings = browse_categories(
            category_ids=config.EBAY_CATEGORY_IDS,
            min_price=config.MIN_PRICE,
            max_price=config.MAX_PRICE,
            pages_per_cat=config.EBAY_PAGES_PER_CATEGORY,
            bin_only=config.EBAY_BIN_ONLY,
        )
    except Exception as e:
        log.error(f"eBay listings browse failed: {e}")
        return

    if not listings:
        log.warning("No eBay listings returned")
        return

    _process(listings, "eBay")
    log.info(f"=== eBay check done | {db.recent_alert_count(24)} alerts today ===")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Arbitrage scanner")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single pass then exit (useful for cron)",
    )
    parser.add_argument(
        "--source",
        choices=["gumtree", "ebay", "both"],
        default="both",
        help="Which source to check (default: both)",
    )
    args = parser.parse_args()

    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — "
            "deals will be logged but not sent to Telegram"
        )

    log.info(
        f"Sale Checker starting | "
        f"£{config.MIN_PRICE}–£{config.MAX_PRICE} | "
        f"min markup {config.MIN_MARKUP_PCT:.0f}%"
    )

    run_gumtree = args.source in ("gumtree", "both")
    run_ebay = args.source in ("ebay", "both")

    if run_gumtree:
        run_gumtree_check()
    if run_ebay:
        run_ebay_check()

    if args.once:
        return

    if run_gumtree:
        schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(run_gumtree_check)
    if run_ebay:
        schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(run_ebay_check)

    log.info(f"Scheduler running — checking every {config.CHECK_INTERVAL_MINUTES} minutes")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
