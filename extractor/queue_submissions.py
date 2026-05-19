#!/usr/bin/env python3
"""
Compare latest extracted data against current published profiles and
submit changed/new dimensions to the review queue.

Usage:
    python extractor/queue_submissions.py [leader_id ...]
    python extractor/queue_submissions.py hun_manet hun_sen
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.queue import submit, list_queue

logging.basicConfig(format="%(levelname)-8s  %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

PROJECT_ROOT  = Path(__file__).parent.parent
LEADERS_DIR   = PROJECT_ROOT / "data" / "leaders"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"

DIM_KEYS = [
    "growth_theory",
    "risk_tolerance",
    "time_horizon",
    "dependency_assumptions",
    "institution_vs_relationship",
    "global_positioning_logic",
    "consistency_score",
]


def _load_profile(leader_id: str) -> dict:
    path = LEADERS_DIR / f"{leader_id}_profile.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _latest_extractions(leader_id: str) -> list[dict]:
    """Return all extracted documents for a leader, newest first."""
    ext_dir = EXTRACTED_DIR / leader_id
    if not ext_dir.exists():
        return []
    files = sorted(ext_dir.glob("*.json"), reverse=True)
    docs = []
    for f in files:
        try:
            docs.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return docs


def _already_queued(leader_id: str, dimension: str, source_url: str) -> bool:
    """Check if this exact (leader, dimension, source) is already pending."""
    for item in list_queue("pending"):
        if (item.get("leader_id") == leader_id
                and item.get("dimension") == dimension
                and item.get("source_url") == source_url):
            return True
    return False


def run(leader_id: str) -> int:
    profile = _load_profile(leader_id)
    pub_dims = profile.get("dimensions", {})
    extractions = _latest_extractions(leader_id)

    if not extractions:
        log.info("%s: no extractions found", leader_id)
        return 0

    queued = 0
    for doc in extractions:
        meta = doc.get("_meta", {})
        source_url  = meta.get("source_url", "")
        source_date = meta.get("source_date", "")

        for dim in DIM_KEYS:
            if dim not in doc:
                continue
            ext_dim = doc[dim]
            if not isinstance(ext_dim, dict):
                continue

            # extract assessed position
            position = ""
            for field in ("assessed_position", "core_thesis", "position", "summary"):
                v = ext_dim.get(field, "")
                if isinstance(v, str) and len(v) > 20:
                    position = v
                    break
            if not position:
                continue

            # extract confidence
            conf = ext_dim.get("confidence", 0.0)
            if isinstance(conf, str):
                try:
                    conf = float(conf)
                except ValueError:
                    conf = 0.5

            # check if this is new or higher-confidence than published
            pub = pub_dims.get(dim, {})
            pub_pos  = pub.get("assessed_position", pub.get("position", "")) if isinstance(pub, dict) else ""
            pub_conf = pub.get("confidence", 0.0) if isinstance(pub, dict) else 0.0

            if position[:80] == pub_pos[:80] and conf <= pub_conf:
                continue  # nothing new

            if _already_queued(leader_id, dim, source_url):
                continue

            exact_quote = ""
            for fld in ("exact_quote", "primary_quote", "quote"):
                q = ext_dim.get(fld, "")
                if isinstance(q, str) and len(q) > 10:
                    exact_quote = q
                    break

            item_id = submit(
                item_type="claim_extraction",
                leader_id=leader_id,
                dimension=dim,
                source_url=source_url,
                source_date=source_date,
                extracted_claim=position[:500],
                exact_quote=exact_quote[:300],
                confidence=conf,
            )
            log.info("Queued: %s → %s.%s (conf %.0f%%)", item_id, leader_id, dim, conf * 100)
            queued += 1

    return queued


def main() -> None:
    leaders = sys.argv[1:] if len(sys.argv) > 1 else []
    if not leaders:
        # default: all leaders that have extraction data
        leaders = [p.name for p in EXTRACTED_DIR.iterdir() if p.is_dir()] if EXTRACTED_DIR.exists() else []

    total = 0
    for lid in sorted(leaders):
        n = run(lid)
        total += n
    log.info("Total queued: %d", total)


if __name__ == "__main__":
    main()
