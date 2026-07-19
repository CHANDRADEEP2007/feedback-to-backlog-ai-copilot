from __future__ import annotations

from dataclasses import dataclass


RERANK_CONFIDENCE_STEP = 0.05


@dataclass(frozen=True)
class RiceScore:
    reach: float
    impact: float
    confidence: float
    effort: float

    def __post_init__(self) -> None:
        if self.reach < 0:
            raise ValueError("Reach cannot be negative")
        if self.impact < 0:
            raise ValueError("Impact cannot be negative")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        if self.effort <= 0:
            raise ValueError("Effort must be greater than zero")

    @property
    def score(self) -> float:
        return round((self.reach * self.impact * self.confidence) / self.effort, 2)

    @property
    def explanation(self) -> str:
        return (
            f"({self.reach:g} reach × {self.impact:g} impact × "
            f"{self.confidence:.0%} confidence) ÷ {self.effort:g} effort = "
            f"{self.score:.2f}"
        )


def confidence_after_move(
    confidence: float,
    from_position: int,
    to_position: int,
    step: float = RERANK_CONFIDENCE_STEP,
) -> float:
    """Translate a rank move into the documented, bounded confidence change."""
    if step <= 0:
        raise ValueError("Confidence step must be greater than zero")
    positions_moved_up = from_position - to_position
    return round(min(1.0, max(0.0, confidence + positions_moved_up * step)), 4)


def initial_rice(priority: str, ticket_type: str, extraction_method: str) -> RiceScore:
    """Create a stable, documented first-pass score from source metadata."""
    priority_key = (priority or "medium").strip().lower()
    type_key = (ticket_type or "").strip().lower()

    impact = {"high": 3.0, "medium": 2.0, "low": 1.0}.get(priority_key, 1.5)
    reach = {"high": 5.0, "medium": 3.0, "low": 1.0}.get(priority_key, 2.0)
    if type_key == "incident":
        reach += 1.0
    confidence = 0.90 if extraction_method == "gemini" else 0.80
    effort = 2.0 if type_key in {"incident", "problem"} else 1.5
    return RiceScore(reach, impact, confidence, effort)
