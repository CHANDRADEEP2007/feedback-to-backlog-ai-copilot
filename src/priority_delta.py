from __future__ import annotations

import pandas as pd


PRIORITY_DELTA_COLUMNS = [
    "backlog_id",
    "issue",
    "previous_score",
    "current_score",
    "delta",
    "reason",
    "direction",
]

CURRENT_PRIORITY_COLUMNS = [
    "backlog_id",
    "issue",
    "current_score",
    "reach",
    "impact",
    "confidence",
    "effort",
    "status",
]


def priority_insight_mode(
    priority_delta: pd.DataFrame,
    minimum_delta_items: int = 2,
) -> str:
    """Choose the comparative delta view only when it has enough context."""
    return "delta" if len(priority_delta) >= minimum_delta_items else "current"


def build_current_priority_frame(
    backlog: pd.DataFrame,
    limit: int = 5,
) -> pd.DataFrame:
    """Return the highest-scoring current backlog items for the fallback view."""
    required = {
        "id",
        "issue",
        "rice_score",
        "reach",
        "impact",
        "confidence",
        "effort",
        "status",
    }
    if backlog.empty or not required.issubset(backlog.columns) or limit < 1:
        return pd.DataFrame(columns=CURRENT_PRIORITY_COLUMNS)

    current = backlog[list(required)].copy().rename(
        columns={"id": "backlog_id", "rice_score": "current_score"}
    )
    score_columns = [
        "current_score",
        "reach",
        "impact",
        "confidence",
        "effort",
    ]
    for column in score_columns:
        current[column] = pd.to_numeric(current[column], errors="coerce")
    current = current.dropna(subset=["backlog_id", "issue", "current_score"])
    current = current.sort_values(
        ["current_score", "issue"], ascending=[False, True]
    ).head(limit)
    return current[CURRENT_PRIORITY_COLUMNS].reset_index(drop=True)


def build_priority_delta_frame(
    backlog: pd.DataFrame,
    history: pd.DataFrame,
    limit: int = 5,
) -> pd.DataFrame:
    """Return latest-vs-previous score changes for the top reviewed items."""
    required_backlog = {"id", "issue", "rice_score", "status"}
    required_history = {"backlog_id", "rice_score", "reason", "recorded_at"}
    if (
        backlog.empty
        or history.empty
        or not required_backlog.issubset(backlog.columns)
        or not required_history.issubset(history.columns)
        or limit < 1
    ):
        return pd.DataFrame(columns=PRIORITY_DELTA_COLUMNS)

    reviewed = backlog[
        backlog["status"].astype(str).str.strip().str.casefold().eq("reviewed")
    ].copy()
    reviewed["rice_score"] = pd.to_numeric(reviewed["rice_score"], errors="coerce")
    reviewed = reviewed.dropna(subset=["id", "rice_score"])

    ordered_history = history.copy()
    ordered_history["rice_score"] = pd.to_numeric(
        ordered_history["rice_score"], errors="coerce"
    )
    ordered_history["recorded_at"] = pd.to_datetime(
        ordered_history["recorded_at"], errors="coerce", utc=True
    )
    ordered_history = ordered_history.dropna(subset=["backlog_id", "rice_score"])
    sort_columns = ["backlog_id", "recorded_at"]
    if "id" in ordered_history.columns:
        sort_columns.append("id")
    ordered_history = ordered_history.sort_values(sort_columns, na_position="first")

    snapshot_counts = ordered_history.groupby("backlog_id").size()
    eligible_ids = snapshot_counts[snapshot_counts >= 2].index
    candidates = reviewed[reviewed["id"].isin(eligible_ids)].sort_values(
        ["rice_score", "issue"], ascending=[False, True]
    ).head(limit)

    changes: list[dict[str, object]] = []
    for candidate in candidates.itertuples(index=False):
        snapshots = ordered_history[ordered_history["backlog_id"] == candidate.id]
        previous = float(snapshots.iloc[-2]["rice_score"])
        current = float(snapshots.iloc[-1]["rice_score"])
        delta = current - previous
        if delta > 1e-9:
            direction = "up"
        elif delta < -1e-9:
            direction = "down"
        else:
            direction = "flat"
        reason_value = snapshots.iloc[-1]["reason"]
        reason = (
            str(reason_value).strip() if pd.notna(reason_value) else ""
        ) or "Not recorded"
        changes.append(
            {
                "backlog_id": int(candidate.id),
                "issue": str(candidate.issue),
                "previous_score": previous,
                "current_score": current,
                "delta": delta,
                "reason": reason,
                "direction": direction,
            }
        )

    if not changes:
        return pd.DataFrame(columns=PRIORITY_DELTA_COLUMNS)

    result = pd.DataFrame(changes, columns=PRIORITY_DELTA_COLUMNS)
    result["absolute_delta"] = result["delta"].abs()
    result = result.sort_values(
        ["absolute_delta", "current_score", "issue"],
        ascending=[False, False, True],
    ).drop(columns="absolute_delta")
    return result.reset_index(drop=True)
