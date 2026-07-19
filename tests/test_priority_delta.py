import pandas as pd

from src.priority_delta import build_priority_delta_frame


def test_priority_delta_uses_latest_two_snapshots_and_sorts_by_movement() -> None:
    backlog = pd.DataFrame(
        [
            {"id": 1, "issue": "Large increase", "rice_score": 9.0, "status": "Reviewed"},
            {"id": 2, "issue": "Small decrease", "rice_score": 8.0, "status": "Reviewed"},
            {"id": 3, "issue": "Not reviewed", "rice_score": 20.0, "status": "Ready for review"},
        ]
    )
    history = pd.DataFrame(
        [
            {"id": 1, "backlog_id": 1, "rice_score": 5.0, "reason": "created", "recorded_at": "2026-07-19T10:00:00Z"},
            {"id": 2, "backlog_id": 1, "rice_score": 6.0, "reason": "first merge", "recorded_at": "2026-07-19T11:00:00Z"},
            {"id": 3, "backlog_id": 1, "rice_score": 9.0, "reason": "manual review", "recorded_at": "2026-07-19T12:00:00Z"},
            {"id": 4, "backlog_id": 2, "rice_score": 9.0, "reason": "created", "recorded_at": "2026-07-19T10:00:00Z"},
            {"id": 5, "backlog_id": 2, "rice_score": 8.0, "reason": "manual review", "recorded_at": "2026-07-19T12:00:00Z"},
            {"id": 6, "backlog_id": 3, "rice_score": 10.0, "reason": "created", "recorded_at": "2026-07-19T10:00:00Z"},
            {"id": 7, "backlog_id": 3, "rice_score": 20.0, "reason": "merge", "recorded_at": "2026-07-19T12:00:00Z"},
        ]
    )

    result = build_priority_delta_frame(backlog, history)

    assert result["issue"].tolist() == ["Large increase", "Small decrease"]
    assert result["previous_score"].tolist() == [6.0, 9.0]
    assert result["current_score"].tolist() == [9.0, 8.0]
    assert result["delta"].tolist() == [3.0, -1.0]
    assert result["direction"].tolist() == ["up", "down"]
    assert result["reason"].tolist() == ["manual review", "manual review"]


def test_priority_delta_requires_a_previous_snapshot() -> None:
    backlog = pd.DataFrame(
        [{"id": 1, "issue": "Initial only", "rice_score": 5.0, "status": "Reviewed"}]
    )
    history = pd.DataFrame(
        [
            {
                "id": 1,
                "backlog_id": 1,
                "rice_score": 5.0,
                "reason": "created",
                "recorded_at": "2026-07-19T10:00:00Z",
            }
        ]
    )

    result = build_priority_delta_frame(backlog, history)

    assert result.empty


def test_priority_delta_includes_flat_changes() -> None:
    backlog = pd.DataFrame(
        [{"id": 1, "issue": "No movement", "rice_score": 5.0, "status": "Reviewed"}]
    )
    history = pd.DataFrame(
        [
            {"id": 1, "backlog_id": 1, "rice_score": 5.0, "reason": "created", "recorded_at": "2026-07-19T10:00:00Z"},
            {"id": 2, "backlog_id": 1, "rice_score": 5.0, "reason": "reviewed", "recorded_at": "2026-07-19T11:00:00Z"},
        ]
    )

    result = build_priority_delta_frame(backlog, history)

    assert result.iloc[0]["direction"] == "flat"
    assert result.iloc[0]["delta"] == 0.0
