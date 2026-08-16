# Sale Checker

eBay UK arbitrage scanner. Watches newly-listed Buy It Now items across chosen categories, checks them against eBay UK sold prices, and sends a Telegram alert when the potential markup meets your minimum threshold.

---

## How it works

1. Scans eBay UK for active Buy It Now listings in configured categories
2. Looks up the average eBay UK *sold* price for each item
3. Sends a Telegram message when the potential markup meets your minimum

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

### 3 — Get an eBay API key (free)

1. Go to **developer.ebay.com** and sign in with your normal eBay account
2. Go to **My Account → Application Keysets → Production**
3. Create a new keyset and copy your **App ID** and **Cert ID**

### 4 — Configure your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum:

| Variable | What it is |
|---|---|
| `EBAY_APP_ID` | Your eBay App ID (Client ID) from developer.ebay.com |
| `EBAY_CERT_ID` | Your eBay Cert ID (Client Secret) from developer.ebay.com |
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/botfather) — send `/newbot` |
| `TELEGRAM_CHAT_ID` | Your chat ID (see `.env.example` for instructions) |

### 5 — Run

```bash
# Continuous loop (checks every CHECK_INTERVAL_MINUTES, default 30 min)
python main.py

# Single pass then exit — useful for testing or cron
python main.py --once
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

| Variable | Default | Description |
|---|---|---|
| `EBAY_APP_ID` | — | eBay API App ID (required) |
| `EBAY_CERT_ID` | — | eBay API Cert ID (required) |
| `MIN_PRICE` | `5` | Skip listings cheaper than this (£) |
| `MAX_PRICE` | `500` | Skip listings more expensive than this (£) |
| `MIN_MARKUP_PCT` | `100` | Minimum markup % to trigger an alert (100 = double your money) |
| `EBAY_CATEGORY_IDS` | several | Comma-separated eBay UK category IDs to scan |
| `EBAY_PAGES_PER_CATEGORY` | `2` | Pages fetched per category (~50 listings each) |
| `EBAY_BIN_ONLY` | `true` | `true` = Buy It Now only; `false` = include auctions |
| `CHECK_INTERVAL_MINUTES` | `30` | How often the loop re-runs |
| `DB_PATH` | `sale_checker.db` | SQLite database path |
