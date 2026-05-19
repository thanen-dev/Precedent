#!/usr/bin/env python3
"""
Weekly scrape + extract + queue pipeline. Called by GitHub Actions.

Usage:
    python scraper/scheduler.py [--leaders hun_manet hun_sen]
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S", level=logging.INFO)
log = logging.getLogger(__name__)

ALL_LEADERS = [
    "hun_manet",
    "hun_sen",
    "aun_pornmoniroth",
    "cham_nimul",
    "chea_serey",
    "chea_vandeth",
    "hang_chuon_naron",
    "hem_vanndy",
    "say_sam_al",
    "sok_siphana",
    "sun_chanthol",
]


def _run(cmd: list[str], label: str) -> bool:
    log.info("Running: %s", label)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning("%s failed (exit %d): %s", label, result.returncode,
                    (result.stderr or result.stdout)[:300])
        return False
    if result.stdout.strip():
        log.info("%s stdout: %s", label, result.stdout.strip()[:300])
    return True


def scrape_all() -> None:
    from scraper.fetch_hun_manet       import run as fetch_hun_manet
    from scraper.fetch_hun_sen         import run as fetch_hun_sen
    from scraper.fetch_aun_pornmoniroth import run as fetch_aun
    from scraper.fetch_cham_nimul      import run as fetch_cham
    from scraper.fetch_khmer_times     import run as fetch_kt
    from scraper.fetch_phnom_penh_post import run as fetch_pp

    for name, fn in [
        ("Hun Manet (official)",   fetch_hun_manet),
        ("Hun Sen (official)",     fetch_hun_sen),
        ("Aun Pornmoniroth",       fetch_aun),
        ("Cham Nimul",             fetch_cham),
        ("Khmer Times (RSS)",      fetch_kt),
        ("Phnom Penh Post (RSS)",  fetch_pp),
    ]:
        try:
            results = fn()
            log.info("%-26s → %d new document(s)", name, len(results) if results else 0)
        except Exception as exc:
            log.warning("%-26s → FAILED: %s", name, exc)


def extract_all(leaders: list[str]) -> None:
    """Run extraction on all unprocessed raw files for each leader."""
    for leader_id in leaders:
        while True:
            result = subprocess.run(
                [sys.executable, "extractor/run_single_extract.py", "--next", leader_id],
                capture_output=True, text=True,
            )
            out = result.stdout.strip()
            if not out or "No unprocessed" in (result.stdout + result.stderr):
                break
            log.info("Extracted: %s", out)
        log.info("%-28s → extraction complete", leader_id)


def queue_extractions(leaders: list[str]) -> None:
    """Submit new extracted dimensions to the review queue."""
    from extractor.queue_submissions import run as queue_run
    for leader_id in leaders:
        try:
            count = queue_run(leader_id)
            log.info("%-28s → queued %d new claim(s)", leader_id, count)
        except Exception as exc:
            log.warning("%-28s → queue failed: %s", leader_id, exc)


def run(leaders: list[str] | None = None) -> None:
    leaders = leaders or ALL_LEADERS
    log.info("=== Weekly pipeline starting — %d leaders ===", len(leaders))

    log.info("--- Phase 1: Scrape ---")
    scrape_all()

    log.info("--- Phase 2: Extract ---")
    extract_all(leaders)

    log.info("--- Phase 3: Queue ---")
    queue_extractions(leaders)

    log.info("=== Pipeline complete. Review queue with: python tools/review.py ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly scrape + extract + queue pipeline.")
    parser.add_argument("--leaders", nargs="+", default=None,
                        help="Limit to specific leader IDs (default: all)")
    args = parser.parse_args()
    run(leaders=args.leaders)


if __name__ == "__main__":
    main()
