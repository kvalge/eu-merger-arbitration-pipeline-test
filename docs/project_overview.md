# Project Overview — EU Merger Arbitration Pipeline

**Last updated:** 2026-05-24  
**Companion docs:** [`progress.md`](progress.md) (implementation log), [`architecture.md`](architecture.md) (target design)

---

## 1. What this project is

### Purpose

This project builds a **data pipeline** to study **arbitration mechanisms** in **European Commission conditional merger decisions**. The business goal is to produce statistics that do not currently exist in a consolidated form: how often arbitration clauses appear when enforcing merger commitments, over time, by sector (NACE), and for recent vs historical periods.

The work originated from a **University of Tartu Data Engineering** group project (March–June 2026).

### Business questions (from README / architecture)

- In how many EC **conditional** merger decisions (Art. 6(1)(b) or Art. 8(2)) has an arbitration mechanism been considered for enforcing commitments?
- What is the **sectoral distribution** (NACE) of those decisions?
- How do counts and shares evolve **by month/year**, including “last month” views for operational monitoring?

### Target architecture (planned)

```mermaid
flowchart LR
    source[EC JSON on S3] --> ingest[Python ingestion]
    ingest --> staging[(PostgreSQL staging)]
    staging --> transform[dbt Core 1.10]
    transform --> mart[(mart)]
    mart --> dashboard[Superset or Streamlit]
    mart --> quality[dbt tests]
    scheduler[Airflow 3.x] --> ingest
```

### Current implementation status

| Planned component | Status |
|-------------------|--------|
| Download EC merger JSON | **Done** (`ingestion/download_json.py`) |
| Explore JSON structure | **Done** (`ingestion/inspect_json.py`) |
| PDF keyword search | **Done** (`ingestion/ingest.py`) |
| Keyword configuration (no code change) | **Done** (`config/keywords.txt`) |
| Processed hits output | **Done** (`data/processed/`) |
| PostgreSQL + `staging` layer | **Not started** (`data/staging/` empty) |
| dbt models | **Not started** (in `requirements.txt` only) |
| Airflow orchestration | **Not started** |
| Dashboard | **Not started** |
| Docker Compose stack | **Not started** |

**Latest full production ingest** (`logs/ingest_summary.json`, 2026-05-23):

| Metric | Value |
|--------|------:|
| Total cases in JSON | 10,225 |
| Relevant cases (Art. 6(1)(b) or Art. 8(2)) | 9,038 |
| Relevant decisions | 9,041 |
| Matched cases | 15 |
| Matched decisions | 15 |

Phase 1 **ingestion is complete**; warehouse, orchestration, and dashboard are not built yet.

---

## 2. Ingest code review (`ingestion/ingest.py`)

### Verdict

The ingest implementation is **correct for its documented design** and aligns with [`progress.md`](progress.md). It is suitable for phase-1 keyword discovery and manual validation; it is **not** yet a complete answer to all business metrics (those need dbt + dashboard).

### What the code does correctly

| Behavior | Implementation |
|----------|----------------|
| Case filter | Only cases with at least one Art. 6(1)(b) or Art. 8(2) decision enter the main loop |
| PDF scope | `process_case()` searches PDFs only on decisions whose types include Art. 6(1)(b) or Art. 8(2) |
| Language rules | Each PDF uses rules for its `attachmentLanguage` only; no cross-language fallback |
| Early skip | Skips cases when no attachment language has rules (languages normalized with `.upper()`) |
| Keywords | Wildcard and AND rules compiled once; config-driven via `keywords.txt` |
| First-match policy | Stops after first matching PDF per decision and first matching decision per case (intentional) |
| Checkpoint (full runs) | Saves processed `caseNumber` after each case; resume skips completed cases |
| Hit reload on resume | Loads existing `arbitration_hits.jsonl` when checkpoint exists |
| Test isolation | `TEST_LIMIT > 0` disables checkpoint read/write; writes to separate `test_*` files |
| Outputs | Production vs test paths are distinct; production files are not overwritten by test runs |

### Known limitations (by design or documented)

| Limitation | Notes |
|------------|--------|
| Crash before write | Matches found after the last checkpoint save but before Step 6 output write are **lost** on resume; checkpoint still skips those cases |
| First-match only | Does not record multiple arbitration mentions per case |
| Keyword semantics | Text match ≠ legal “commitment arbitration mechanism”; manual review required |
| No PDF retries | Download failures logged at DEBUG and skipped |
| Early skip scope | Language set for skip includes attachments on **all** decision types (minor edge case; see progress.md) |
| `TEST_LIMIT` summary | `test_ingest_summary.json` still uses full-dataset `totalRelevantDecisions` (9041) while only processing N cases |
| Download refresh | `download_json.py` skips if file exists; refresh deferred to Airflow |

### Alignment: `progress.md` vs code

| Topic | Match? |
|-------|--------|
| Step-by-step ingest logic | Yes |
| Checkpoint + hit reload | Yes |
| Crash limitation | Yes (documented in both) |
| `TEST_LIMIT` / separate test outputs | Yes |
| First full run stats | Yes (matches `ingest_summary.json`) |
| NL keyword changes | Yes (`arbitrag*` commented; specific NL terms in `keywords.txt`) |
| PT ambiguity note | Documented in progress; `PT: arbitrag*` still active in config |

---

## 3. Repository layout

