# Progress
 
## Completed steps
 
### 1. Project foundation
- Created project folder structure:
  - `ingestion/` — scripts for downloading and processing data
  - `config/` — configuration files (keyword list)
  - `data/raw/` — downloaded source data (JSON file from EC)
  - `data/processed/` — processing results (hits files)
  - `logs/` — process metadata (summary, checkpoint)
  - `docs/` — documentation
- Created `requirements.txt` — list of Python dependencies
- Configured `.gitignore` — virtual environment, cache files and IDE files excluded;
  data files committed to git (35 MB, fits fine)
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
- Rules that were found to be too broad are kept but commented out, with an explanation:
  - `FR: arbitrag*` — matched economic arbitrage, not arbitration proceedings
  - `FI: välitys*` — matched `välityksellä` meaning "via/through"
  - `SV: skilje*` — matched `skiljer` meaning "differs/distinguishes"
  - `NL: arbitrag*` — same ambiguity as French, economic arbitrage vs dispute resolution
- `PT: arbitrag*` has the same potential ambiguity as FR and NL — review Portuguese hits manually
- **To change search terms in the future: edit this file only — no code changes needed**
---
 
### 3. JSON download (`ingestion/download_json.py`)
- Downloads the European Commission merger decisions JSON from:
  `https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com/case-data-M.json`
- Saves to `data/raw/case-data-M.json`
- If the file already exists, skips the download
- Run: `python ingestion/download_json.py`
- **Note:** the source file is updated periodically (new decisions added). The current
  "skip if exists" logic is intentional for manual runs. Automatic refresh logic
  (ETag / `Last-Modified` header check) will be added in the Airflow setup stage.
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
- Saves output to `ingestion/inspect_json_output.txt`
- Run: `python ingestion/inspect_json.py`
---
 
### 5. PDF search and results (`ingestion/ingest.py`)
 
#### Overview
Iterates over all relevant cases (those with an Art. 6(1)(b) or Art. 8(2) decision),
downloads their PDF attachments, searches for keywords by language, and saves matches.
 
#### Step-by-step logic
 
**Step 1 — Load keyword rules**
Reads `config/keywords.txt` and builds a dict keyed by language code:
```
{
  "EN": [{"raw": "arbitrat*", "type": "wildcard", "pattern": <compiled regex>}],
  "CZ": [{"raw": "rozhodč*:řízen*", "type": "and", "patterns": [<regex1>, <regex2>]}],
  ...
}
```
Wildcard terms are compiled once into regex patterns at load time — `arbitrat*` becomes
a regex that matches any sequence of non-space characters after the stem.
AND rules require all patterns to match somewhere in the text.
 
**Step 2 — Load JSON and filter relevant cases**
Loads `data/raw/case-data-M.json` and filters to cases that have at least one decision
whose `decisionTypes` label is exactly `Art. 6(1)(b)` or `Art. 8(2)`.
Also counts the total number of relevant decisions across all cases — used later
in the dashboard to calculate the share: `matchedDecisions / totalRelevantDecisions` (decision-based, not case-based).
 
**Step 3 — Load checkpoint (if resuming)**
Before processing starts, reads `logs/checkpoint.json` if it exists.
The file contains a list of `caseNumber` values already processed in a previous run.
If a checkpoint exists, also loads hits from the last *written*
`data/processed/arbitration_hits.jsonl` into memory — so matches from a previously
completed run segment are included in the final output.
 
**Important limitation:** this only recovers hits that were already written to disk.
If the process crashed before writing output files (Step 6), any matches found
during that interrupted run are not recoverable — those cases are skipped by checkpoint
but their in-progress matches are lost. See Known Limitations.
 
**Step 4 — Process each case**
 
For each relevant case, `process_case()` runs the following logic:
 
1. **Early language skip** — collects all `attachmentLanguage` values across all
   PDFs of the case. If none of them have keyword rules in `keywords.txt`, skips
   the case entirely without downloading any PDFs.
2. **Decision type filter** — iterates only over decisions whose `decisionTypes`
   include `Art. 6(1)(b)` or `Art. 8(2)`. Decisions of other types (procedural,
   referral, etc.) are skipped — their PDFs are not downloaded or searched.
   Note: the early language skip in step 1 collects languages from *all* decisions
   including non-qualifying ones — this is a minor edge case with no practical impact.
3. **PDF download and search** — for each PDF attachment of a qualifying decision:
   - Looks up keyword rules for the PDF's `attachmentLanguage`
   - If no rules exist for that language, skips the PDF (no fallback to another language)
   - Downloads the PDF and extracts all text using `pdfplumber`
   - Searches the full text using the language's rules:
     - Wildcard rule: regex pattern must match anywhere in the text
     - AND rule: all patterns must match somewhere in the text
   - On a match: records the keyword, language and a context snippet
     (up to 100 characters before and after the match)
