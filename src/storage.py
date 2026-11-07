"""SQLite persistence and duplicate protection for source-monitor."""
from __future__ import annotations

import sqlite3
from pathlib import Path


class SourceStore:
    def __init__(self, database_path: str = "data/source_monitor.sqlite3") -> None:
        self.path = database_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS source_posts (
                    source_chat TEXT NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    asin TEXT,
                    status TEXT NOT NULL DEFAULT 'seen',
                    telegram_message_id TEXT,
                    facebook_post_id TEXT,
                    failure_reason TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source_chat, source_message_id)
                )
            """)
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_source_posts_asin_active "
                "ON source_posts(asin) WHERE asin IS NOT NULL "
                "AND status IN ('processing', 'posted')"
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def already_seen(self, source_chat: str, message_id: int) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM source_posts WHERE source_chat=? AND source_message_id=?",
                (source_chat, message_id),
            ).fetchone()
        return row is not None

    def claim(self, source_chat: str, message_id: int, asin: str | None) -> bool:
        """Atomically claim a message and reserve its ASIN against concurrent duplicates."""
        try:
            with self._connect() as db:
                cursor = db.execute(
                    """INSERT OR IGNORE INTO source_posts
                       (source_chat, source_message_id, asin, status)
                       VALUES (?, ?, ?, 'processing')""",
                    (source_chat, message_id, asin),
                )
                return cursor.rowcount == 1
        except sqlite3.IntegrityError:
            return False

    def mark_posted(
        self, source_chat: str, message_id: int,
        telegram_message_id: str | None, facebook_post_id: str | None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """UPDATE source_posts SET status='posted',
                   telegram_message_id=?, facebook_post_id=?, failure_reason=NULL,
                   updated_at=CURRENT_TIMESTAMP
                   WHERE source_chat=? AND source_message_id=?""",
                (telegram_message_id, facebook_post_id, source_chat, message_id),
            )

    def mark_failed(self, source_chat: str, message_id: int, reason: str) -> None:
        safe_reason = (reason or "Publishing failed")[:300]
        with self._connect() as db:
            db.execute(
                """UPDATE source_posts SET status='failed', failure_reason=?,
                   updated_at=CURRENT_TIMESTAMP
                   WHERE source_chat=? AND source_message_id=?""",
                (safe_reason, source_chat, message_id),
            )

    def asin_was_posted(self, asin: str) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM source_posts WHERE asin=? AND status='posted' LIMIT 1",
                (asin,),
            ).fetchone()
        return row is not None
