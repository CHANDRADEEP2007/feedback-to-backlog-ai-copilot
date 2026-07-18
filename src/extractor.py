from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ExtractedFeedback:
    issue: str
    category: str
    source: str
    method: str


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _local_extract(row: Mapping[str, object]) -> ExtractedFeedback:
    subject = _clean(row.get("subject"))
    body = _clean(row.get("body"))
    issue = subject or re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0][:180]
    tags = [_clean(row.get(f"tag_{index}")) for index in range(1, 9)]
    category = next((tag for tag in tags if tag), "") or _clean(row.get("queue")) or "Other"
    source = f"Kaggle support ticket · {_clean(row.get('language')) or 'unknown language'}"
    return ExtractedFeedback(issue[:180], category[:80], source, "local")


def _parse_json(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    return json.loads(cleaned)


def extract_feedback(
    row: Mapping[str, object],
    api_key: str = "",
    model: str = "gemini-2.5-flash",
) -> ExtractedFeedback:
    if not api_key:
        return _local_extract(row)

    from google import genai

    client = genai.Client(api_key=api_key)
    base_context = f"""Subject: {_clean(row.get('subject'))}
Body: {_clean(row.get('body'))[:6000]}
Queue: {_clean(row.get('queue'))}
Type: {_clean(row.get('type'))}
Tags: {', '.join(_clean(row.get(f'tag_{i}')) for i in range(1, 9))}"""
    prompts = [
        """Extract one product-feedback item from this support ticket.
Return only strict JSON with string keys: issue, category, source.
Keep issue concise (max 180 characters), preserve meaning, and do not invent facts.
source must be 'Kaggle support ticket'.\n\n""" + base_context,
        """RETRY: The previous answer was invalid. Return exactly one JSON object and no markdown.
Required schema: {"issue":"non-empty string","category":"non-empty string","source":"Kaggle support ticket"}.
The issue must be at most 180 characters. Do not add keys or commentary.\n\n""" + base_context,
    ]
    last_error: Exception | None = None
    for prompt in prompts:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            payload = _parse_json(response.text or "")
            issue = _clean(payload.get("issue"))
            category = _clean(payload.get("category"))
            if not issue or not category:
                raise ValueError("Gemini response omitted a required field")
            return ExtractedFeedback(
                issue=issue[:180],
                category=category[:80],
                source=_clean(payload.get("source"))[:80] or "Kaggle support ticket",
                method="gemini",
            )
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            last_error = error
    raise ValueError(f"Gemini extraction failed after one retry: {last_error}")
