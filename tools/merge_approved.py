#!/usr/bin/env python3
"""
Merge all approved queue items into their leader profiles.
Run after approving items in sunday_review.py.

Usage:
    python tools/merge_approved.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.queue import APPROVED_DIR, PROJECT_ROOT, list_queue

logging.basicConfig(format="%(levelname)-8s  %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

LEADERS_DIR = PROJECT_ROOT / "data" / "leaders"


def load_profile(leader_id: str) -> dict:
    path = LEADERS_DIR / f"{leader_id}_profile.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"id": leader_id, "dimensions": {}}


def save_profile(leader_id: str, profile: dict, dry_run: bool) -> None:
    path = LEADERS_DIR / f"{leader_id}_profile.json"
    if dry_run:
        log.info("[DRY RUN] Would write %s", path)
        return
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False))
    log.info("Written: %s", path)


def merge_claim(profile: dict, item: dict) -> bool:
    """Merge a claim_extraction item into a profile. Returns True if profile changed."""
    dim = item.get("dimension")
    if not dim:
        return False

    dims = profile.setdefault("dimensions", {})
    existing = dims.get(dim, {})

    new_conf = item.get("confidence", 0.0)
    old_conf  = existing.get("confidence", 0.0) if isinstance(existing, dict) else 0.0

    if new_conf <= old_conf and existing:
        log.info("Skip merge — existing confidence %.2f >= new %.2f for %s.%s",
                 old_conf, new_conf, item["leader_id"], dim)
        return False

    dims[dim] = {
        "assessed_position": item["extracted_claim"],
        "exact_quote":       item.get("exact_quote", ""),
        "source_url":        item["source_url"],
        "source_date":       item["source_date"],
        "confidence":        new_conf,
        "merged_from_queue": item["id"],
    }
    return True


def run(dry_run: bool = False) -> int:
    approved = list_queue("approved")
    if not approved:
        log.info("No approved items to merge.")
        return 0

    profiles: dict[str, dict] = {}
    changed: dict[str, bool] = {}

    for item in approved:
        lid = item["leader_id"]
        if lid not in profiles:
            profiles[lid] = load_profile(lid)
            changed[lid] = False

        item_type = item.get("type", "claim_extraction")
        if item_type == "claim_extraction":
            if merge_claim(profiles[lid], item):
                changed[lid] = True
                log.info("Merged: %s → %s.%s", item["id"], lid, item.get("dimension"))
        elif item_type == "brief_draft":
            log.info("Brief draft %s — handled by generate_brief.py, skipping merge.", item["id"])
        else:
            log.warning("Unknown item type '%s' for %s — skipping.", item_type, item["id"])

    for lid, profile in profiles.items():
        if changed[lid]:
            save_profile(lid, profile, dry_run)

    merged_count = sum(changed.values())
    log.info("Merged %d profile(s) from %d approved item(s).", merged_count, len(approved))
    return merged_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge approved queue items into leader profiles.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, don't write.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
