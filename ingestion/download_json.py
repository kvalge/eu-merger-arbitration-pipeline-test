"""
Downloads the European Commission merger decisions JSON file
and saves it to data/raw/case-data-M.json.
"""
 
import logging
from pathlib import Path
 
import requests
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
 
URL = "https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com/case-data-M.json"
DEST = Path(__file__).resolve().parent.parent / "data" / "raw" / "case-data-M.json"
 
 
def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
 
    if DEST.exists():
        log.info("File already exists: %s (%.1f MB)", DEST, DEST.stat().st_size / 1e6)
        log.info("Delete the file and re-run to force a fresh download.")
        return
 
    log.info("Downloading: %s", URL)
    resp = requests.get(URL, timeout=120)
    resp.raise_for_status()
    DEST.write_bytes(resp.content)
    log.info("Saved: %s (%.1f MB)", DEST, DEST.stat().st_size / 1e6)
 
 
if __name__ == "__main__":
    main()