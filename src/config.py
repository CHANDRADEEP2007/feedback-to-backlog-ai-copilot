from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _secret(name: str, default: str = "") -> str:
    """Read environment first, then Streamlit secrets when available."""
    value = os.getenv(name)
    if value is not None:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:
        return default


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(_secret("DATABASE_PATH", "feedback_backlog.db"))
    dataset_path: Path = Path(
        _secret("DATASET_PATH", "data/aa_dataset-tickets-multi-lang-5-2-50-version.csv")
    )
    dedup_threshold: float = float(_secret("DEDUP_THRESHOLD", "85"))
    gemini_api_key: str = _secret("GEMINI_API_KEY")
    gemini_model: str = _secret("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_embedding_model: str = _secret("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    semantic_dedup_enabled: bool = _as_bool(_secret("SEMANTIC_DEDUP_ENABLED", "false"))
    semantic_dedup_threshold: float = float(_secret("SEMANTIC_DEDUP_THRESHOLD", "0.82"))
    gold_set_path: Path = Path(_secret("GOLD_SET_PATH", "eval/gold_set.csv"))
    jira_base_url: str = _secret("JIRA_BASE_URL").rstrip("/")
    jira_email: str = _secret("JIRA_EMAIL")
    jira_api_token: str = _secret("JIRA_API_TOKEN")
    jira_project_key: str = _secret("JIRA_PROJECT_KEY")
    jira_issue_type: str = _secret("JIRA_ISSUE_TYPE", "Task")

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def semantic_dedup_active(self) -> bool:
        return self.semantic_dedup_enabled and self.gemini_enabled

    @property
    def jira_enabled(self) -> bool:
        return all(
            [
                self.jira_base_url,
                self.jira_email,
                self.jira_api_token,
                self.jira_project_key,
            ]
        )
