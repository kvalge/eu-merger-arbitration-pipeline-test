# Data dictionary
 
Describes all fields used in the pipeline — source JSON fields, output record fields,
and summary/checkpoint file fields.
 
---
 
## Source: `data/raw/case-data-M.json`
 
Top-level structure: a dict where each key is a `caseNumber` (e.g. `"M.2027"`).
 
### Case-level fields (`metadata`)
 
| Field | Type | Description |
|-------|------|-------------|
| `caseNumber` | string | Unique case identifier, e.g. `"M.2027"` |
| `caseTitle` | string | Title of the merger case, usually the merging parties |
| `caseCompanies` | list of strings | Names of the companies involved |
| `caseInstrument` | string | Always `"Merger"` in this dataset |
| `caseRegulation` | string | Legal basis, e.g. `"Council Regulation 139/2004"` |
| `caseSimplified` | string | `"Normal procedure"` or `"Simplified procedure"` |
| `caseSectors` | list of JSON strings | NACE sector codes and labels, e.g. `{"code": "NaceSectorsG_46", "label": "G.46 - Wholesale trade..."}` |
| `caseInitiationDate` | string | Date the case was opened (ISO 8601) |
| `caseNotificationDate` | string | Date the merger was notified to the Commission (ISO 8601) |
| `caseDeadlineDate` | string | Decision deadline date (ISO 8601) |
| `caseLastDecisionDate` | string | Date of the last decision in the case (ISO 8601) |
 
All source values are wrapped in single-element lists, e.g. `"caseNumber": ["M.2027"]`.
The pipeline unwraps these using `first()`.
 
### Case attachments (`caseAttachments[].metadata`)
 
| Field | Type | Description |
|-------|------|-------------|
| `metadataReference` | string | Unique identifier for the case attachment |
 
### Decision fields (`decisions[].metadata`)
 
| Field | Type | Description |
|-------|------|-------------|
| `decisionNumber` | string | Numeric part of the decision identifier, e.g. `"40398"` |
| `decisionAdoptionDate` | string | Date the decision was adopted (ISO 8601) |
| `decisionOfficialJournalPublicationsPublishedDates` | list of strings | OJ publication dates |
| `decisionTypes` | list of JSON strings | Decision type(s), each encoded as `{"code": "...", "label": "..."}` |
| `metadataReference` | string | Unique decision identifier, e.g. `"M.2027-DEC40398"` |
 
**`decisionTypes` labels relevant to this project:**
 
| Label | Meaning |
|-------|---------|
| `Art. 6(1)(b)` | Phase I clearance — no serious doubts |
| `Art. 6(1)(b) with conditions & obligations` | Phase I conditional clearance |
| `Art. 8(2)` | Phase II clearance — compatible with common market |
| `Art. 8(2) with conditions & obligations` | Phase II conditional clearance |
| `Modification of Art. 6(1)(b) with conditions & obligations` | Amendment of Phase I commitments |
| `Modification of Art. 8(2) with conditions & obligations` | Amendment of Phase II commitments |
 
The pipeline uses substring match on `"6(1)(b)"` and `"8(2)"` to capture all variants.
 
### Decision attachment fields (`decisions[].decisionAttachments[].metadata`)
 
| Field | Type | Description |
|-------|------|-------------|
| `metadataReference` | string | Unique attachment identifier, e.g. `"M.2027-DEC40398-ATT4"`. Nearly unique across the dataset — 2 duplicate values found in source data. |
| `attachmentLanguage` | string | Two-letter uppercase language code of the PDF, e.g. `"EN"`, `"FR"`, `"DE"`. Used to select keyword rules from `keywords.txt`. |
| `language` | string | Lowercase language code, e.g. `"en"`, `"fr"`. Should match `attachmentLanguage` — `inspect_json.py` checks this. |
| `attachmentName` | string | Human-readable name of the attachment |
| `attachmentLink` | string | Full URL to the PDF file. Used as the unique checkpoint ID in the pipeline. |
 
---
 
