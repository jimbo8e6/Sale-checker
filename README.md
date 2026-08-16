# Sale Checker

Arbitrage scanner that watches Gumtree and eBay UK for underpriced items and alerts you via Telegram when markup is above your threshold.

## How it works

1. Scrapes Gumtree for local private listings near your postcode
2. Scrapes eBay UK for active Buy It Now listings in chosen categories
3. Looks up the average eBay UK *sold* price for each item
4. Sends a Telegram message when the potential markup meets your minimum

---

## Running on macOS

### Prerequisites

You need **Python 3.11+** and **Homebrew** installed.

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python@3.11
```

### 1 — Clone and set up a virtual environment

```bash
git clone https://github.com/jimbo8e6/sale-checker.git
cd sale-checker

python3 -m venv .venv
source .venv/bin/activate
```

### 2 — Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3 — Configure your `.env` file

```bash
cp .env.example .env
```

Open `.env` in any editor and fill in at minimum:

| Variable | What it is |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/botfather) — send `/newbot` |
| `TELEGRAM_CHAT_ID` | Your chat ID (see `.env.example` for instructions) |
| `POSTCODE` | Your postcode for the Gumtree radius search |
| `RADIUS_MILES` | How far from your postcode to scan |

Everything else has sensible defaults and is optional to change.

### 4 — Run

```bash
# Continuous loop (checks every CHECK_INTERVAL_MINUTES, default 30 min)
python main.py

# Single pass then exit — useful for testing or cron
python main.py --once

# Only one source
python main.py --source gumtree
python main.py --source ebay
```

Logs are written to `sale_checker.log` and also printed to the terminal.

---

## Running as a scheduled job on Mac (launchd)

Create `~/Library/LaunchAgents/com.salechecker.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.salechecker</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/sale-checker/.venv/bin/python</string>
    <string>/path/to/sale-checker/main.py</string>
    <string>--once</string>
  </array>
  <key>StartInterval</key>
  <integer>1800</integer>
  <key>WorkingDirectory</key>
  <string>/path/to/sale-checker</string>
  <key>StandardOutPath</key>
  <string>/path/to/sale-checker/sale_checker.log</string>
  <key>StandardErrorPath</key>
  <string>/path/to/sale-checker/sale_checker_err.log</string>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
```

Replace `/path/to/sale-checker` with the actual path, then:

```bash
launchctl load ~/Library/LaunchAgents/com.salechecker.plist
```

To stop it:

```bash
launchctl unload ~/Library/LaunchAgents/com.salechecker.plist
```

---

## Configuration reference

All settings live in `.env`. See `.env.example` for the full list with comments.

| Variable | Default | Description |
|---|---|---|
| `POSTCODE` | `LN11 9YX` | Centre point for Gumtree search |
| `RADIUS_MILES` | `15` | Search radius in miles |
| `MIN_PRICE` | `5` | Skip listings cheaper than this (£) |
| `MAX_PRICE` | `500` | Skip listings more expensive than this (£) |
| `MIN_MARKUP_PCT` | `100` | Minimum markup % to trigger an alert (100 = double your money) |
| `EBAY_CATEGORY_IDS` | several | Comma-separated eBay UK category IDs to scan |
| `EBAY_PAGES_PER_CATEGORY` | `2` | Pages fetched per category (~50 listings each) |
| `EBAY_BIN_ONLY` | `true` | `true` = Buy It Now only; `false` = include auctions |
| `CHECK_INTERVAL_MINUTES` | `30` | How often the loop re-runs |
| `DB_PATH` | `sale_checker.db` | SQLite database path |
