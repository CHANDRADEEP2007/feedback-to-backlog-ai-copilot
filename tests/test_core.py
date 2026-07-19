from types import SimpleNamespace

from src.database import BacklogDatabase
from src.dedup import find_duplicate, find_semantic_duplicate
from src.evaluation import run_evaluation
from src.extractor import ExtractedFeedback, extract_feedback
from src.jira_client import JiraClient, JiraResult, sync_reviewed_items
from src.scoring import RiceScore, confidence_after_move, initial_rice


def test_rice_formula_is_traceable_and_stable():
    rice = RiceScore(reach=10, impact=3, confidence=0.8, effort=2)
    assert rice.score == 12.0
    assert "80% confidence" in rice.explanation


def test_initial_rice_is_deterministic():
    assert initial_rice("high", "Incident", "local") == initial_rice("high", "Incident", "local")


def test_rank_move_changes_confidence_by_five_points_per_position():
    assert confidence_after_move(0.8, from_position=3, to_position=1) == 0.9
    assert confidence_after_move(0.98, from_position=2, to_position=0) == 1.0
    assert confidence_after_move(0.02, from_position=0, to_position=2) == 0.0


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


def test_manual_reorder_is_audited_and_resets_to_ai_score(tmp_path):
    db = BacklogDatabase(tmp_path / "rerank.db")
    rice = RiceScore(3, 2, 0.8, 2)
    ids = []
    for index in range(2):
        feedback = ExtractedFeedback(f"Issue {index}", "Test", "Test", "local")
        ids.append(
            db.create_backlog_item(
                feedback,
                rice,
                {"subject": f"Issue {index}", "body": "Body"},
            )
        )

    result = db.apply_manual_reorder(list(reversed(ids)), "Sai")

    assert result == {"changed": 2, "capped": 0}
    reordered = [dict(row) for row in db.backlog_rows()]
    assert [row["id"] for row in reordered] == list(reversed(ids))
    assert all(row["manually_adjusted"] == 1 for row in reordered)
    audit = [dict(row) for row in db.priority_adjustment_rows()]
    assert len(audit) == 2
    assert {row["actor"] for row in audit} == {"Sai"}
    assert {row["action"] for row in audit} == {"manual reorder"}

    db.reset_to_ai_score(ids[1], "Sai")

    reset_item = next(dict(row) for row in db.backlog_rows() if row["id"] == ids[1])
    assert reset_item["confidence"] == reset_item["ai_confidence"] == 0.8
    assert reset_item["manually_adjusted"] == 0
    assert dict(db.priority_adjustment_rows(ids[1])[0])["action"] == "reset to AI score"


def test_unrepresentable_manual_order_is_rejected_without_changes(tmp_path):
    db = BacklogDatabase(tmp_path / "blocked-rerank.db")
    feedback_a = ExtractedFeedback("Major outage", "Test", "Test", "local")
    feedback_b = ExtractedFeedback("Minor typo", "Test", "Test", "local")
    first = db.create_backlog_item(
        feedback_a, RiceScore(10, 3, 0.8, 1), {"subject": "Major", "body": "Outage"}
    )
    second = db.create_backlog_item(
        feedback_b, RiceScore(1, 1, 0.8, 2), {"subject": "Minor", "body": "Typo"}
    )

    try:
        db.apply_manual_reorder([second, first], "Sai")
        raise AssertionError("Expected an unrepresentable order to be rejected")
    except ValueError as error:
        assert "cannot be represented" in str(error)

    assert [row["id"] for row in db.backlog_rows()] == [first, second]
    assert db.priority_adjustment_rows() == []


def test_ai_baseline_migration_uses_latest_non_manual_history(tmp_path):
    path = tmp_path / "baseline-migration.db"
    db = BacklogDatabase(path)
    feedback = ExtractedFeedback("Login issue", "Account", "Test", "local")
    backlog_id = db.create_backlog_item(
        feedback,
        RiceScore(3, 2, 0.8, 2),
        {"subject": "Login issue", "body": "Cannot sign in"},
    )
    db.update_score(backlog_id, RiceScore(3, 2, 0.95, 2), "Sai")
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE backlog SET ai_reach=NULL, ai_impact=NULL,
                ai_confidence=NULL, ai_effort=NULL WHERE id=?
            """,
            (backlog_id,),
        )

    migrated = BacklogDatabase(path)
    row = dict(migrated.backlog_rows()[0])

    assert row["confidence"] == 0.95
    assert row["ai_confidence"] == 0.8
    assert row["manually_adjusted"] == 1


def test_new_feedback_refreshes_a_manually_adjusted_ai_baseline(tmp_path):
    db = BacklogDatabase(tmp_path / "baseline-refresh.db")
    feedback = ExtractedFeedback("Account portal offline", "Account", "Test", "local")
    original = RiceScore(3, 2, 0.8, 2)
    first = {"subject": "Portal offline", "body": "Cannot load", "type": "Incident"}
    backlog_id = db.create_backlog_item(feedback, original, first)
    db.update_score(backlog_id, RiceScore(3, 2, 0.95, 2), "Sai")
    match = find_duplicate(
        "Account portal is offline", [dict(db.backlog_rows()[0])], threshold=85
    )

    db.add_duplicate_source(
        backlog_id,
        {"subject": "Account portal is offline", "body": "Still down"},
        RiceScore(4, 2, 0.8, 2),
        match,
    )

    row = dict(db.backlog_rows()[0])
    assert row["manually_adjusted"] == 0
    assert row["confidence"] == row["ai_confidence"] == 0.8
    assert dict(db.priority_adjustment_rows(backlog_id)[0])["action"] == "AI baseline refreshed"


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
