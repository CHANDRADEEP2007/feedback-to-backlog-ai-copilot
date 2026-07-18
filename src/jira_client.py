from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import requests


@dataclass(frozen=True)
class JiraResult:
    key: str
    url: str


@dataclass(frozen=True)
class BulkSyncResult:
    batch_id: str
    attempted: int
    succeeded: int
    failed: int


class JiraClient:
    def __init__(self, settings):
        self.settings = settings

    def _description(self, item: dict[str, object]) -> dict[str, object]:
        text = (
            f"Category: {item['category']}\n"
            f"RICE score: {item['rice_score']:.2f}\n"
            f"Formula: {item['score_explanation']}\n"
            f"Feedback occurrences: {item['occurrence_count']}\n"
            f"Source: {item['source']}"
        )
        return {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        }

    def sync(self, item: dict[str, object]) -> JiraResult:
        auth = (self.settings.jira_email, self.settings.jira_api_token)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        fields = {
            "summary": str(item["issue"])[:255],
            "description": self._description(item),
        }
        if item.get("jira_key"):
            key = str(item["jira_key"])
            response = requests.put(
                f"{self.settings.jira_base_url}/rest/api/3/issue/{key}",
                json={"fields": fields}, auth=auth, headers=headers, timeout=30,
            )
            response.raise_for_status()
        else:
            fields.update(
                {
                    "project": {"key": self.settings.jira_project_key},
                    "issuetype": {"name": self.settings.jira_issue_type},
                }
            )
            response = requests.post(
                f"{self.settings.jira_base_url}/rest/api/3/issue",
                json={"fields": fields}, auth=auth, headers=headers, timeout=30,
            )
            response.raise_for_status()
            key = str(response.json()["key"])
        return JiraResult(key, f"{self.settings.jira_base_url}/browse/{key}")


def sync_reviewed_items(db, settings, progress=None) -> BulkSyncResult:
    """Sync reviewed items independently so one Jira failure never stops the batch."""
    items = [dict(row) for row in db.backlog_rows() if row["status"] == "Reviewed"]
    batch_id = str(uuid4())
    succeeded = 0
    client = JiraClient(settings)
    for index, item in enumerate(items, start=1):
        try:
            result = client.sync(item)
            db.update_jira(int(item["id"]), result.key, result.url, "Synced to Jira")
            db.log_jira_sync(int(item["id"]), batch_id, True, jira_key=result.key)
            succeeded += 1
        except Exception as error:
            db.log_jira_sync(int(item["id"]), batch_id, False, error=str(error))
        if progress:
            progress(index / max(len(items), 1), f"Synced {index} of {len(items)}")
    return BulkSyncResult(batch_id, len(items), succeeded, len(items) - succeeded)
