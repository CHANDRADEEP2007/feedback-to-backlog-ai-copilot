from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BacklogDatabase:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS backlog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issue TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    reach REAL NOT NULL,
                    impact REAL NOT NULL,
                    confidence REAL NOT NULL,
                    effort REAL NOT NULL,
                    rice_score REAL NOT NULL,
                    score_explanation TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'Ready for review',
                    extraction_method TEXT NOT NULL,
                    jira_key TEXT,
                    jira_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backlog_id INTEGER NOT NULL REFERENCES backlog(id) ON DELETE CASCADE,
                    source_hash TEXT NOT NULL UNIQUE,
                    subject TEXT,
                    body TEXT,
                    language TEXT,
                    priority TEXT,
                    source_type TEXT,
                    raw_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS processing_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_hash TEXT,
                    subject TEXT,
                    error TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS score_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backlog_id INTEGER NOT NULL REFERENCES backlog(id) ON DELETE CASCADE,
                    reach REAL NOT NULL,
                    impact REAL NOT NULL,
                    confidence REAL NOT NULL,
                    effort REAL NOT NULL,
                    rice_score REAL NOT NULL,
                    reason TEXT NOT NULL,
                    batch_id TEXT,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jira_sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backlog_id INTEGER NOT NULL REFERENCES backlog(id) ON DELETE CASCADE,
                    batch_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    jira_key TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(feedback_sources)")
            }
            if "match_method" not in columns:
                connection.execute("ALTER TABLE feedback_sources ADD COLUMN match_method TEXT")
            if "match_similarity" not in columns:
                connection.execute("ALTER TABLE feedback_sources ADD COLUMN match_similarity REAL")
            connection.execute(
                """
                INSERT INTO score_history (
                    backlog_id, reach, impact, confidence, effort, rice_score,
                    reason, batch_id, recorded_at
                )
                SELECT b.id, b.reach, b.impact, b.confidence, b.effort, b.rice_score,
                       'migration snapshot', NULL, b.updated_at
                FROM backlog b
                WHERE NOT EXISTS (
                    SELECT 1 FROM score_history h WHERE h.backlog_id = b.id
                )
                """
            )

    @staticmethod
    def source_hash(row: Mapping[str, object]) -> str:
        raw = f"{row.get('subject', '')}\n{row.get('body', '')}".encode("utf-8", errors="replace")
        return hashlib.sha256(raw).hexdigest()

    def source_exists(self, source_hash: str) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM feedback_sources WHERE source_hash = ?", (source_hash,)
            ).fetchone() is not None

    def backlog_rows(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute("SELECT * FROM backlog ORDER BY rice_score DESC, id"))

    def source_rows(self, backlog_id: int | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM feedback_sources"
        params: tuple[object, ...] = ()
        if backlog_id is not None:
            sql += " WHERE backlog_id = ?"
            params = (backlog_id,)
        sql += " ORDER BY id DESC"
        with self.connect() as connection:
            return list(connection.execute(sql, params))

    def error_rows(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute("SELECT * FROM processing_errors ORDER BY id DESC"))

    def score_history_rows(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT h.*, b.issue
                    FROM score_history h JOIN backlog b ON b.id = h.backlog_id
                    ORDER BY h.recorded_at, h.id
                    """
                )
            )

    def jira_sync_rows(self, batch_id: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM jira_sync_history"
        params: tuple[object, ...] = ()
        if batch_id:
            sql += " WHERE batch_id = ?"
            params = (batch_id,)
        sql += " ORDER BY id DESC"
        with self.connect() as connection:
            return list(connection.execute(sql, params))

    def create_backlog_item(
        self, feedback, rice, row: Mapping[str, object], batch_id: str | None = None
    ) -> int:
        now = utc_now()
        source_hash = self.source_hash(row)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO backlog (
                    issue, category, source, reach, impact, confidence, effort,
                    rice_score, score_explanation, extraction_method, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.issue, feedback.category, feedback.source, rice.reach, rice.impact,
                    rice.confidence, rice.effort, rice.score, rice.explanation,
                    feedback.method, now, now,
                ),
            )
            backlog_id = int(cursor.lastrowid)
            self._insert_source(connection, backlog_id, source_hash, row, now)
            self._record_score(connection, backlog_id, rice, "created", batch_id, now)
            return backlog_id

    def add_duplicate_source(
        self, backlog_id: int, row: Mapping[str, object], rice, match,
        batch_id: str | None = None,
    ) -> None:
        now = utc_now()
        source_hash = self.source_hash(row)
        with self.connect() as connection:
            self._insert_source(
                connection, backlog_id, source_hash, row, now,
                match_method=match.method, match_similarity=match.similarity,
            )
            connection.execute(
                """
                UPDATE backlog
                SET occurrence_count = occurrence_count + 1,
                    reach = ?, impact = ?, confidence = ?, effort = ?, rice_score = ?,
                    score_explanation = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    rice.reach, rice.impact, rice.confidence, rice.effort, rice.score,
                    rice.explanation, now, backlog_id,
                ),
            )
            self._record_score(
                connection, backlog_id, rice, f"{match.method} duplicate merged", batch_id, now
            )

    @staticmethod
    def _insert_source(
        connection, backlog_id: int, source_hash: str, row, now: str,
        match_method: str | None = None, match_similarity: float | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO feedback_sources (
                backlog_id, source_hash, subject, body, language, priority,
                source_type, raw_payload, created_at, match_method, match_similarity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                backlog_id, source_hash, str(row.get("subject", "")), str(row.get("body", "")),
                str(row.get("language", "")), str(row.get("priority", "")),
                str(row.get("type", "")), json.dumps(dict(row), ensure_ascii=False, default=str), now,
                match_method, match_similarity,
            ),
        )

    @staticmethod
    def _record_score(connection, backlog_id: int, rice, reason: str, batch_id, now: str) -> None:
        connection.execute(
            """
            INSERT INTO score_history (
                backlog_id, reach, impact, confidence, effort, rice_score,
                reason, batch_id, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                backlog_id, rice.reach, rice.impact, rice.confidence, rice.effort,
                rice.score, reason, batch_id, now,
            ),
        )

    def update_score(self, backlog_id: int, rice) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE backlog SET reach=?, impact=?, confidence=?, effort=?, rice_score=?,
                    score_explanation=?, status='Reviewed', updated_at=? WHERE id=?
                """,
                (
                    rice.reach, rice.impact, rice.confidence, rice.effort, rice.score,
                    rice.explanation, now, backlog_id,
                ),
            )
            self._record_score(connection, backlog_id, rice, "manual review", None, now)

    def update_jira(self, backlog_id: int, key: str, url: str, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE backlog SET jira_key=?, jira_url=?, status=?, updated_at=? WHERE id=?",
                (key, url, status, utc_now(), backlog_id),
            )

    def log_jira_sync(
        self, backlog_id: int, batch_id: str, success: bool,
        jira_key: str | None = None, error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO jira_sync_history (
                    backlog_id, batch_id, success, jira_key, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (backlog_id, batch_id, int(success), jira_key, error, utc_now()),
            )

    def log_error(self, row: Mapping[str, object], error: Exception) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO processing_errors (source_hash, subject, error, created_at) VALUES (?, ?, ?, ?)",
                (self.source_hash(row), str(row.get("subject", "")), str(error), utc_now()),
            )
