# Dataset source and attribution

This repository redistributes the dataset used by the Feedback-to-Backlog AI Copilot demo.

## Source

- **Title:** Customer IT Support - Ticket Dataset
- **Creator:** Tobias Bueck
- **Kaggle dataset:** https://www.kaggle.com/datasets/tobiasbueck/multilingual-customer-support-tickets
- **Pinned source version:** https://www.kaggle.com/datasets/tobiasbueck/multilingual-customer-support-tickets/versions/10
- **License:** Attribution 4.0 International (CC BY 4.0)
- **License text:** https://creativecommons.org/licenses/by/4.0/

Kaggle describes the data as labeled support emails with agent answers, priorities, queues, types, languages, and tags. The project uses these records as a static simulation of product-feedback ingestion.

## Files included here

| File | Purpose | Records | Changes |
|---|---:|---:|---|
| `data/aa_dataset-tickets-multi-lang-5-2-50-version.csv` | Default full app dataset | 28,587 | None; copied from the downloaded version-10 CSV |
| `data/sample_tickets.csv` | Fast smoke-test subset | 300 | First 300 records exported with the same fields |

Full-file integrity:

- Size: 25,996,354 bytes
- SHA-256: `F187C090E59581C2BBF3AA1377C8DB4DD647464ECF2AE51BF8966E42E0ED6BC0`

## Field inventory

The included CSV contains 16 columns:

`subject`, `body`, `answer`, `type`, `queue`, `priority`, `language`, `version`, `tag_1`, `tag_2`, `tag_3`, `tag_4`, `tag_5`, `tag_6`, `tag_7`, and `tag_8`.

## Attribution notice

Dataset attribution: **Customer IT Support - Ticket Dataset** by **Tobias Bueck**, obtained from Kaggle, licensed under **CC BY 4.0**. The original full CSV is redistributed unchanged. The smaller sample is identified as a subset. No endorsement by the dataset creator or Kaggle is implied.

The repository's application code, evaluation harness, and curated gold-set labels are separate project artifacts and are not represented as part of the original Kaggle dataset.
