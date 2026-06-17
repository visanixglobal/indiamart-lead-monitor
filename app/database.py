"""
SQLite persistence layer.
All DB interaction goes through this module.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Generator, List, Optional

from app.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "leads.db"


def _ensure_data_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    _ensure_data_dir()
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id     TEXT    UNIQUE NOT NULL,
                product_name TEXT,
                category    TEXT,
                quantity    TEXT,
                buyer_city  TEXT,
                buyer_state TEXT,
                buyer_country TEXT,
                lead_value  TEXT,
                enrichment_value TEXT,
                credits_needed TEXT,
                purchase_status TEXT,
                buyer_name  TEXT,
                raw_json    TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Index on created_at for date-range queries
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_created_at ON lead_history (created_at)"
        )
    logger.info("Database initialised at %s", DB_PATH)


def lead_exists(lead_id: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM lead_history WHERE lead_id = ?", (lead_id,)
        ).fetchone()
    return row is not None


def insert_lead(
    lead_id: str,
    product_name: str,
    quantity: str,
    buyer_city: str,
    buyer_state: str,
    buyer_country: str,
    lead_value: str,
    raw_json: dict,
    category: str = "",
    enrichment_value: str = "",
    credits_needed: str = "",
    purchase_status: str = "",
    buyer_name: str = "",
) -> bool:
    """
    Insert a lead.  Returns True if inserted, False if it already existed.
    """
    try:
        with _conn() as con:
            con.execute(
                """
                INSERT INTO lead_history
                    (lead_id, product_name, category, quantity, buyer_city, buyer_state,
                     buyer_country, lead_value, enrichment_value, credits_needed,
                     purchase_status, buyer_name, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    product_name,
                    category,
                    quantity,
                    buyer_city,
                    buyer_state,
                    buyer_country,
                    lead_value,
                    enrichment_value,
                    credits_needed,
                    purchase_status,
                    buyer_name,
                    json.dumps(raw_json, ensure_ascii=False),
                ),
            )
        logger.debug("Inserted lead %s", lead_id)
        return True
    except sqlite3.IntegrityError:
        return False


def get_latest_leads(limit: int = 50) -> List[dict]:
    with _conn() as con:
        rows = con.execute(
            """
            SELECT id, lead_id, product_name, category, quantity,
                   buyer_city, buyer_state, buyer_country,
                   lead_value, enrichment_value, credits_needed,
                   purchase_status, buyer_name, created_at
            FROM lead_history
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    today = date.today().isoformat()
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM lead_history").fetchone()[0]
        today_count = con.execute(
            "SELECT COUNT(*) FROM lead_history WHERE DATE(created_at) = ?",
            (today,),
        ).fetchone()[0]
    return {"total_leads": total, "today_leads": today_count}
