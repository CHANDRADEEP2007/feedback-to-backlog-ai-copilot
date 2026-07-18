from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from rapidfuzz import fuzz


@dataclass(frozen=True)
class DuplicateMatch:
    backlog_id: int
    issue: str
    similarity: float
    method: str = "rapidfuzz"


def normalize(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (text or "").lower(), flags=re.UNICODE)
    return " ".join(text.split())


def find_duplicate(
    issue: str,
    backlog: Iterable[Mapping[str, object]],
    threshold: float = 85,
) -> DuplicateMatch | None:
    candidate = normalize(issue)
    best: DuplicateMatch | None = None
    for row in backlog:
        similarity = float(fuzz.token_set_ratio(candidate, normalize(str(row["issue"]))))
        if similarity >= threshold and (best is None or similarity > best.similarity):
            best = DuplicateMatch(int(row["id"]), str(row["issue"]), similarity, "rapidfuzz")
    return best


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def find_semantic_duplicate(
    issue: str,
    backlog: Iterable[Mapping[str, object]],
    api_key: str,
    model: str = "gemini-embedding-001",
    threshold: float = 0.82,
    embedder=None,
) -> DuplicateMatch | None:
    """Second-pass semantic match. Returns None safely when it cannot run."""
    rows = list(backlog)
    if not api_key or not rows:
        return None
    texts = [issue, *(str(row["issue"]) for row in rows)]
    try:
        if embedder is None:
            from google import genai
            from google.genai import types

            result = genai.Client(api_key=api_key).models.embed_content(
                model=model,
                contents=texts,
                config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"),
            )
            vectors = [embedding.values for embedding in result.embeddings]
        else:
            vectors = embedder(texts)
        candidate = vectors[0]
        best: DuplicateMatch | None = None
        for row, vector in zip(rows, vectors[1:]):
            similarity = cosine_similarity(candidate, vector)
            if similarity >= threshold and (best is None or similarity > best.similarity):
                best = DuplicateMatch(
                    int(row["id"]), str(row["issue"]), round(similarity * 100, 2), "semantic"
                )
        return best
    except Exception:
        return None
