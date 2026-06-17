import os
from dotenv import load_dotenv

load_dotenv()

POSTCODE = os.getenv("POSTCODE", "LN11 9YX")
RADIUS_MILES = int(os.getenv("RADIUS_MILES", "15"))
MIN_MARKUP_PCT = float(os.getenv("MIN_MARKUP_PCT", "100"))
MIN_PRICE = float(os.getenv("MIN_PRICE", "5"))
MAX_PRICE = float(os.getenv("MAX_PRICE", "500"))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DB_PATH = os.getenv("DB_PATH", "sale_checker.db")
