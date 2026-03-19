import sqlite3
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = "data/signals.db"

CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                author TEXT,
                subreddit TEXT,
                posted_at DATETIME,
                scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                matched BOOLEAN DEFAULT FALSE,
                service_match TEXT,
                client_tier TEXT,
                confidence TEXT,
                reasoning TEXT,
                suggested_reply TEXT,
                included_in_report BOOLEAN DEFAULT FALSE,
                actioned BOOLEAN DEFAULT FALSE,
                UNIQUE(platform, external_id)
            )
        """)
        # Migrate existing DBs that predate the suggested_reply column
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN suggested_reply TEXT")
        except Exception:
            pass  # Column already exists
        conn.commit()

    # Remove signals from retired subreddits
    delete_signals_by_subreddit("cscareerquestions")


def delete_signals_by_subreddit(subreddit: str) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM signals WHERE subreddit = ?",
            (subreddit,),
        )
        conn.commit()
    if cursor.rowcount:
        logger.info("[db] Deleted %d signals from r/%s", cursor.rowcount, subreddit)
    return cursor.rowcount


def save_signals(signals: list[dict]) -> int:
    if not signals:
        return 0

    rows = [
        (
            s["id"],
            s["platform"],
            s["external_id"],
            s["url"],
            s["title"],
            s.get("body"),
            s.get("author"),
            s.get("subreddit"),
            s.get("posted_at"),
        )
        for s in signals
    ]

    with _connect() as conn:
        cursor = conn.executemany(
            """
            INSERT OR IGNORE INTO signals
                (id, platform, external_id, url, title, body, author, subreddit, posted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        inserted = cursor.rowcount

    skipped = len(signals) - inserted
    logger.info("[db] Saved %d new signals (skipped %d duplicates)", inserted, skipped)
    return inserted


def get_unmatched(limit: int = 200) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM signals
            WHERE matched = FALSE
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_match_result(
    id: str,
    matched: bool,
    service_match: str,
    client_tier: str,
    confidence: str,
    reasoning: str,
    suggested_reply: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE signals
            SET matched = ?, service_match = ?, client_tier = ?, confidence = ?,
                reasoning = ?, suggested_reply = ?
            WHERE id = ?
            """,
            (matched, service_match, client_tier, confidence, reasoning, suggested_reply, id),
        )
        conn.commit()


def get_matched_without_reply(limit: int = 500) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM signals
            WHERE matched = TRUE AND (suggested_reply IS NULL OR suggested_reply = '')
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_suggested_reply(id: str, suggested_reply: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE signals SET suggested_reply = ? WHERE id = ?",
            (suggested_reply, id),
        )
        conn.commit()


def get_report_candidates() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM signals
            WHERE matched = TRUE AND included_in_report = FALSE
            """
        ).fetchall()
    results = [dict(r) for r in rows]
    results.sort(key=lambda r: CONFIDENCE_ORDER.get(r.get("confidence") or "", 99))
    return results


def mark_included_in_report(ids: list[str]) -> None:
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with _connect() as conn:
        conn.execute(
            f"UPDATE signals SET included_in_report = TRUE WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    logger.info("Database initialized at %s", DB_PATH)
