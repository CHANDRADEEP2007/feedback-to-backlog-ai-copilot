from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping
from uuid import uuid4

from .dedup import find_duplicate, find_semantic_duplicate
from .extractor import extract_feedback
from .scoring import RiceScore, initial_rice


@dataclass
class BatchResult:
    processed: int = 0
    created: int = 0
    duplicates: int = 0
    skipped: int = 0
    errors: int = 0


def process_row(
    row: Mapping[str, object], db, settings, batch_id: str | None = None
) -> str:
    source_hash = db.source_hash(row)
    if db.source_exists(source_hash):
        return "skipped"

    feedback = extract_feedback(row, settings.gemini_api_key, settings.gemini_model)
    backlog = [dict(item) for item in db.backlog_rows()]
    match = find_duplicate(feedback.issue, backlog, settings.dedup_threshold)
    if not match and settings.semantic_dedup_active:
        match = find_semantic_duplicate(
            feedback.issue,
            backlog,
            settings.gemini_api_key,
            settings.gemini_embedding_model,
            settings.semantic_dedup_threshold,
        )
    base = initial_rice(str(row.get("priority", "")), str(row.get("type", "")), feedback.method)

    if match:
        existing = next(item for item in backlog if int(item["id"]) == match.backlog_id)
        baseline_reach = float(existing.get("ai_reach") or existing["reach"])
        baseline_impact = float(existing.get("ai_impact") or existing["impact"])
        baseline_confidence = float(existing.get("ai_confidence") or existing["confidence"])
        baseline_effort = float(existing.get("ai_effort") or existing["effort"])
        reach = max(baseline_reach + 1.0, base.reach)
        rice = RiceScore(
            reach=reach,
            impact=max(baseline_impact, base.impact),
            confidence=max(baseline_confidence, base.confidence),
            effort=baseline_effort,
        )
        db.add_duplicate_source(match.backlog_id, row, rice, match, batch_id)
        return "duplicate"

    db.create_backlog_item(feedback, base, row, batch_id)
    return "created"


def process_batch(rows: Iterable[Mapping[str, object]], db, settings, progress=None) -> BatchResult:
    rows = list(rows)
    result = BatchResult()
    batch_id = str(uuid4())
    for index, row in enumerate(rows, start=1):
        try:
            outcome = process_row(row, db, settings, batch_id)
            setattr(result, outcome if outcome != "duplicate" else "duplicates", getattr(result, outcome if outcome != "duplicate" else "duplicates") + 1)
        except Exception as error:
            db.log_error(row, error)
            result.errors += 1
        result.processed += 1
        if progress:
            progress(index / max(len(rows), 1), f"Processed {index} of {len(rows)}")
    return result
