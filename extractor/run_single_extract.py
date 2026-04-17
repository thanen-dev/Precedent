#!/usr/bin/env python3
"""
Extract mental-model fields from one raw document and write to data/extracted/.

Raw file convention (set by the scraper)
-----------------------------------------
Each file in data/raw/<leader_id>/ is a JSON envelope:
    {
        "url":   "https://...",
        "date":  "YYYY-MM-DD",
        "title": "...",
        "text":  "<full document text>"
    }

Output
------
    data/extracted/<leader_id>/<date>_<stem>.json

Idempotency
-----------
If the output file already exists the script exits 0 without calling the API.

Usage
-----
    # Process a specific file
    python extractor/run_single_extract.py data/raw/hun_manet/2024-08-17_speech.json

    # Auto-pick the next unprocessed file
    python extractor/run_single_extract.py --next hun_manet
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as Date
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from extractor.claude_client import extract_fields

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"


# ── raw file helpers ──────────────────────────────────────────────────────────

def load_raw(path: Path) -> dict:
    """Load and minimally validate a raw document envelope."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in ("url", "date", "text"):
        if not raw.get(key):
            raise ValueError(f"Raw file missing required field '{key}': {path}")
    return raw


def output_path(leader_id: str, doc_date: str, stem: str) -> Path:
    """Derive the canonical output path for a given raw file."""
    return EXTRACTED_DIR / leader_id / f"{doc_date}_{stem}.json"


# ── idempotency ───────────────────────────────────────────────────────────────

def already_extracted(out: Path) -> bool:
    if out.exists():
        logger.info("Skip — output already exists: %s", out)
        return True
    return False


# ── next-file picker ──────────────────────────────────────────────────────────

def find_next_unprocessed(leader_id: str) -> Path | None:
    """Return the first raw file that has no corresponding extracted output."""
    raw_leader_dir = RAW_DIR / leader_id
    if not raw_leader_dir.exists():
        return None

    candidates = sorted(raw_leader_dir.glob("*.json"))
    for candidate in candidates:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
        doc_date = raw.get("date", "unknown")
        out = output_path(leader_id, doc_date, candidate.stem)
        if not out.exists():
            return candidate

    return None


# ── core pipeline ─────────────────────────────────────────────────────────────

def run(raw_path: Path) -> Path:
    """
    Load raw_path → extract fields → write output JSON.

    Returns the output path that was written.
    Skips without API call if output already exists.
    """
    leader_id = raw_path.parent.name          # e.g. "hun_manet"
    raw = load_raw(raw_path)

    doc_date: str = raw["date"]
    out = output_path(leader_id, doc_date, raw_path.stem)

    if already_extracted(out):
        return out

    logger.info(
        "Extracting: leader=%s  date=%s  url=%s",
        leader_id, doc_date, raw["url"],
    )

    fields = extract_fields(
        document=raw["text"],
        leader_id=leader_id,
        source_url=raw["url"],
        source_date=doc_date,
    )

    populated = list(fields.keys())
    logger.info("Fields populated: %s", populated if populated else "none")

    out.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "_meta": {
            "leader_id": leader_id,
            "source_file": raw_path.name,
            "source_url": raw["url"],
            "source_date": doc_date,
            "extracted_on": str(Date.today()),
            "fields_found": populated,
        },
        **fields,
    }

    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Written: %s", out)
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract mental-model fields from one raw document."
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "file",
        nargs="?",
        type=Path,
        help="Path to a raw JSON document, e.g. data/raw/hun_manet/2024-08-17_speech.json",
    )
    group.add_argument(
        "--next",
        metavar="LEADER_ID",
        help="Auto-pick the next unprocessed file for this leader, e.g. hun_manet",
    )

    args = parser.parse_args()

    if args.next:
        raw_path = find_next_unprocessed(args.next)
        if raw_path is None:
            logger.info("No unprocessed files found for leader '%s'.", args.next)
            sys.exit(0)
    else:
        raw_path = args.file

    try:
        out = run(raw_path)
        print(out)
    except (ValueError, KeyError) as exc:
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
