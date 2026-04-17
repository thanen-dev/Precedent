#!/usr/bin/env python3
"""
Merge extracted document evidence into a leader's master profile JSON.

Design
------
Extracted docs (data/extracted/<leader_id>/*.json) contain per-dimension
findings produced by claude_client.extract_fields(). This script appends
those findings as evidence entries inside each dimension's '_evidence' list
in the master profile (data/leaders/<leader_id>_profile.json).

The hand-curated dimension content (core_thesis, stated_theory, etc.) is
never touched. Evidence is additive only.

Merge rule (per evidence entry):
  - If no entry for this source URL exists in _evidence → append.
  - If an entry for this URL already exists AND new confidence is strictly
    higher → replace.
  - Otherwise → skip (keep existing higher-confidence entry).

Usage
-----
    # Merge all extracted docs for a leader
    python extractor/merge_profile.py hun_manet

    # Preview without writing
    python extractor/merge_profile.py hun_manet --dry-run

    # Re-read already-merged docs (for re-extraction with updated prompt)
    python extractor/merge_profile.py hun_manet --force
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as Date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from extractor.schema import DIMENSION_KEYS, LeaderProfile

log = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

PROJECT_ROOT = Path(__file__).parent.parent
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"
LEADERS_DIR   = PROJECT_ROOT / "data" / "leaders"

# Sentinel file tracking which extracted docs have been merged
MERGED_LEDGER_NAME = ".merged"


# ── ledger (idempotency) ──────────────────────────────────────────────────────

def _ledger_path(leader_id: str) -> Path:
    return EXTRACTED_DIR / leader_id / MERGED_LEDGER_NAME


def _load_ledger(leader_id: str) -> set[str]:
    """Return set of already-merged extracted filenames."""
    p = _ledger_path(leader_id)
    if not p.exists():
        return set()
    return set(p.read_text(encoding="utf-8").splitlines())


def _save_ledger(leader_id: str, merged: set[str]) -> None:
    p = _ledger_path(leader_id)
    p.write_text("\n".join(sorted(merged)), encoding="utf-8")


# ── evidence merge logic ──────────────────────────────────────────────────────

def _should_upsert(existing_entries: list[dict], new_entry: dict) -> tuple[bool, int | None]:
    """
    Decide whether to append or replace.

    Returns (should_write, index_to_replace).
    index_to_replace is None when appending.
    """
    url = new_entry["url"]
    for i, entry in enumerate(existing_entries):
        if entry.get("url") == url:
            if new_entry["confidence"] > entry.get("confidence", 0.0):
                return True, i       # replace: strictly higher confidence
            return False, i          # skip: existing is same or better
    return True, None                # append: URL not seen before


def _merge_dimension(
    dimension_dict: dict,
    dim_key: str,
    new_entry: dict,
) -> tuple[str, str | None]:
    """
    Insert new_entry into dimension_dict['_evidence'].

    Returns (action, reason) where action is 'appended', 'replaced', or 'skipped'.
    """
    if "_evidence" not in dimension_dict:
        dimension_dict["_evidence"] = []

    entries: list[dict] = dimension_dict["_evidence"]
    should_write, idx = _should_upsert(entries, new_entry)

    if not should_write:
        existing_conf = entries[idx].get("confidence", 0.0) if idx is not None else 0.0
        return "skipped", f"existing confidence {existing_conf:.2f} >= {new_entry['confidence']:.2f}"

    if idx is not None:
        entries[idx] = new_entry
        return "replaced", f"confidence {new_entry['confidence']:.2f} > previous"

    entries.append(new_entry)
    return "appended", None


# ── extracted doc loading ─────────────────────────────────────────────────────

def _load_extracted(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_evidence_entry(field_data: dict, meta: dict) -> dict:
    """
    Build a single evidence entry from extracted field data + doc metadata.

    Shape written into _evidence:
    {
        "url":        str,
        "date":       str,
        "quote":      str,
        "value":      str,
        "confidence": float,
        "source_file": str
    }
    """
    source = field_data.get("source", {})
    return {
        "url":         source.get("url")        or meta.get("source_url", ""),
        "date":        source.get("date")        or meta.get("source_date", ""),
        "quote":       source.get("quote", ""),
        "value":       field_data.get("value",   ""),
        "confidence":  source.get("confidence", 0.0),
        "source_file": meta.get("source_file",  ""),
    }


def _is_valid_entry(entry: dict) -> bool:
    """Reject entries missing any of the required provenance fields."""
    return all([
        entry.get("url"),
        entry.get("date"),
        entry.get("quote"),
        entry.get("value"),
    ])


# ── merge orchestration ───────────────────────────────────────────────────────

def merge_one(
    extracted_path: Path,
    profile: dict,
    dry_run: bool,
) -> dict[str, str]:
    """
    Merge evidence from one extracted doc into the profile dict (in-place).

    Returns a summary dict: {dim_key: action_string}.
    """
    doc = _load_extracted(extracted_path)
    meta = doc.get("_meta", {})
    actions: dict[str, str] = {}

    for dim_key in DIMENSION_KEYS:
        field_data = doc.get(dim_key)
        if field_data is None:
            continue

        entry = _build_evidence_entry(field_data, meta)

        if not _is_valid_entry(entry):
            log.warning(
                "  [%s] Skipping incomplete entry (missing url/date/quote/value): %s",
                dim_key, extracted_path.name,
            )
            actions[dim_key] = "invalid"
            continue

        dim_dict = profile["dimensions"].get(dim_key)
        if dim_dict is None:
            log.warning("  [%s] Dimension missing from profile — skipping", dim_key)
            actions[dim_key] = "no_dimension"
            continue

        action, reason = _merge_dimension(dim_dict, dim_key, entry)
        note = f" ({reason})" if reason else ""
        log.info("  [%s] %s%s", dim_key, action, note)
        actions[dim_key] = action

    return actions


def merge_all(
    leader_id: str,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    extracted_dir = EXTRACTED_DIR / leader_id
    if not extracted_dir.exists():
        log.error("No extracted docs found at %s", extracted_dir)
        sys.exit(1)

    profile_path = LEADERS_DIR / f"{leader_id}_profile.json"
    if not profile_path.exists():
        log.error("Profile not found: %s", profile_path)
        sys.exit(1)

    # Load and validate profile before touching it
    profile_raw = json.loads(profile_path.read_text(encoding="utf-8"))
    try:
        LeaderProfile.model_validate(profile_raw)
    except Exception as exc:
        log.error("Profile failed schema validation: %s", exc)
        sys.exit(1)

    ledger = _load_ledger(leader_id) if not force else set()
    docs = sorted(extracted_dir.glob("*.json"))

    if not docs:
        log.warning("No extracted JSON files found in %s", extracted_dir)
        return

    total_appended = total_replaced = total_skipped = 0
    newly_merged: set[str] = set()

    for doc_path in docs:
        if doc_path.name in ledger:
            log.info("Already merged: %s", doc_path.name)
            continue

        log.info("Merging: %s", doc_path.name)
        actions = merge_one(doc_path, profile_raw, dry_run=dry_run)

        for action in actions.values():
            if action == "appended":   total_appended  += 1
            elif action == "replaced": total_replaced  += 1
            elif action == "skipped":  total_skipped   += 1

        newly_merged.add(doc_path.name)

    if dry_run:
        log.info(
            "DRY-RUN complete. Would append=%d replace=%d skip=%d",
            total_appended, total_replaced, total_skipped,
        )
        return

    # Write updated profile
    profile_raw["updated"] = str(Date.today())
    profile_path.write_text(
        json.dumps(profile_raw, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Profile written: %s", profile_path.relative_to(PROJECT_ROOT))

    # Update ledger
    ledger.update(newly_merged)
    _save_ledger(leader_id, ledger)

    log.info(
        "Done. appended=%d replaced=%d skipped=%d from %d doc(s)",
        total_appended, total_replaced, total_skipped, len(newly_merged),
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge extracted evidence into a leader profile JSON."
    )
    parser.add_argument("leader_id", help="Snake-case leader ID, e.g. hun_manet")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be merged without writing",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-merge even already-ledgered docs",
    )
    args = parser.parse_args()
    merge_all(args.leader_id, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
