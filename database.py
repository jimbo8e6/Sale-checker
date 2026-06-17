import sqlite3
from datetime import datetime
from typing import Optional


class Database:
    def __init__(self, db_path: str = "sale_checker.db"):
        self.db_path = db_path
        self._init()

    def _init(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_listings (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    url         TEXT    UNIQUE NOT NULL,
                    title       TEXT,
                    local_price REAL,
                    ebay_avg    REAL,
                    markup_pct  REAL,
                    alerted     INTEGER DEFAULT 0,
                    first_seen  TEXT,
                    last_seen   TEXT
                )
            """)

    def is_seen(self, url: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT 1 FROM seen_listings WHERE url = ?", (url,)
            ).fetchone() is not None

    def record(
        self,
        url: str,
        title: str,
        local_price: float,
        ebay_avg: Optional[float] = None,
        markup_pct: Optional[float] = None,
        alerted: bool = False,
    ):
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO seen_listings
                    (url, title, local_price, ebay_avg, markup_pct, alerted, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET last_seen = excluded.last_seen
                """,
                (url, title, local_price, ebay_avg, markup_pct, int(alerted), now, now),
            )

    def recent_alert_count(self, hours: int = 24) -> int:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM seen_listings WHERE alerted = 1 AND first_seen >= ?",
                (cutoff,),
            ).fetchone()
            return row[0] if row else 0
