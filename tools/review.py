#!/usr/bin/env python3
"""
Interactive queue reviewer. Run from any terminal.

Usage:
    python tools/review.py
    python tools/review.py --status approved   # review approved items
    python tools/review.py --type brief_draft  # only brief drafts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.queue import approve, list_queue, reject


def _fmt(item: dict) -> str:
    lines = [
        f"\n{'='*72}",
        f"ID:         {item['id']}",
        f"Type:       {item['type']}",
        f"Leader:     {item['leader_id']}",
        f"Dimension:  {item.get('dimension', '—')}",
        f"Date:       {item['source_date']}",
        f"Confidence: {item.get('confidence', 0):.0%}",
        f"URL:        {item['source_url']}",
        f"",
        f"CLAIM:",
        f"  {item['extracted_claim']}",
    ]
    if item.get("exact_quote"):
        lines += [f"", f"QUOTE:", f'  "{item["exact_quote"]}"']
    if item.get("reviewer_notes"):
        lines += [f"", f"NOTES: {item['reviewer_notes']}"]
    lines.append(f"{'='*72}")
    return "\n".join(lines)


def run_review(status: str = "pending", item_type: str | None = None) -> None:
    items = list_queue(status)  # type: ignore[arg-type]
    if item_type:
        items = [i for i in items if i.get("type") == item_type]

    if not items:
        print(f"\nNo {status} items{' of type ' + item_type if item_type else ''}.\n")
        return

    print(f"\n{len(items)} item(s) to review.\n")
    approved_count = rejected_count = skipped_count = 0

    for i, item in enumerate(items, 1):
        print(f"[{i}/{len(items)}] {_fmt(item)}")
        while True:
            choice = input("\n  [a]pprove  [r]eject  [s]kip  [q]uit  [v]iew raw > ").strip().lower()
            if choice == "a":
                notes = input("  Notes (optional): ").strip()
                approve(item["id"], notes)
                print("  → APPROVED")
                approved_count += 1
                break
            elif choice == "r":
                reason = input("  Reason (required): ").strip()
                if not reason:
                    print("  Reason is required to reject.")
                    continue
                reject(item["id"], reason)
                print("  → REJECTED")
                rejected_count += 1
                break
            elif choice == "s":
                skipped_count += 1
                break
            elif choice == "q":
                print(f"\nStopped. A:{approved_count} R:{rejected_count} S:{skipped_count}\n")
                return
            elif choice == "v":
                print(json.dumps(item, indent=2))
            else:
                print("  Enter a / r / s / q / v")

    print(f"\nDone. Approved:{approved_count}  Rejected:{rejected_count}  Skipped:{skipped_count}\n")
    if approved_count:
        print("Run `python tools/merge_approved.py` to merge approved items into profiles.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive queue reviewer.")
    parser.add_argument("--status", default="pending", choices=["pending", "approved", "rejected"])
    parser.add_argument("--type", dest="item_type", default=None,
                        help="Filter by item type, e.g. claim_extraction or brief_draft")
    args = parser.parse_args()
    run_review(status=args.status, item_type=args.item_type)


if __name__ == "__main__":
    main()
