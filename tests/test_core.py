from types import SimpleNamespace

from src.database import BacklogDatabase
from src.dedup import find_duplicate, find_semantic_duplicate
from src.evaluation import run_evaluation
from src.extractor import ExtractedFeedback, extract_feedback
from src.jira_client import JiraClient, JiraResult, sync_reviewed_items
from src.scoring import RiceScore, initial_rice


def test_rice_formula_is_traceable_and_stable():
    rice = RiceScore(reach=10, impact=3, confidence=0.8, effort=2)
    assert rice.score == 12.0
    assert "80% confidence" in rice.explanation


def test_initial_rice_is_deterministic():
    assert initial_rice("high", "Incident", "local") == initial_rice("high", "Incident", "local")


def test_dedup_finds_similar_wording():
    backlog = [{"id": 7, "issue": "Account management portal is offline"}]
    match = find_duplicate("The account management portal is offline", backlog, threshold=85)
    assert match is not None
    assert match.backlog_id == 7


def test_dedup_rejects_unrelated_issue():
    backlog = [{"id": 7, "issue": "Account management portal is offline"}]
    assert find_duplicate("Need a refund for duplicate charge", backlog, threshold=85) is None


def test_semantic_second_pass_accepts_injected_embeddings():
    backlog = [{"id": 9, "issue": "Unable to sign in with new credentials"}]

    def embedder(_texts):
        return [[1.0, 0.0], [0.99, 0.01]]

    match = find_semantic_duplicate(
        "Login fails after changing password", backlog, "test-key", threshold=0.9, embedder=embedder
    )
    assert match is not None
    assert match.method == "semantic"
    assert match.similarity > 99


def test_database_records_score_history_and_merge_evidence(tmp_path):
    db = BacklogDatabase(tmp_path / "test.db")
    rice = RiceScore(3, 2, 0.8, 2)
    feedback = ExtractedFeedback("Account portal offline", "Account", "Test", "local")
    first = {"subject": "Account portal offline", "body": "Cannot load it", "type": "Incident"}
    backlog_id = db.create_backlog_item(feedback, rice, first, "batch-one")
    match = find_duplicate("Account portal is offline", [dict(db.backlog_rows()[0])], 85)
    second = {"subject": "Account portal is offline", "body": "Still down", "type": "Incident"}
    db.add_duplicate_source(backlog_id, second, RiceScore(4, 2, 0.8, 2), match, "batch-two")
    assert len(db.score_history_rows()) == 2
    merged_source = dict(db.source_rows(backlog_id)[0])
    assert merged_source["match_method"] == "rapidfuzz"
    assert merged_source["match_similarity"] >= 85


def test_gold_set_evaluation_is_measured_from_40_labels():
    settings = SimpleNamespace(
        gold_set_path="eval/gold_set.csv",
        gemini_api_key="",
        gemini_model="gemini-2.5-flash",
        dedup_threshold=85,
        semantic_dedup_active=False,
        gemini_embedding_model="gemini-embedding-001",
        semantic_dedup_threshold=0.82,
    )
    result = run_evaluation(settings)
    assert result["gold_set_size"] == 40
    assert result["extraction_accuracy"] >= 0.85
    assert result["baseline_dedup"]["precision"] >= 0.80


def test_gemini_extraction_retries_once(monkeypatch):
    from google import genai

    class Models:
        def __init__(self):
            self.calls = 0

        def generate_content(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(text="not json")
            return SimpleNamespace(
                text='{"issue":"Login fails","category":"Account","source":"Kaggle support ticket"}'
            )

    models = Models()
    monkeypatch.setattr(genai, "Client", lambda api_key: SimpleNamespace(models=models))
    result = extract_feedback({"subject": "Login fails", "body": "Cannot sign in"}, "fake-key")
    assert result.issue == "Login fails"
    assert models.calls == 2


def test_bulk_jira_sync_isolates_item_failures(tmp_path, monkeypatch):
    db = BacklogDatabase(tmp_path / "jira.db")
    rice = RiceScore(3, 2, 0.8, 2)
    for index in range(2):
        feedback = ExtractedFeedback(f"Issue {index}", "Test", "Test", "local")
        backlog_id = db.create_backlog_item(
            feedback, rice, {"subject": f"Issue {index}", "body": "Body"}
        )
        db.update_score(backlog_id, rice)

    def fake_sync(_client, item):
        if int(item["id"]) == 2:
            raise RuntimeError("Jira rejected item")
        return JiraResult("DEMO-1", "https://jira.example/browse/DEMO-1")

    monkeypatch.setattr(JiraClient, "sync", fake_sync)
    result = sync_reviewed_items(db, SimpleNamespace())
    assert (result.attempted, result.succeeded, result.failed) == (2, 1, 1)
    assert len(db.jira_sync_rows(result.batch_id)) == 2
