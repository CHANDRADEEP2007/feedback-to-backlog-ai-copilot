<div align="center">

# ⚡ Feedback-to-Backlog AI Copilot

### Turn messy customer noise into a ranked, explainable product backlog—automatically.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_API-4285F4?style=for-the-badge&logo=google&logoColor=white)
![Jira](https://img.shields.io/badge/Jira_Cloud-0052CC?style=for-the-badge&logo=jira&logoColor=white)
![Phase](https://img.shields.io/badge/status-MVP_Phase_2-9146FF?style=for-the-badge)
[![CI](https://github.com/CHANDRADEEP2007/feedback-to-backlog-ai-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/CHANDRADEEP2007/feedback-to-backlog-ai-copilot/actions/workflows/ci.yml)

[Project page](https://chandradeep2007.github.io/feedback-to-backlog-ai-copilot/) · [Dataset source](https://www.kaggle.com/datasets/tobiasbueck/multilingual-customer-support-tickets/versions/10)

</div>

---

## 🧠 What this actually does

Product managers receive feedback through support tickets, calls, reviews, and other disconnected channels. Important signals get lost because manually converting that feedback into a prioritized backlog is slow and inconsistent.

This project is a working AI-assisted pipeline that:

1. extracts the core issue from raw support tickets;
2. merges duplicate and near-duplicate feedback;
3. assigns a transparent RICE priority score;
4. preserves links to every source ticket;
5. lets a product manager review the score; and
6. creates or updates Jira issues.

Every score is explainable, evaluation results are measured, and known limitations are documented.

> 💡 The application runs without API keys. Gemini, semantic matching, and Jira are optional integrations.

---

## ✨ What works now

| Feature | Detail |
|---|---|
| **AI extraction** | Gemini-powered when configured, with a deterministic local fallback |
| **Layered deduplication** | RapidFuzz matching plus an optional Gemini embedding second pass |
| **Full provenance** | SQLite links every backlog item to its source feedback |
| **Transparent scoring** | Fixed and fully traceable RICE formula |
| **Human review** | Product managers can adjust RICE inputs before Jira sync |
| **Explainable re-rank** | Dragging priority changes Confidence by a fixed 5 percentage points per position, logs the reviewer and formula change, and supports one-click reset |
| **Jira Cloud sync** | Creates new issues or updates already-linked issues through the REST API |
| **Interactive dashboard** | Priority, category, search, source, score-change, and guardrail views in Streamlit |
| **Dedicated architecture view** | A fifth dashboard tab switches between the built MVP flow and a clearly labeled target-state roadmap |
| **Connections preview** | A minor sidebar panel lists planned sources as disabled “Coming soon” controls; no connector is presented as functional before it exists |
| **Guardrails** | Malformed AI output is retried once, then logged and skipped safely |
| **Measured quality** | A labeled 40-ticket evaluation harness reports actual extraction and dedup metrics |
| **Adaptive priority insight** | Shows score-change deltas when history is sufficient, otherwise explains the current top five with full RICE inputs |
| **Bulk Jira sync** | Syncs reviewed items independently so one failure does not stop the batch |
| **Explainable merges** | Each duplicate source stores its matching method and similarity score |

---

## 🏁 Quick start

```powershell
git clone https://github.com/CHANDRADEEP2007/feedback-to-backlog-ai-copilot.git
cd feedback-to-backlog-ai-copilot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) if Streamlit does not open automatically.

The repository contains the complete 28,587-ticket CSV and uses it by default:

```env
DATASET_PATH=data/aa_dataset-tickets-multi-lang-5-2-50-version.csv
```

For faster smoke tests, use the included 300-row subset:

```env
DATASET_PATH=data/sample_tickets.csv
```

---

## 🔌 Optional integrations

### Gemini extraction

```env
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash
```

Without a key, the application uses a consistent metadata-based extractor and labels the method as `local`.

### Semantic deduplication

```env
SEMANTIC_DEDUP_ENABLED=true
GEMINI_API_KEY=your-key
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
SEMANTIC_DEDUP_THRESHOLD=0.82
```

Semantic matching runs only after RapidFuzz does not find a match. If credentials are missing or the embedding request fails, ingestion continues safely with the RapidFuzz result.

### Jira Cloud sync

```env
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-token
JIRA_PROJECT_KEY=PROJ
JIRA_ISSUE_TYPE=Task
```

Jira sync remains disabled until all required values are set. Keep these values in `.env` locally or in Streamlit secrets when deployed—never commit them.

---

## 🧮 Transparent RICE scoring

Every priority score uses the same visible formula:

```text
        Reach × Impact × Confidence
RICE = ────────────────────────────
                   Effort
```

Initial inputs are derived deterministically from ticket priority and type. Repeated feedback increases Reach and re-scores the item. Reviewers can edit every component before Jira sync, and the stored explanation retains the exact calculation.

Manual drag-to-reorder never creates a separate hidden priority. Moving an item up one position adds `0.05` to Confidence; moving it down subtracts `0.05`, bounded to `0.0–1.0`. The app previews the recalculated score and accepts the order only when the resulting RICE scores produce that exact ranking. Each accepted adjustment records the reviewer, timestamp, positions, Confidence change, and score change. **Reset to AI score** restores the deterministic baseline in one click.

---

## 🎯 Evaluation

Run the labeled gold-set evaluation:

```powershell
python eval/run_eval.py
```

To evaluate configured Gemini extraction:

```powershell
python eval/run_eval.py --use-gemini
```

Results are written to `eval/results.json` and displayed beside targets in the **Quality & guardrails** tab.

Current credential-free baseline on the included gold set:

| Metric | Measured result | Target |
|---|---:|---:|
| Extraction accuracy | 100.0% | ≥85% |
| RapidFuzz dedup precision | 100.0% | ≥80% |
| RapidFuzz dedup recall | 33.3% | Improvement expected from semantic matching |

> ⚠️ The included 40-ticket gold set is intentionally small and curated. These numbers validate the evaluation harness; they are not production-scale quality claims. Expand and independently review the labels before using the results externally.

---

## 📦 Dataset source and attribution

- **Dataset:** [Customer IT Support - Ticket Dataset, version 10](https://www.kaggle.com/datasets/tobiasbueck/multilingual-customer-support-tickets/versions/10)
- **Creator:** Tobias Bueck
- **License:** [Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
- **Full file:** `data/aa_dataset-tickets-multi-lang-5-2-50-version.csv`
- **Smoke-test subset:** `data/sample_tickets.csv`
- **Profile:** 28,587 records, 16 columns, 25,996,354 bytes
- **SHA-256:** `F187C090E59581C2BBF3AA1377C8DB4DD647464ECF2AE51BF8966E42E0ED6BC0`

The full CSV is redistributed unchanged under CC BY 4.0. The smaller file is identified as a 300-row subset. See [DATASET_SOURCE.md](DATASET_SOURCE.md) for the field inventory and reproducibility details.

---

## 🗂️ Project structure

```text
.
├── app.py                         # Streamlit dashboard
├── src/                           # Pipeline, storage, scoring, dedup, Jira
├── data/                          # Full Kaggle CSV and smoke-test subset
├── eval/                          # Gold set, evaluator, measured results
├── scripts/prepublish_check.py    # Repository secret and hygiene scan
├── tests/                         # Automated tests
├── .env.example                   # Safe configuration template
└── requirements.txt
```

---

## 🛡️ Before publishing

- [ ] Confirm `.env`, `.streamlit/secrets.toml`, `*.db`, `*.sqlite*`, and `*.log` are ignored.
- [ ] Run `python scripts/prepublish_check.py` and require a passing result.
- [ ] Run `git status --ignored` and verify no credentials or local database is staged.
- [ ] Run `git diff --cached` and inspect every staged line.
- [ ] Rotate any credential that has ever appeared in a commit or shared log.
- [ ] Store deployment credentials in Streamlit secrets or environment variables.
- [ ] Confirm committed evaluation results identify their method and timestamp.
- [ ] Run `python -m pytest -q` before pushing.

---

## ⚠️ Known limitations

- The gold set is deliberately small and does not represent production-scale validation.
- RapidFuzz misses sufficiently different paraphrases when semantic matching is disabled.
- Semantic matching incurs Gemini API usage and requires credentials.
- Initial RICE inputs are heuristics until reviewed by a product manager.
- Some drag arrangements cannot be represented by the fixed Confidence rule; the app rejects them without changing any score instead of storing a rank that conflicts with RICE.
- Jira projects with custom required fields may need additional field mapping.
- Local SQLite storage is suitable for the demo but is ephemeral on Streamlit Community Cloud rebuilds.

---

## ☁️ Deployment

For Streamlit Community Cloud:

1. select `app.py` as the entrypoint;
2. add optional integration values under app secrets;
3. use a persistent external database for production; and
4. use the sample dataset path if faster startup is more important than full-data exploration.

GitHub Pages hosts the [project documentation](https://chandradeep2007.github.io/feedback-to-backlog-ai-copilot/) but cannot execute the Python Streamlit application.

---

<div align="center">

**Built to demonstrate transparent prioritization, honest limitations, and measured pipeline quality—not just an AI demo.**

</div>
