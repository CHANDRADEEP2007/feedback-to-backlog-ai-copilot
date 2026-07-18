from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

from .dedup import find_duplicate, find_semantic_duplicate, normalize
from .extractor import extract_feedback


@dataclass(frozen=True)
class ClassificationMetrics:
    precision: float
    recall: float
    true_positives: int
    false_positives: int
    false_negatives: int


def _ratio(numerator: int, denominator: int, empty: float = 0.0) -> float:
    return numerator / denominator if denominator else empty


def _evaluate_dedup(rows: list[dict[str, object]], matcher) -> ClassificationMetrics:
    representatives: list[dict[str, object]] = []
    seen_groups: set[str] = set()
    tp = fp = fn = 0
    for index, row in enumerate(rows, start=1):
        group = str(row["duplicate_group"])
        actual_duplicate = group in seen_groups
        match = matcher(str(row["expected_issue"]), representatives)
        predicted_duplicate = match is not None
        if predicted_duplicate and actual_duplicate:
            tp += 1
        elif predicted_duplicate and not actual_duplicate:
            fp += 1
        elif actual_duplicate and not predicted_duplicate:
            fn += 1
        if not predicted_duplicate:
            representatives.append({"id": index, "issue": str(row["expected_issue"])})
        seen_groups.add(group)
    return ClassificationMetrics(
        precision=_ratio(tp, tp + fp, empty=1.0),
        recall=_ratio(tp, tp + fn),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
    )


def run_evaluation(settings, use_gemini: bool = False) -> dict[str, object]:
    data = pd.read_csv(settings.gold_set_path).fillna("")
    rows = data.to_dict("records")
    correct = 0
    extraction_details = []
    for row in rows:
        extracted = extract_feedback(
            row,
            settings.gemini_api_key if use_gemini else "",
            settings.gemini_model,
        )
        issue_similarity = fuzz.token_set_ratio(
            normalize(extracted.issue), normalize(str(row["expected_issue"]))
        )
        category_correct = normalize(extracted.category) == normalize(str(row["expected_category"]))
        item_correct = issue_similarity >= 75 and category_correct
        correct += int(item_correct)
        extraction_details.append(
            {
                "subject": row["subject"],
                "issue_similarity": round(issue_similarity, 2),
                "category_correct": category_correct,
                "correct": item_correct,
            }
        )

    baseline = _evaluate_dedup(
        rows,
        lambda issue, backlog: find_duplicate(issue, backlog, settings.dedup_threshold),
    )
    semantic_active = settings.semantic_dedup_active

    def hybrid_matcher(issue, backlog):
        return find_duplicate(issue, backlog, settings.dedup_threshold) or find_semantic_duplicate(
            issue,
            backlog,
            settings.gemini_api_key if semantic_active else "",
            settings.gemini_embedding_model,
            settings.semantic_dedup_threshold,
        )

    hybrid = _evaluate_dedup(rows, hybrid_matcher) if semantic_active else baseline
    result = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gold_set_size": len(rows),
        "extraction_method": "gemini" if use_gemini else "local fallback",
        "extraction_accuracy": _ratio(correct, len(rows)),
        "extraction_correct": correct,
        "baseline_dedup": asdict(baseline),
        "hybrid_dedup": asdict(hybrid),
        "semantic_active": semantic_active,
        "semantic_recall_delta": hybrid.recall - baseline.recall if semantic_active else None,
        "extraction_details": extraction_details,
    }
    return result


def save_results(result: dict[str, object], path: Path | str = "eval/results.json") -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")


def load_results(path: Path | str = "eval/results.json") -> dict[str, object] | None:
    source = Path(path)
    if not source.exists():
        return None
    return json.loads(source.read_text(encoding="utf-8"))