```
eu-merger-arbitration-pipeline-test/
├── README.md
├── requirements.txt
├── .gitignore
├── config/
│   └── keywords.txt
├── data/
│   ├── raw/
│   │   └── case-data-M.json          # ~36 MB EC source
│   ├── processed/
│   │   ├── arbitration_hits.jsonl    # production hits (dbt input)
│   │   ├── arbitration_hits_readable.json
│   │   ├── test_arbitration_hits.jsonl           # TEST_LIMIT only
│   │   └── test_arbitration_hits_readable.json
│   └── staging/                        # empty; future PostgreSQL load
├── docs/
│   ├── architecture.md
│   ├── progress.md
│   └── project_overview.md
├── ingestion/
│   ├── download_json.py
│   ├── inspect_json.py
│   ├── inspect_json_output.txt
│   └── ingest.py
└── logs/
    ├── ingest_summary.json             # production run stats
    ├── test_ingest_summary.json        # TEST_LIMIT runs
    └── checkpoint.json                 # runtime only; deleted on success
```

A local `venv/` may exist but is gitignored.

---

## 4. File-by-file reference

### Root

| File | Role |
|------|------|
| `README.md` | Business context, architecture diagram, planned stack |
| `requirements.txt` | `requests`, `pdfplumber`; planned `dbt-postgres`, `apache-airflow`; `pytest` |
| `.gitignore` | Excludes `.env`, venv, caches; `data/` may be committed (~35 MB JSON) |

### `config/keywords.txt`

Multilingual arbitration search rules (`LANG: term`). Wildcards (`*`), AND (`LANG: a*:b*`), comments. Broad rules commented for FR, FI, SV, NL with narrower replacements where needed. Edit this file only to tune search terms.

### `ingestion/download_json.py`

Downloads EC `case-data-M.json` to `data/raw/`; skips if file exists. Run: `python ingestion/download_json.py`.

### `ingestion/inspect_json.py`

Explores JSON structure and statistics for Art. 6(1)(b) / Art. 8(2) cases. Writes `ingestion/inspect_json_output.txt`.

### `ingestion/ingest.py`

Main pipeline (~510 lines). See [§2](#2-ingest-code-review-ingestioningestpy) and [`progress.md` §5](progress.md) for full logic.

**Production outputs:**

- `data/processed/arbitration_hits.jsonl`
- `data/processed/arbitration_hits_readable.json`
- `logs/ingest_summary.json`

**Test outputs** (`TEST_LIMIT` set):

- `data/processed/test_arbitration_hits.jsonl`
- `data/processed/test_arbitration_hits_readable.json`
- `logs/test_ingest_summary.json`

### `data/processed/arbitration_hits.jsonl`

One JSON object per line per matched case. Includes case metadata, matched decisions only, and `_matchedKeywords`, `_matchedPdfUrl`, `_processedAt`. Current production file: **15 hits**.

### `docs/progress.md`

Authoritative implementation log and run instructions. Prefer this over this overview for day-to-day ingest details.

### `docs/architecture.md`

Target metrics, DB layers (`staging` / `intermediate` / `mart`), risks — mostly future state.

---

## 5. Metrics readiness

| Metric (architecture) | Status |
|-----------------------|--------|
| Arbitration mention yes/no per decision | **Partial** — hits exist; denominator in `ingest_summary.json` |
| Share `matchedDecisions / totalRelevantDecisions` | **Partial** — summary has both values |
| Count/share by month/year | **No** — needs dbt time aggregation |
| Sector (NACE) distribution | **Partial** — `caseSectors` on hits; needs mart |
| Sector trends over time | **No** — needs mart + dashboard |

---

## 6. Suggested run order

```bash
pip install -r requirements.txt

python ingestion/download_json.py
python ingestion/inspect_json.py          # optional

# Test (does not touch production outputs or checkpoint)
# Linux/macOS:
TEST_LIMIT=20 python ingestion/ingest.py
# Windows PowerShell:
$env:TEST_LIMIT=20; python ingestion/ingest.py

# Full production run
python ingestion/ingest.py
```

Review production results in `data/processed/arbitration_hits_readable.json` and `logs/ingest_summary.json`.

After keyword changes: delete `logs/checkpoint.json` if present; delete or back up `arbitration_hits.jsonl` for a clean re-run (resume merges from last written jsonl).

---

## 7. Remaining work (prioritized)

### Ingestion quality (before trusting published stats)

1. Manual review of all 15 hits in `arbitration_hits_readable.json` (false positives, PT/EN context).
2. Refine `keywords.txt` based on review; re-run full ingest.
3. Optional: append hits to jsonl after each match to survive crashes without re-scan gaps.

### Pipeline build-out (from progress.md)

4. dbt project — load `arbitration_hits.jsonl` into PostgreSQL staging/mart.
5. Docker Compose — PostgreSQL, dbt, Airflow, Superset.
6. Airflow DAG — monthly download → ingest → dbt run/test.
7. Dashboard — Superset or Streamlit.

### Code quality (optional)

8. Extract shared helpers (`first`, `parse_label`, relevance checks) shared by `inspect_json.py` and `ingest.py`.
9. pytest fixtures for `load_keywords()`, `is_relevant_case()`, `search_pdf()`.
10. PDF download retries and polite rate limiting.
11. ETag / `Last-Modified` refresh in `download_json.py` (planned for Airflow stage).

---

## 8. Summary

The repository delivers a **working phase-1 pipeline**: download EC merger open data, filter to conditional-clearance decision types, search decision PDFs in many EU languages via configurable keywords, and emit production and test outputs with checkpoint resume for full runs.

`ingest.py` and `progress.md` are **in sync**. The main gaps are **business validation of hits**, **crash-safe hit persistence** (optional improvement), and **everything after ingestion** (PostgreSQL, dbt, Airflow, dashboard).

For implementation detail and changelog-style notes, use [`progress.md`](progress.md).
