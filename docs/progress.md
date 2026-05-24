# Progress
 
## Tehtud
 
### 1. Projekti alus
- Loodud projekti kaustapuu:
  - `ingestion/` — andmete allalaadimise ja töötlemise skriptid
  - `config/` — seadistusfailid (nt otsisõnade nimekiri)
  - `data/raw/` — allalaaditud töötlemata sisendandmed
  - `data/processed/` — töötlustulemused
  - `logs/` — protsessi metainfo
  - `docs/` — dokumentatsioon
- Loodud `requirements.txt` — projekti Pythoni teekide nimekiri
- `.gitignore` seadistatud — virtuaalkeskkond, cache-failid ja IDE failid jäetakse gitist välja
### 2. Otsisõnade fail (`config/keywords.txt`)
- Loodud `config/keywords.txt`, kuhu on kirja pandud vahekohtu-terminid EL keeltes
- Iga rida on kujul `KEELEKOOD: termin` (nt `EN: arbitrat*`, `ET: vahekoh*`)
- Tärniga (`*`) saab otsida sõnatüve — nt `arbitrat*` leiab nii `arbitration` kui `arbitral`
- Kahe sõna AND-tingimus: `CZ: rozhodč*:řízen*` — mõlemad peavad tekstis esinema
- Iga PDF otsitakse läbi selle keele reeglitega, mis on märgitud JSON-is `attachmentLanguage` väljal
- **Otsisõnade muutmiseks muuda ainult seda faili — koodi muutma ei pea**
### 3. Andmete allalaadimine (`ingestion/download_json.py`)
- Skript laeb Euroopa Komisjoni koondumisotsuste JSON-faili alla aadressilt:
  `https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com/case-data-M.json`
- Salvestab faili `data/raw/case-data-M.json`
- Kui fail on juba olemas, ei lae uuesti alla
- Käivitamine: `python ingestion/download_json.py`
### 4. JSON-i struktuuri uurimine (`ingestion/inspect_json.py`)
- Skript loeb allalaetud JSON-faili struktuuri ja prindib statistika
- JSON-i ülesehitus:
  - Tipp on dict, kus võti = `caseNumber` (nt `"M.2027"`)
  - Iga case sisaldab `metadata`, `caseAttachments`, `decisions`
  - Otsused (`decisions`) on list — igal otsusel on `metadata` ja `decisionAttachments`
  - Otsuse PDF-link asub: `decisions → decisionAttachments → metadata → attachmentLink`
  - Kõik väärtused on listid (nt `"caseNumber": ["M.2027"]`)
- Skript filtreerib ainult Art. 6(1)(b) ja Art. 8(2) otsuseid sisaldavaid case'id
- Väljastab statistika: otsuste tüübid, sektorid (NACE divisjoni tasemel), attachment-keeled
- Salvestab väljundi `ingestion/inspect_json_output.txt`
- Käivitamine: `python ingestion/inspect_json.py`
### 5. PDF-ide otsimine ja tulemuste salvestamine (`ingestion/ingest.py`)
- Skript käib läbi kõik relevantsed case'id (Art. 6(1)(b) või Art. 8(2) otsusega)
- Iga case kohta:
  1. Leiab otsuse külge lisatud PDF-failid
  2. Laeb PDF alla
  3. Otsib PDF-ist otsisõnu — keele järgi (nt prantsuskeelsest PDF-ist otsitakse `arbitrag*`)
  4. Kui sõna leitakse, salvestatakse case'i andmed tulemuste faili
- Tulemused salvestatakse kahes formaadis:
  - `data/processed/arbitration_hits.jsonl` — masinloetav, üks kirje rea kohta (dbt jaoks)
  - `data/processed/arbitration_hits_readable.json` — inimloetav, taandega
- Protsessi statistika salvestatakse `logs/ingest_summary.json`:
  - kõigi case'ide arv, relevantsete otsuste koguarv, hits arv
  - kasutatakse hiljem dashboardil osakaalu arvutamiseks (`matchedDecisions / totalRelevantDecisions`)
- Skript töötab lihtsalt järjest (üks PDF korraga) — lihtne debugida
- Testimiseks saab piirata töödeldavate case'ide arvu: `TEST_LIMIT=5 python ingestion/ingest.py`
- Käivitamine: `python ingestion/ingest.py`
---
 
## Järgmised sammud
 
1. **Katkestuse korral taasalustamine** — lisada `ingest.py`-sse checkpoint-loogika,
   et kui protsess katkeb, ei pea otsast alustama
2. **Andmete uuendamine** — lisada loogika, et ainult uued või muutunud kirjed
   protsessitakse uuesti (mitte kogu andmestik)
3. **dbt seadistamine** — `arbitration_hits.jsonl` laadimine PostgreSQL-i ja
   transformatsioonikihi ehitamine
4. **Docker Compose** — PostgreSQL, dbt, Airflow ja Superset konteinerites
5. **Airflow DAG** — automaatne ajaplaneerija: kord kuus ingest → dbt → test
6. **Dashboard** — Superset või Streamlit, kuvab mõõdikud README-st
 