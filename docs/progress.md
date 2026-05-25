# Progress
 
## Project structure
 
```
project-root/
    scripts/
        ingestion/
            download_json.py
            inspect_json.py
            ingest.py
        requirements.txt
    data/
        raw/          — source JSON file from EC
        processed/    — arbitration hit results
    logs/             — process metadata and checkpoint
    docs/             — documentation
    config/
        keywords.txt  — search terms by language
```
 
---
 
## Completed steps
 
### 1. Keyword configuration (`config/keywords.txt`)
 
Each line has the format `LANG: term` where `LANG` matches the `attachmentLanguage`
field in the JSON (e.g. `EN: arbitrat*`, `ET: vahekoh*`).
 
- Wildcard `*` matches any number of characters — `arbitrat*` matches `arbitration`, `arbitral`, `arbitrator`, etc.
- AND condition: `CZ: rozhodč*:řízen*` — both terms must appear in the text
- OR condition: put each variant on its own line
- Languages sorted alphabetically (BG → SV)
- Rules that were too broad are commented out with an explanation:
  - `FR: arbitrag*` — matched economic arbitrage, not arbitration proceedings
  - `FI: välitys*` — matched `välityksellä` meaning "via/through"
  - `SV: skilje*` — matched `skiljer` meaning "differs/distinguishes"
  - `NL: arbitrag*` — same ambiguity as French
- `PT: arbitrag*` may have similar ambiguity — review Portuguese hits manually
- **To change search terms: edit this file only — no code changes needed**
---
 
### 2. JSON download (`scripts/ingestion/download_json.py`)
 
Downloads source data from:
`https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com/case-data-M.json`
 
**How it works:**
1. Downloads to a temporary file `case-data-M.json.tmp`
2. Validates the file — checks that `json.load()` succeeds and there are at least 1000 cases
3. If valid — replaces `data/raw/case-data-M.json` with the new file
4. If invalid or download fails — deletes the temporary file, leaves the existing file untouched
This means the existing file is never overwritten with a broken or incomplete download.
 
**Note:** every run re-downloads the file. Automatic refresh logic (ETag / `Last-Modified`
header check) will be added in the Airflow setup stage.
 
Run: `python scripts/ingestion/download_json.py`
 
---
 
### 3. JSON structure inspection (`scripts/ingestion/inspect_json.py`)
 
Explores the downloaded JSON and prints statistics.
 
**JSON structure:**
- Top level is a dict where key = `caseNumber` (e.g. `"M.2027"`)
- Each case contains `metadata`, `caseAttachments`, `decisions`
- `decisions` is a list — each decision has `metadata` and `decisionAttachments`
- PDF link is nested at: `decisions → decisionAttachments → metadata → attachmentLink`
- All values are wrapped in lists (e.g. `"caseNumber": ["M.2027"]`)
**Statistics printed:**
- Total cases and cases with relevant decisions
- Attachment count
- Decisions per case
- All `decisionTypes` label variants containing `6(1)(b)` or `8(2)`
- `caseRegulation` and `caseSimplified` breakdowns
- Attachment languages
- Check: `attachmentLanguage` vs `language` field consistency
- Check: `metadataReference` uniqueness (found 2 duplicates out of ~9000 — data quality issue in source)
- Sectors grouped by NACE division
- Sample case with all relevant fields
Output also saved to `scripts/ingestion/inspect_json_output.txt`.
 
Run: `python scripts/ingestion/inspect_json.py`
 
---
 
### 4. PDF search and results (`scripts/ingestion/ingest.py`)
 
#### What it does
Finds all cases with `6(1)(b)` or `8(2)` decisions, downloads their PDF attachments,
searches for arbitration keywords by language, and saves matches.
 
#### Step-by-step logic
 
**Step 1 — Load keyword rules**
Reads `config/keywords.txt` and builds a dict keyed by language code:
```
{
  "EN": [{"raw": "arbitrat*", "type": "wildcard", "pattern": <compiled regex>}],
  "CZ": [{"raw": "rozhodč*:řízen*", "type": "and", "patterns": [<regex1>, <regex2>]}],
}
```
Wildcard `*` becomes a regex that matches any non-space characters after the stem.
AND rules require all patterns to match somewhere in the text.
Patterns are compiled once at load time.
 
**Step 2 — Load JSON and filter relevant cases**
Loads `data/raw/case-data-M.json` and filters to cases that have at least one decision
whose `decisionTypes` label contains `"6(1)(b)"` or `"8(2)"` (substring match —
captures all variants including `"with conditions & obligations"`, `"Modification of"` etc.).
 
**Step 3 — Load checkpoint**
Reads `logs/checkpoint.json` if it exists. The file contains a list of PDF URLs
(`attachmentLink`) already processed in a previous run. Any PDF whose URL is in
this list is skipped without downloading.
 
If a checkpoint exists, also loads existing hits from
`data/processed/arbitration_hits.jsonl` into memory so previous matches are
included in the final output.
 
**Step 4 — Process each case**
 
For each relevant case:
 
1. **Early language skip** — collects all `attachmentLanguage` values across all PDFs
   of the case. If none of them have rules in `keywords.txt`, skips the case entirely
   without downloading any PDFs.
