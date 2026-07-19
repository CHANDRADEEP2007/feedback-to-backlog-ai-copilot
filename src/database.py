from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Sequence

from .scoring import RiceScore, confidence_after_move


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
                CREATE TABLE IF NOT EXISTS priority_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backlog_id INTEGER NOT NULL REFERENCES backlog(id) ON DELETE CASCADE,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    from_position INTEGER,
                    to_position INTEGER,
                    old_confidence REAL NOT NULL,
                    new_confidence REAL NOT NULL,
                    old_rice_score REAL NOT NULL,
                    new_rice_score REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            backlog_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(backlog)")
            }
            baseline_columns = {
                "ai_reach": "REAL",
                "ai_impact": "REAL",
                "ai_confidence": "REAL",
                "ai_effort": "REAL",
                "manually_adjusted": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, column_type in baseline_columns.items():
                if name not in backlog_columns:
                    connection.execute(f"ALTER TABLE backlog ADD COLUMN {name} {column_type}")
            connection.execute(
                """
                UPDATE backlog SET
                    ai_reach = COALESCE(ai_reach, reach),
                    ai_impact = COALESCE(ai_impact, impact),
                    ai_confidence = COALESCE(ai_confidence, confidence),
                    ai_effort = COALESCE(ai_effort, effort)
                """
            )
            connection.execute(
                """
                UPDATE backlog SET
                    ai_reach = COALESCE((
                        SELECT h.reach FROM score_history h
                        WHERE h.backlog_id = backlog.id
                          AND h.reason NOT LIKE 'manual%'
                          AND h.reason NOT LIKE 'reset to AI%'
                        ORDER BY h.id DESC LIMIT 1
                    ), ai_reach, reach),
                    ai_impact = COALESCE((
                        SELECT h.impact FROM score_history h
                        WHERE h.backlog_id = backlog.id
                          AND h.reason NOT LIKE 'manual%'
                          AND h.reason NOT LIKE 'reset to AI%'
                        ORDER BY h.id DESC LIMIT 1
                    ), ai_impact, impact),
                    ai_confidence = COALESCE((
                        SELECT h.confidence FROM score_history h
                        WHERE h.backlog_id = backlog.id
                          AND h.reason NOT LIKE 'manual%'
                          AND h.reason NOT LIKE 'reset to AI%'
                        ORDER BY h.id DESC LIMIT 1
                    ), ai_confidence, confidence),
                    ai_effort = COALESCE((
                        SELECT h.effort FROM score_history h
                        WHERE h.backlog_id = backlog.id
                          AND h.reason NOT LIKE 'manual%'
                          AND h.reason NOT LIKE 'reset to AI%'
                        ORDER BY h.id DESC LIMIT 1
                    ), ai_effort, effort)
                """
            )
            connection.execute(
                """
                UPDATE backlog SET manually_adjusted = CASE
                    WHEN ABS(reach - ai_reach) > 0.000000001
                      OR ABS(impact - ai_impact) > 0.000000001
                      OR ABS(confidence - ai_confidence) > 0.000000001
                      OR ABS(effort - ai_effort) > 0.000000001
                    THEN 1 ELSE 0 END
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

    def priority_adjustment_rows(self, backlog_id: int | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM priority_adjustments"
        params: tuple[object, ...] = ()
        if backlog_id is not None:
            sql += " WHERE backlog_id = ?"
            params = (backlog_id,)
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
                    rice_score, score_explanation, extraction_method, created_at, updated_at,
                    ai_reach, ai_impact, ai_confidence, ai_effort, manually_adjusted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    feedback.issue, feedback.category, feedback.source, rice.reach, rice.impact,
                    rice.confidence, rice.effort, rice.score, rice.explanation,
                    feedback.method, now, now,
                    rice.reach, rice.impact, rice.confidence, rice.effort,
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
            previous = connection.execute(
                "SELECT * FROM backlog WHERE id = ?", (backlog_id,)
            ).fetchone()
            if previous is None:
                raise ValueError(f"Backlog item {backlog_id} does not exist")
            self._insert_source(
                connection, backlog_id, source_hash, row, now,
                match_method=match.method, match_similarity=match.similarity,
            )
            connection.execute(
                """
                UPDATE backlog
                SET occurrence_count = occurrence_count + 1,
                    reach = ?, impact = ?, confidence = ?, effort = ?, rice_score = ?,
                    score_explanation = ?, ai_reach = ?, ai_impact = ?,
                    ai_confidence = ?, ai_effort = ?, manually_adjusted = 0,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    rice.reach, rice.impact, rice.confidence, rice.effort, rice.score,
                    rice.explanation, rice.reach, rice.impact, rice.confidence,
                    rice.effort, now, backlog_id,
                ),
            )
            self._record_score(
                connection, backlog_id, rice, f"{match.method} duplicate merged", batch_id, now
            )
            if int(previous["manually_adjusted"]):
                self._record_adjustment(
                    connection, backlog_id, "Pipeline", "AI baseline refreshed",
                    None, None, float(previous["confidence"]), rice.confidence,
                    float(previous["rice_score"]), rice.score, now,
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

    def update_score(self, backlog_id: int, rice, actor: str = "Product manager") -> None:
        now = utc_now()
        with self.connect() as connection:
            previous = connection.execute(
                "SELECT * FROM backlog WHERE id = ?", (backlog_id,)
            ).fetchone()
            if previous is None:
                raise ValueError(f"Backlog item {backlog_id} does not exist")
            manually_adjusted = int(
                any(
                    abs(float(current) - float(baseline)) > 1e-9
                    for current, baseline in (
                        (rice.reach, previous["ai_reach"]),
                        (rice.impact, previous["ai_impact"]),
                        (rice.confidence, previous["ai_confidence"]),
                        (rice.effort, previous["ai_effort"]),
                    )
                )
            )
            connection.execute(
                """
                UPDATE backlog SET reach=?, impact=?, confidence=?, effort=?, rice_score=?,
                    score_explanation=?, manually_adjusted=?, status='Reviewed', updated_at=?
                WHERE id=?
                """,
                (
                    rice.reach, rice.impact, rice.confidence, rice.effort, rice.score,
                    rice.explanation, manually_adjusted, now, backlog_id,
                ),
            )
            self._record_score(
                connection, backlog_id, rice, f"manual review by {actor}", None, now
            )
            self._record_adjustment(
                connection, backlog_id, actor, "manual score edit", None, None,
                float(previous["confidence"]), rice.confidence,
                float(previous["rice_score"]), rice.score, now,
            )

    def apply_manual_reorder(
        self,
        ordered_ids: Sequence[int],
        actor: str,
    ) -> dict[str, int]:
        actor = actor.strip() or "Product manager"
        now = utc_now()
        with self.connect() as connection:
            rows = list(
                connection.execute("SELECT * FROM backlog ORDER BY rice_score DESC, id")
            )
            current_ids = [int(row["id"]) for row in rows]
            requested_ids = [int(item_id) for item_id in ordered_ids]
            if len(requested_ids) != len(set(requested_ids)):
                raise ValueError("Reordered backlog contains duplicate item IDs")
            if set(requested_ids) != set(current_ids):
                raise ValueError("Reordered backlog must contain every current item exactly once")

            current_positions = {item_id: index for index, item_id in enumerate(current_ids)}
            rows_by_id = {int(row["id"]): row for row in rows}
            projected: dict[int, RiceScore] = {}
            for new_position, backlog_id in enumerate(requested_ids):
                row = rows_by_id[backlog_id]
                projected[backlog_id] = RiceScore(
                    float(row["reach"]),
                    float(row["impact"]),
                    confidence_after_move(
                        float(row["confidence"]),
                        current_positions[backlog_id],
                        new_position,
                    ),
                    float(row["effort"]),
                )
            score_order = sorted(
                requested_ids,
                key=lambda item_id: (-projected[item_id].score, item_id),
            )
            if score_order != requested_ids:
                raise ValueError(
                    "That order cannot be represented by the fixed Confidence rule. "
                    "No scores were changed."
                )

            changed = 0
            capped = 0
            for new_position, backlog_id in enumerate(requested_ids):
                old_position = current_positions[backlog_id]
                if old_position == new_position:
                    continue
                row = rows_by_id[backlog_id]
                old_confidence = float(row["confidence"])
                new_confidence = confidence_after_move(
                    old_confidence, old_position, new_position
                )
                expected = old_confidence + (old_position - new_position) * 0.05
                if new_confidence != round(expected, 4):
                    capped += 1
                rice = projected[backlog_id]
                connection.execute(
                    """
                    UPDATE backlog SET confidence=?, rice_score=?, score_explanation=?,
                        manually_adjusted=?, status='Reviewed', updated_at=? WHERE id=?
                    """,
                    (
                        rice.confidence, rice.score, rice.explanation,
                        int(abs(rice.confidence - float(row["ai_confidence"])) > 1e-9),
                        now, backlog_id,
                    ),
                )
                self._record_score(
                    connection, backlog_id, rice,
                    f"manual reorder {old_position + 1}->{new_position + 1} by {actor}",
                    None, now,
                )
                self._record_adjustment(
                    connection, backlog_id, actor, "manual reorder",
                    old_position + 1, new_position + 1, old_confidence,
                    rice.confidence, float(row["rice_score"]), rice.score, now,
                )
                changed += 1
            return {"changed": changed, "capped": capped}

    def reset_to_ai_score(self, backlog_id: int, actor: str) -> None:
        actor = actor.strip() or "Product manager"
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM backlog WHERE id = ?", (backlog_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Backlog item {backlog_id} does not exist")
            rice = RiceScore(
                float(row["ai_reach"]), float(row["ai_impact"]),
                float(row["ai_confidence"]), float(row["ai_effort"]),
            )
            connection.execute(
                """
                UPDATE backlog SET reach=?, impact=?, confidence=?, effort=?, rice_score=?,
                    score_explanation=?, manually_adjusted=0, status='Reviewed', updated_at=?
                WHERE id=?
                """,
                (
                    rice.reach, rice.impact, rice.confidence, rice.effort,
                    rice.score, rice.explanation, now, backlog_id,
                ),
            )
            self._record_score(
                connection, backlog_id, rice, f"reset to AI score by {actor}", None, now
            )
            self._record_adjustment(
                connection, backlog_id, actor, "reset to AI score", None, None,
                float(row["confidence"]), rice.confidence,
                float(row["rice_score"]), rice.score, now,
            )

    @staticmethod
    def _record_adjustment(
        connection, backlog_id: int, actor: str, action: str,
        from_position: int | None, to_position: int | None,
        old_confidence: float, new_confidence: float,
        old_rice_score: float, new_rice_score: float, now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO priority_adjustments (
                backlog_id, actor, action, from_position, to_position,
                old_confidence, new_confidence, old_rice_score,
                new_rice_score, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                backlog_id, actor, action, from_position, to_position,
                old_confidence, new_confidence, old_rice_score,
                new_rice_score, now,
            ),
        )

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
