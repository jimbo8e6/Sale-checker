import os
from dotenv import load_dotenv

load_dotenv()

# ── Location (Gumtree) ────────────────────────────────────────────────────────
POSTCODE = os.getenv("POSTCODE", "LN11 9YX")
RADIUS_MILES = int(os.getenv("RADIUS_MILES", "15"))

# ── Shared filtering ──────────────────────────────────────────────────────────
MIN_MARKUP_PCT = float(os.getenv("MIN_MARKUP_PCT", "100"))
MIN_PRICE = float(os.getenv("MIN_PRICE", "5"))
MAX_PRICE = float(os.getenv("MAX_PRICE", "500"))

# ── eBay listings scan ────────────────────────────────────────────────────────
# Category IDs to browse for active listings.
# Defaults: Sound&Vision(293), Computing(58058), Mobile(15032), Cameras(625),
#           Video Games(1249), Toys(220), Collectibles(1)
_DEFAULT_CAT_IDS = "293,58058,15032,625,1249,220,1"
EBAY_CATEGORY_IDS: list[int] = [
    int(x.strip())
    for x in os.getenv("EBAY_CATEGORY_IDS", _DEFAULT_CAT_IDS).split(",")
    if x.strip().isdigit()
]
# Pages to fetch per category per run (each page ≈ 50 listings)
EBAY_PAGES_PER_CATEGORY = int(os.getenv("EBAY_PAGES_PER_CATEGORY", "2"))
# True = Buy It Now only (reliable fixed prices); False = include auctions
EBAY_BIN_ONLY = os.getenv("EBAY_BIN_ONLY", "true").lower() == "true"

# ── Scheduler ─────────────────────────────────────────────────────────────────
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Storage ───────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "sale_checker.db")