2. **Decision type filter** — only processes decisions whose `decisionTypes` label
   contains `"6(1)(b)"` or `"8(2)"`. Other decision types are skipped.
3. **PDF download and search** — for each PDF attachment of a qualifying decision:
   - Checks if the PDF URL is already in the checkpoint — if yes, skips it
   - Looks up keyword rules for the PDF's `attachmentLanguage`
   - If no rules exist for that language, skips the PDF (no fallback to another language)
   - Downloads the PDF and extracts all text using `pdfplumber`
   - Searches the full text using the language's rules:
     - Wildcard rule: regex pattern must match anywhere in the text
     - AND rule: all patterns must match somewhere in the text
   - Records the keyword, language and a context snippet (up to 100 characters
     before and after the match)
   - Marks the PDF URL as processed and saves the checkpoint immediately
4. **All matches collected** — all matching PDFs across all qualifying decisions
   of the case are recorded. No early stop after the first match.
5. **Record building** — if any match was found, builds the output record with:
   - Case-level fields from `metadata`
   - Only the matched decisions (not all decisions of the case)
   - Each decision includes `decisionTypes` with full `code` and `label`
   - `_matches` list: one entry per matching PDF with keyword, language, context, and PDF URL
   - `_processedAt` timestamp
**Step 5 — Write output**
After all cases are processed, writes two output files:
- `data/processed/arbitration_hits.jsonl` — one JSON object per line, for dbt
- `data/processed/arbitration_hits_readable.json` — same content, indented, for review
Test runs write to separate files (`test_arbitration_hits.*`) and never overwrite
production results.
 
**Step 6 — Write summary**
Writes `logs/ingest_summary.json`:
- `totalCases` — all cases in the JSON
- `totalRelevantCases` — cases with a `6(1)(b)` or `8(2)` decision
- `totalRelevantDecisions` — total count of those decisions
- `matchedCases` — cases where a keyword was found
- `matchedDecisions` — decisions where a keyword was found
- `processedAt` — timestamp
`matchedDecisions / totalRelevantDecisions` is used on the dashboard to show
the share of decisions with an arbitration mention.
 
**Step 7 — Clear checkpoint**
On successful completion, deletes `logs/checkpoint.json` automatically.
 
#### Checkpoint in detail
 
The checkpoint allows resuming an interrupted run without reprocessing already-completed PDFs.
It is keyed by `attachmentLink` URL (not by case or `metadataReference`) because:
- `attachmentLink` is unique per PDF file
- New PDFs added to existing cases are automatically picked up on the next run —
  their URLs are new and not in the checkpoint
| Event | What happens |
|-------|-------------|
| Process starts fresh | No checkpoint → starts from the beginning |
| After each PDF | Checkpoint rewritten with all processed PDF URLs so far |
| Process interrupted | Checkpoint contains all PDFs completed before the interruption |
| Process restarted | Checkpoint loaded → existing hits loaded → new PDFs processed |
| Process completes | Checkpoint deleted automatically |
 
**Important limitation:** hits are written to disk only at the end (Step 5). If the
process crashes before reaching that step, matches found during the interrupted run
are not recoverable — those PDFs are skipped by checkpoint on restart but their
in-progress matches are lost.
 
**Note on TEST_LIMIT:** test runs fully disable the checkpoint — it is never read or
written. Test runs always process from scratch and never interfere with a real run.
 
#### Running
```bash
# Full run
python scripts/ingestion/ingest.py
 
# Test run — first 20 cases only (Linux/macOS)
TEST_LIMIT=20 python scripts/ingestion/ingest.py
 
# Test run — first 20 cases only (Windows PowerShell)
$env:TEST_LIMIT=20; python scripts/ingestion/ingest.py
```
 
Test run output files (never overwrite production):
- `data/processed/test_arbitration_hits.jsonl`
- `data/processed/test_arbitration_hits_readable.json`
- `logs/test_ingest_summary.json`
#### First full run result
10,225 total cases — 9,038 relevant cases — 9,041 relevant decisions — 15 matches found.
 
---
 
## Known limitations
 
- **Hits written only at end** — if the process crashes before writing output files,
  matches found during that run are not recoverable. The checkpoint skips those PDFs
  on resume but their matches are lost.
- **Keyword precision** — keyword search cannot distinguish legal concepts without
  tighter rules or NLP. Some false positives are expected; review manually in
  `arbitration_hits_readable.json`.
- **No PDF download retries** — transient network failures are logged and the PDF is
  skipped. Will be addressed when Airflow retry logic is added.
- **`attachmentLanguage` consistency** — `inspect_json.py` checks that
  `attachmentLanguage` and `language` fields match; any mismatches are logged.
---
 
## Next steps
 
1. **Manual result validation** — review `arbitration_hits_readable.json` for false
   positives and refine `keywords.txt` as needed
2. **Re-run ingest** — after keyword changes, delete checkpoint (if any) and
   `arbitration_hits.jsonl` for a clean slate, then re-run
3. **dbt setup** — load `arbitration_hits.jsonl` into PostgreSQL and build
   transformation layer
4. **Docker Compose** — PostgreSQL, dbt, Airflow and Superset in containers
5. **Airflow DAG** — automated scheduler: monthly download → ingest → dbt run → dbt test
6. **Dashboard** — Superset or Streamlit displaying the metrics from the README