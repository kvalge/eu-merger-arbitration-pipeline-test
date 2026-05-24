"""
Explores the structure of the downloaded JSON file.
Focuses on Art. 6(1)(b) and Art. 8(2) decisions and relevant fields only.
Output is printed to the console and saved to inspect_json_output.txt
in the same folder. Re-running overwrites the file.
 
Run after download_json.py:
    python ingestion/inspect_json.py
"""
 
import json
from collections import Counter
from io import StringIO
from pathlib import Path
 
JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "case-data-M.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "inspect_json_output.txt"
 
SEP = "=" * 60
DECISION_TYPES_OF_INTEREST = {"Art. 6(1)(b)", "Art. 8(2)"}
 
 
def first(lst):
    """Returns the first element of a list, or None if empty."""
    return lst[0] if lst else None
 
 
def parse_label(raw):
    """Parses a JSON-encoded label string, falls back to raw value."""
    try:
        return json.loads(raw).get("label", raw)
    except (json.JSONDecodeError, AttributeError):
        return raw
 
 
def case_has_relevant_decision(case):
    """Returns True if the case has at least one Art. 6(1)(b) or Art. 8(2) decision."""
    for dec in case.get("decisions", []):
        for raw in dec.get("metadata", {}).get("decisionTypes", []):
            if parse_label(raw) in DECISION_TYPES_OF_INTEREST:
                return True
    return False
 
 
