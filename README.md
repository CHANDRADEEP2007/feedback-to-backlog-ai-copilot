# Feedback-to-Backlog AI Copilot

An MVP that converts multilingual support tickets into a deduplicated, explainably ranked product backlog. It uses the Kaggle Multilingual Customer Support Ticket dataset as a static stand-in for live feedback channels.

## What works

- Structured feedback extraction with Gemini when configured
- Safe deterministic extraction fallback for credential-free demos
- RapidFuzz duplicate detection with an adjustable threshold
- SQLite feedback-to-backlog provenance
- Fixed, fully traceable RICE scoring
- Manual score review before Jira sync
- Jira Cloud create/update through REST API
- Streamlit dashboard with priority, category, search, source, and guardrail views
- Bad extraction output is logged and skipped instead of being sent to Jira
- A labeled 40-ticket evaluation harness with measured extraction and dedup metrics
- Optional Gemini embedding second-pass deduplication
- Score history and top-five prioritization trends
- Bulk Jira sync for reviewed items with isolated failures and measured success
- Similarity evidence stored for every duplicate merge

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

The repository includes a small dataset sample, so it runs immediately. To use the full local dataset, set:

```text
DATASET_PATH=C:\Users\chand\Downloads\aa_dataset-tickets-multi-lang-5-2-50-version.csv
```

## Optional integrations

Add `GEMINI_API_KEY` to `.env` (or Streamlit secrets) to enable Gemini extraction. Without it, the app uses a consistent metadata-based extractor and labels the method as `local`.

For Jira Cloud, set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `JIRA_PROJECT_KEY`. Jira sync remains disabled until every required value is present. Existing linked issues are updated; unlinked backlog items create a new issue.

To enable semantic duplicate matching after RapidFuzz misses, set:

```text
SEMANTIC_DEDUP_ENABLED=true
GEMINI_API_KEY=your-key
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
SEMANTIC_DEDUP_THRESHOLD=0.82
```

Without a key, the pipeline falls back to RapidFuzz without failing ingestion.

## RICE model

The score is always:

```text
(Reach × Impact × Confidence) ÷ Effort
```

Initial values are derived deterministically from ticket priority/type. Repeated feedback increases Reach and re-scores the item. A reviewer can edit every component before Jira sync, and the stored explanation shows the exact inputs.

## Evaluation

The repository includes `eval/gold_set.csv`, a curated 40-ticket labeled validation set. Run:

```powershell
python eval/run_eval.py
```

Add `--use-gemini` to measure configured Gemini extraction. Results are written to `eval/results.json` and displayed beside targets in **Quality & guardrails**. The app reports semantic recall improvement only when the semantic layer is actually active.

The initial included gold set is intentionally small; its metrics are evidence for the harness, not a production-quality claim. Expand and independently review it before using the results externally.

## Before you publish

- Confirm `.env`, `.streamlit/secrets.toml`, `*.db`, `*.sqlite*`, and `*.log` remain ignored.
- Run `python scripts/prepublish_check.py` and require a passing result.
- Run `git status --ignored` and verify no credential or local database is staged.
- Run `git diff --cached` and inspect every staged line.
- Revoke and rotate any credential that has ever appeared in a commit or shared log.
- Use Streamlit secrets or environment variables; never paste credentials into source files.
- Confirm the committed evaluation result names its method and timestamp.
- Run `python -m pytest -q` before publishing.

## Deployment

For Streamlit Community Cloud, select `app.py` as the entrypoint and add integration values in app secrets. The included sample CSV supports a credential-free demo. Use a persistent external database for a production deployment; Community Cloud's local SQLite storage is ephemeral across rebuilds.