## Output: `data/processed/arbitration_hits.jsonl` / `arbitration_hits_readable.json`
 
One record per matched case. Contains case-level fields, matched decisions only,
and match metadata.
 
### Case-level fields
 
| Field | Type | Description |
|-------|------|-------------|
| `caseNumber` | string | Case identifier |
| `caseTitle` | string | Case title |
| `caseCompanies` | list of strings | Companies involved |
| `caseInstrument` | string | Always `"Merger"` |
| `caseRegulation` | string | Legal basis |
| `caseSimplified` | string | `"Normal procedure"` or `"Simplified procedure"` |
| `caseSectors` | list of strings | Parsed NACE sector labels, e.g. `"E.36.00 - Water collection, treatment and supply"` |
| `caseInitiationDate` | string | ISO 8601 date |
| `caseNotificationDate` | string | ISO 8601 date |
| `caseDeadlineDate` | string | ISO 8601 date |
| `caseLastDecisionDate` | string | ISO 8601 date |
| `caseAttachments` | list of objects | `[{"metadataReference": "..."}]` |
 
### Decision fields (only matched decisions)
 
| Field | Type | Description |
|-------|------|-------------|
| `decisionNumber` | string | Decision identifier |
| `decisionAdoptionDate` | string | ISO 8601 date |
| `decisionOfficialJournalPublicationsPublishedDates` | list of strings | OJ publication dates |
| `decisionTypes` | list of objects | `[{"code": "...", "label": "..."}]` — full type info |
| `decisionAttachments` | list of objects | All attachments of the decision (see fields below) |
 
### Decision attachment fields
 
| Field | Type | Description |
|-------|------|-------------|
| `metadataReference` | string | Attachment identifier |
| `attachmentLanguage` | string | Uppercase language code |
| `language` | string | Lowercase language code |
| `attachmentName` | string | Attachment name |
| `attachmentLink` | string | PDF URL |
 
### Match metadata fields
 
| Field | Type | Description |
|-------|------|-------------|
| `_matches` | list of objects | One entry per matching PDF (see below) |
| `_processedAt` | string | ISO 8601 timestamp of when this case was processed |
 
### `_matches` entry fields
 
| Field | Type | Description |
|-------|------|-------------|
| `dec_idx` | integer | Index of the matched decision in the `decisions` list |
| `pdfUrl` | string | URL of the PDF where the keyword was found |
| `keywords` | list of objects | One entry per matched keyword rule (see below) |
 
### `keywords` entry fields
 
| Field | Type | Description |
|-------|------|-------------|
| `keyword` | string | The matched rule from `keywords.txt`, e.g. `"arbitrat*"` |
| `language` | string | Language code the rule was applied under, e.g. `"EN"` |
| `context` | string | Up to 100 characters before and after the match in the PDF text |
 
---
 
## Process metadata: `logs/ingest_summary.json`
 
| Field | Type | Description |
|-------|------|-------------|
| `totalCases` | integer | All cases in the source JSON |
| `totalRelevantCases` | integer | Cases with at least one `6(1)(b)` or `8(2)` decision |
| `totalRelevantDecisions` | integer | Total count of `6(1)(b)` and `8(2)` decisions across relevant cases |
| `matchedCases` | integer | Cases where a keyword was found in at least one PDF |
| `matchedDecisions` | integer | Decisions where a keyword was found |
| `testLimit` | integer or null | `TEST_LIMIT` value if a test run, otherwise `null` |
| `processedAt` | string | ISO 8601 timestamp of when the run completed |
 
Dashboard metric: `matchedDecisions / totalRelevantDecisions` = share of conditional
decisions with an arbitration mention.
 
---
 
## Checkpoint: `logs/checkpoint.json`
 
| Field | Type | Description |
|-------|------|-------------|
| `processedLinks` | list of strings | PDF URLs (`attachmentLink`) already downloaded and searched. Used to skip already-processed PDFs on resume and to detect new PDFs on data refresh. |
 
The checkpoint is deleted automatically on successful completion.