def main() -> None:
    if not JSON_PATH.exists():
        print(f"[!] File not found: {JSON_PATH}")
        print("    Run first: python ingestion/download_json.py")
        return
 
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
 
    buf = StringIO()
 
    def out(text=""):
        print(text)
        buf.write(text + "\n")
 
    all_cases = list(data.values())
    relevant_cases = [c for c in all_cases if case_has_relevant_decision(c)]
 
    # --- Totals ---
    out(f"\n{SEP}")
    out(f"Total cases in file:                        {len(all_cases)}")
    out(f"Cases with Art. 6(1)(b) or Art. 8(2):      {len(relevant_cases)}")
 
    # --- Decisions per relevant case ---
    out(f"\n{SEP}")
    out("Decisions per relevant case:")
    dec_counts = Counter(len(c.get("decisions", [])) for c in relevant_cases)
    for count, freq in sorted(dec_counts.items()):
        out(f"  {count} decision(s): {freq} cases")
 
    # --- Decision type breakdown (relevant cases only) ---
    out(f"\n{SEP}")
    out("Decision types in relevant cases:")
    dec_types = Counter()
    for case in relevant_cases:
        for dec in case.get("decisions", []):
            for raw in dec.get("metadata", {}).get("decisionTypes", []):
                label = parse_label(raw)
                if label in DECISION_TYPES_OF_INTEREST:
                    dec_types[label] += 1
    for dtype, cnt in dec_types.most_common():
        out(f"  {dtype:50s} {cnt:6d}")
 
    # --- caseRegulation breakdown ---
    out(f"\n{SEP}")
    out("caseRegulation breakdown (relevant cases):")
    regulations = Counter(
        first(c.get("metadata", {}).get("caseRegulation", [])) or "unknown"
        for c in relevant_cases
    )
    for reg, cnt in regulations.most_common():
        out(f"  {reg:50s} {cnt:6d}")
 
    # --- caseSimplified breakdown ---
    out(f"\n{SEP}")
    out("caseSimplified breakdown (relevant cases):")
    simplified = Counter(
        first(c.get("metadata", {}).get("caseSimplified", [])) or "unknown"
        for c in relevant_cases
    )
    for val, cnt in simplified.most_common():
        out(f"  {val:50s} {cnt:6d}")
 
    # --- caseSectors breakdown grouped by NACE division ---
    out(f"\n{SEP}")
    out("Sectors by NACE division (relevant cases):")
    import re as _re
    division_labels = {}
    division_counts = Counter()
    for case in relevant_cases:
        for raw in case.get("metadata", {}).get("caseSectors", []):
            label = parse_label(raw)
            # Extract division from label, e.g. 'G.46 - Wholesale trade...' -> 'G.46'
            m = _re.match(r'^([A-Z]\.\d+)', label)
            if m:
                division = m.group(1)
                if division not in division_labels:
                    division_labels[division] = label.split(' - ', 1)[1].strip() if ' - ' in label else label
                division_counts[division] += 1
            else:
                division_counts[label] += 1
    # Align counts: pad division+description to a fixed width
    col_width = max((len(f"{div}  {division_labels.get(div, '')}") for div in division_counts), default=40) + 2
    for division, cnt in sorted(division_counts.items(), key=lambda x: (x[0][0], int(x[0][1:].split('.')[1]) if len(x[0]) > 1 and x[0][1:].lstrip('.').split('.')[0].isdigit() else 0)):
        desc = division_labels.get(division, '')
        line = f"{division}  {desc}"
        out(f"  {line:<{col_width}} {cnt:6d}")
 
    # --- Attachment languages (relevant cases only) ---
    out(f"\n{SEP}")
    out("Attachment languages in relevant cases (all, sorted by count):")
    att_langs = Counter()
    for case in relevant_cases:
        for dec in case.get("decisions", []):
            for att in dec.get("decisionAttachments", []):
                lang = first(att.get("metadata", {}).get("attachmentLanguage", []))
                att_langs[lang or "unknown"] += 1
    for lang, cnt in att_langs.most_common():
        out(f"  {lang:10s} {cnt:6d}")
 
    # --- Attachments count ---
    out(f"\n{SEP}")
    cases_with_att = sum(
        1 for case in relevant_cases
        if any(dec.get("decisionAttachments") for dec in case.get("decisions", []))
    )
    total_att = sum(
        len(dec.get("decisionAttachments", []))
        for case in relevant_cases
        for dec in case.get("decisions", [])
    )
    out(f"Relevant cases with at least one attachment: {cases_with_att}")
    out(f"Total decision attachments in relevant cases: {total_att}")
 
    # --- Sample case ---
    out(f"\n{SEP}")
    out("Sample relevant case (first match):")
    sample = relevant_cases[0]
    meta = sample.get("metadata", {})
    out(f"  caseNumber:           {first(meta.get('caseNumber', []))}")
    out(f"  caseTitle:            {first(meta.get('caseTitle', []))}")
    out(f"  caseCompanies:        {meta.get('caseCompanies', [])}")
    out(f"  caseInstrument:       {first(meta.get('caseInstrument', []))}")
    out(f"  caseRegulation:       {first(meta.get('caseRegulation', []))}")
    out(f"  caseSimplified:       {first(meta.get('caseSimplified', []))}")
    out(f"  caseSectors:          {[parse_label(s) for s in meta.get('caseSectors', [])]}")
    out(f"  caseInitiationDate:   {first(meta.get('caseInitiationDate', []))}")
    out(f"  caseNotificationDate: {first(meta.get('caseNotificationDate', []))}")
    out(f"  caseDeadlineDate:     {first(meta.get('caseDeadlineDate', []))}")
    out(f"  caseLastDecisionDate: {first(meta.get('caseLastDecisionDate', []))}")
 
    out(f"\n  caseAttachments ({len(sample.get('caseAttachments', []))}):")
    for ca in sample.get("caseAttachments", []):
        cam = ca.get("metadata", {})
        out(f"    metadataReference: {first(cam.get('metadataReference', []))}")
 
    out(f"\n  decisions ({len(sample.get('decisions', []))}):")
    for i, dec in enumerate(sample.get("decisions", [])):
        dm = dec.get("metadata", {})
        types = [parse_label(r) for r in dm.get("decisionTypes", [])]
        out(f"    decision[{i}]:")
        out(f"      decisionNumber:      {first(dm.get('decisionNumber', []))}")
        out(f"      decisionAdoptionDate: {first(dm.get('decisionAdoptionDate', []))}")
        out(f"      decisionOJPublishedDates: {dm.get('decisionOfficialJournalPublicationsPublishedDates', [])}")
        out(f"      decisionTypes:       {types}")
        out(f"      decisionAttachments ({len(dec.get('decisionAttachments', []))}):")
        for att in dec.get("decisionAttachments", []):
            am = att.get("metadata", {})
            out(f"        metadataReference:  {first(am.get('metadataReference', []))}")
            out(f"        attachmentLanguage: {first(am.get('attachmentLanguage', []))}")
            out(f"        language:           {first(am.get('language', []))}")
            out(f"        attachmentName:     {first(am.get('attachmentName', []))}")
            out(f"        attachmentLink:     {first(am.get('attachmentLink', []))}")
 
    # --- Save to file ---
    OUTPUT_PATH.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\nOutput saved to: {OUTPUT_PATH}")
 
 
if __name__ == "__main__":
    main()