4. **First match policy** — stops after the first matching PDF within a decision,
   and after the first matching decision within a case. This is an intentional
   design choice to keep processing fast. A case is either "has arbitration mention"
   or "does not" — exhaustive detection within a case is not required at this stage.
5. **Record building** — if a match was found, builds the output record with:
   - Case-level fields from `metadata`
   - Only the matched decision(s), not all decisions of the case
   - Match metadata: matched keywords with context, matched PDF URL, timestamp
**Step 5 — Checkpoint update**
After each case is processed (whether a match was found or not), the checkpoint
file is rewritten with the updated list of processed case numbers.
This happens after **every single case**, so if the process is interrupted,
at most one case's work is lost.
 
**Step 6 — Write output**
After all cases are processed, writes two output files:
- `data/processed/arbitration_hits.jsonl` — one JSON object per line, for dbt
- `data/processed/arbitration_hits_readable.json` — same content, indented, for GitHub review
**Step 7 — Write summary**
Writes `logs/ingest_summary.json` with:
- `totalCases` — all cases in the JSON file
- `totalRelevantCases` — cases with Art. 6(1)(b) or Art. 8(2) decision
- `totalRelevantDecisions` — total count of Art. 6(1)(b) / Art. 8(2) decisions
- `matchedCases` — cases where a keyword was found
- `matchedDecisions` — decisions where a keyword was found
- `processedAt` — timestamp
First full run completed: 10,225 total cases, 9,038 relevant cases, 9,041 relevant decisions, 15 matches found.
 
**Step 8 — Clear checkpoint**
On successful completion, deletes `logs/checkpoint.json` automatically.
 
#### Checkpoint in detail
 
The checkpoint allows resuming an interrupted run without reprocessing already-completed cases.
 
| Event | What happens |
|-------|-------------|
| Process starts fresh | No checkpoint file → starts from the beginning |
| After each case | Checkpoint file rewritten with all processed case numbers so far |
| Process interrupted | Checkpoint file contains all cases completed before the interruption |
| Process restarted | Checkpoint loaded → existing hits loaded → skips already-processed cases |
| Process completes | Checkpoint file deleted automatically |
 
On resume, the script logs:
```
Resuming from checkpoint: skipping 358 already-processed cases
Loaded 12 existing hits from last written output
```
 
**Note on TEST_LIMIT:** when `TEST_LIMIT` is set, the checkpoint is fully disabled —
the checkpoint file is never read or written during a test run. Test runs always process
from scratch and never interfere with a real run in progress.
 
#### Running
```bash
# Full run
python ingestion/ingest.py
 
# Test run — first 20 cases only (Linux/macOS)
TEST_LIMIT=20 python ingestion/ingest.py
 
# Test run — first 20 cases only (Windows PowerShell)
$env:TEST_LIMIT=20; python ingestion/ingest.py
```
 
**Test run output files** — test runs write to separate files and never overwrite production results:
- `data/processed/test_arbitration_hits.jsonl`
- `data/processed/test_arbitration_hits_readable.json`
- `logs/test_ingest_summary.json`
---
 
## Known limitations
 
- **First match policy** — only the first matching PDF per decision and first matching
  decision per case are recorded. Multiple arbitration mentions within the same case
  are not fully captured. This is a deliberate choice for this stage.
- **Checkpoint does not recover in-progress hits** — if the process crashes before
  writing output files, matches found during that interrupted run are not recoverable.
  The checkpoint skips those cases on resume but their matches are lost. The checkpoint
  only preserves hits written to `arbitration_hits.jsonl` in a previously completed run segment.
- **Keyword precision** — keyword search cannot distinguish legal concepts without
  tighter rules or NLP. Some false positives are expected and should be reviewed manually
  in `arbitration_hits_readable.json`.
- **No PDF download retries** — transient network failures are logged and the PDF is
  skipped. Will be addressed when Airflow retry logic is added.
---
 
## Next steps
 
1. **Manual result validation** — review `arbitration_hits_readable.json` for false
   positives and refine `keywords.txt` as needed
2. **Re-run ingest** — after keyword changes, delete checkpoint (if any) and re-run.
   Also delete or back up `arbitration_hits.jsonl` if you want a clean slate —
   on resume the script merges from the last written file
3. **dbt setup** — load `arbitration_hits.jsonl` into PostgreSQL and build transformation layer
4. **Docker Compose** — PostgreSQL, dbt, Airflow and Superset in containers
5. **Airflow DAG** — automated scheduler: monthly ingest → dbt run → dbt test
6. **Dashboard** — Superset or Streamlit displaying the metrics from the README