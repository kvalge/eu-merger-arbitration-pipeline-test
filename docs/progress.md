# Progress
 
## Completed steps
 
### 1. Project foundation
- Created project folder structure:
  - `ingestion/` — scripts for downloading and processing data
  - `config/` — configuration files (e.g. keyword list)
  - `data/raw/` — downloaded source data (JSON file from EC)
  - `data/processed/` — processing results (hits file)
  - `logs/` — process metadata (summary, checkpoint)
  - `docs/` — documentation
- Created `requirements.txt` — list of Python dependencies
- Configured `.gitignore` — virtual environment, cache files and IDE files excluded; data files committed to git (35 MB, fits fine)
---
 
### 2. Keyword configuration (`config/keywords.txt`)

Each line has the format `LANG: term` where `LANG` is the two-letter language code
matching the `attachmentLanguage` field in the JSON (e.g. `EN: arbitrat*`, `ET: vahekoh*`).

**Format rules:**
- Wildcard `*` matches any number of characters — `arbitrat*` matches `arbitration`, `arbitral`, `arbitrator`, etc.
- AND condition: `CZ: rozhodč*:řízen*` — both terms must appear in the text
- OR condition: put each variant on its own line
- Empty lines and lines starting with `#` are ignored

**Language matching:**
Each PDF is searched using only the rules for its language as indicated by the
`attachmentLanguage` field in the JSON. If no rules exist for a PDF's language —
either because the language is not in `keywords.txt` or all its rules have been
commented out — the PDF is skipped entirely. There is no fallback to another language.
This means commenting out all rules for a language reliably disables searching for that language.

**Maintenance:**
- Languages are sorted alphabetically by language code (BG → SV)
- Rules that were found to be too broad are kept but commented out, with an explanation
  (e.g. `FR: arbitrag*` matched economic arbitrage, not arbitration proceedings;
  `FI: välitys*` matched `välityksellä` meaning "via/through")
- **To change search terms in the future: edit this file only — no code changes needed**

---
 
### 3. JSON download (`ingestion/download_json.py`)
- Downloads the European Commission merger decisions JSON from:
  `https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com/case-data-M.json`
- Saves to `data/raw/case-data-M.json`
- If the file already exists, skips the download
- Run: `python ingestion/download_json.py`
---
 
### 4. JSON structure inspection (`ingestion/inspect_json.py`)
- Explores the downloaded JSON and prints statistics
- Identified actual JSON structure:
  - Top level is a dict where key = `caseNumber` (e.g. `"M.2027"`)
  - Each case contains `metadata`, `caseAttachments`, `decisions`
  - `decisions` is a list — each decision has `metadata` and `decisionAttachments`
  - PDF link is nested deep: `decisions → decisionAttachments → metadata → attachmentLink`
  - All values are lists (e.g. `"caseNumber": ["M.2027"]`)
- Filters to cases with Art. 6(1)(b) or Art. 8(2) decisions only
- Prints statistics: decision types, sectors (grouped by NACE division), attachment languages
- Saves output to `ingestion/inspect_json_output.txt` (not committed to git)
- Run: `python ingestion/inspect_json.py`
---
 
### 5. PDF search and results (`ingestion/ingest.py`)
 
#### What it does
Iterates over all relevant cases (those with an Art. 6(1)(b) or Art. 8(2) decision),
downloads their PDF attachments, searches for keywords by language, and saves matches.
 
#### Step by step
1. Loads keyword rules from `config/keywords.txt`, grouped by language code
2. Loads `data/raw/case-data-M.json`
3. Filters to relevant cases — those with at least one Art. 6(1)(b) or Art. 8(2) decision
4. For each relevant case:
   - Finds PDF links in `decisionAttachments`
   - Downloads the PDF
   - Looks up the keyword rules for the PDF's `attachmentLanguage`
   - Searches the full PDF text using those rules
   - If a keyword matches: saves the case record with only the matched decision
5. Writes results to two output files
6. Writes a summary to `logs/ingest_summary.json`
7. Clears the checkpoint file on successful completion
#### Output files
- `data/processed/arbitration_hits.jsonl` — one JSON object per line, machine-readable (for dbt)
- `data/processed/arbitration_hits_readable.json` — same content, indented, human-readable (for reviewing on GitHub)
- `logs/ingest_summary.json` — process statistics:
  - total cases, total relevant cases, total relevant decisions
  - matched cases and matched decisions
  - used later on the dashboard to calculate the share: `matchedDecisions / totalRelevantDecisions`
#### Each hit record contains
- Case-level fields: `caseNumber`, `caseTitle`, `caseCompanies`, `caseInstrument`,
  `caseRegulation`, `caseSimplified`, `caseSectors`, `caseInitiationDate`,
  `caseNotificationDate`, `caseDeadlineDate`, `caseLastDecisionDate`
- Only the matched decisions (not all decisions of the case)
- Each matched decision includes: `decisionNumber`, `decisionAdoptionDate`,
  `decisionOfficialJournalPublicationsPublishedDates`, `decisionTypes`, `decisionAttachments`
- Match metadata: `_matchedKeywords` (keyword, language, context snippet), `_matchedPdfUrl`, `_processedAt`
#### Testing
To process only the first N relevant cases:
```bash
TEST_LIMIT=20 python ingestion/ingest.py
```
To run the full dataset:
```bash
python ingestion/ingest.py
```
 
---
 
### 6. Checkpoint (`logs/checkpoint.json`)
 
The checkpoint system allows the ingest process to resume from where it stopped
if it is interrupted (e.g. network error, manual `Ctrl+C`, machine restart).
 
#### How it works
- Before processing starts, the checkpoint file is read (if it exists)
- The file contains a list of `caseNumber` values that have already been processed
- At the start of each case, the script checks: `if caseNumber in checkpoint → skip`
- After each case is processed (whether a match was found or not), the checkpoint file
  is rewritten with the updated list — this happens after **every single case**
- If the process is interrupted at any point, the checkpoint captures everything
  up to the last completed case
- On restart, processing resumes from the first case not yet in the checkpoint
- On successful completion, the checkpoint file is automatically deleted
#### Key detail
The checkpoint tracks **all processed cases**, not just the ones where a keyword was found.
This ensures no case is ever processed twice, regardless of the result.
 
#### Example log output on resume
```
Resuming from checkpoint: skipping 358 already-processed cases
Processing case 359 / 9038: M.2940
Processing case 360 / 9038: M.2941
...
```
 
#### Note on TEST_LIMIT
When `TEST_LIMIT` is set, the checkpoint is not used — test runs are always
processed from scratch and do not interfere with a real run in progress.
 
---
 
## Next steps
 
1. **Manual result validation** — review `arbitration_hits_readable.json` for false positives
   and refine `keywords.txt` as needed
2. **Re-run ingest** — after keyword changes, delete checkpoint (if any) and re-run
3. **dbt setup** — load `arbitration_hits.jsonl` into PostgreSQL and build transformation layer
4. **Docker Compose** — PostgreSQL, dbt, Airflow and Superset in containers
5. **Airflow DAG** — automated scheduler: monthly ingest → dbt run → dbt test
6. **Dashboard** — Superset or Streamlit displaying the metrics from the README