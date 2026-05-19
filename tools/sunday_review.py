#!/usr/bin/env python3
"""
Sunday Review — your 30-minute weekly session.
Walks through queue items, brief drafts, and prediction checks in order.

Usage:
    python tools/sunday_review.py
    python tools/sunday_review.py --quick   # skip detail prompts
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent


def _counts() -> dict:
    from tools.queue import list_queue
    return {
        "pending":  list_queue("pending"),
        "approved": list_queue("approved"),
        "rejected": list_queue("rejected"),
    }


def _header(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def _show_dashboard(queues: dict) -> None:
    pending = queues["pending"]
    types: dict[str, int] = {}
    for item in pending:
        t = item.get("type", "unknown")
        types[t] = types.get(t, 0) + 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  PRECEDENT — SUNDAY REVIEW  {now}")
    print(f"{'='*60}")
    print(f"\n  Queue status:")
    print(f"    Pending:  {len(pending)}")
    for t, n in sorted(types.items()):
        print(f"      └─ {t}: {n}")
    print(f"    Approved: {len(queues['approved'])}")
    print(f"    Rejected: {len(queues['rejected'])}")

    pred_path = PROJECT_ROOT / "data" / "predictions.json"
    if pred_path.exists():
        preds = json.loads(pred_path.read_text())
        if isinstance(preds, list):
            active = [p for p in preds if p.get("status") == "active"]
        else:
            active = [p for p in preds.get("predictions", []) if p.get("status") == "active"]
        expiring = [
            p for p in active
            if p.get("timeframe_date", "9999") <= (
                datetime.now(timezone.utc).replace(year=datetime.now().year + 1)
                .strftime("%Y-%m-%d")
            )
        ]
        print(f"\n  Predictions:")
        print(f"    Active:   {len(active)}")
        print(f"    Expiring within 1 year: {len(expiring)}")

    brief_dir = PROJECT_ROOT / "site" / "docs" / "brief"
    draft_dir = brief_dir / "drafts"
    if draft_dir.exists():
        drafts = list(draft_dir.glob("*.html"))
        print(f"\n  Brief drafts: {len(drafts)}")


def _run_claim_review(quick: bool) -> int:
    from tools.queue import list_queue, approve, reject
    items = [i for i in list_queue("pending") if i.get("type") == "claim_extraction"]
    if not items:
        print("\n  No claim extractions pending.")
        return 0

    print(f"\n  {len(items)} claim extraction(s) to review.")
    approved = rejected = skipped = 0

    for i, item in enumerate(items, 1):
        print(f"\n  [{i}/{len(items)}]  {item['leader_id']}.{item.get('dimension','?')}  "
              f"conf={item.get('confidence',0):.0%}  date={item['source_date']}")
        print(f"  Claim: {item['extracted_claim'][:160]}")
        if item.get("exact_quote"):
            print(f"  Quote: \"{item['exact_quote'][:120]}\"")

        if quick:
            choice = "s"
        else:
            choice = input("  [a]pprove [r]eject [s]kip [v]iew full > ").strip().lower()

        if choice == "a":
            notes = input("  Notes (optional): ").strip() if not quick else ""
            approve(item["id"], notes)
            approved += 1
        elif choice == "r":
            reason = input("  Reason: ").strip()
            if reason:
                reject(item["id"], reason)
                rejected += 1
        elif choice == "v":
            print(json.dumps(item, indent=2))
            choice = input("  [a]pprove [r]eject [s]kip > ").strip().lower()
            if choice == "a":
                approve(item["id"])
                approved += 1
            elif choice == "r":
                reason = input("  Reason: ").strip()
                if reason:
                    reject(item["id"], reason)
                    rejected += 1
        else:
            skipped += 1

    print(f"\n  Claims: approved={approved} rejected={rejected} skipped={skipped}")
    return approved


def _run_prediction_review() -> int:
    from tools.queue import list_queue, approve, reject
    items = [i for i in list_queue("pending") if i.get("type") == "prediction_draft"]
    if not items:
        return 0

    print(f"\n  {len(items)} prediction draft(s) to review.")
    approved_preds = []
    approved = rejected = 0

    pred_path = PROJECT_ROOT / "data" / "predictions.json"
    published = json.loads(pred_path.read_text()) if pred_path.exists() else []
    if isinstance(published, dict):
        published = published.get("predictions", [])

    for i, item in enumerate(items, 1):
        pd = item.get("prediction_data", {})
        print(f"\n  [{i}/{len(items)}]  Prediction:")
        print(f"    {pd.get('prediction','')[:180]}")
        print(f"    Timeframe: {pd.get('timeframe_date','?')}  Conf: {pd.get('confidence',0):.0%}")
        print(f"    Falsifier: {pd.get('falsifier','')[:140]}")

        choice = input("  [a]pprove [r]eject [s]kip > ").strip().lower()
        if choice == "a":
            import uuid
            pd["id"] = pd.get("id") or f"pred-{uuid.uuid4().hex[:8]}"
            pd["status"] = "active"
            pd["published_at"] = datetime.now(timezone.utc).isoformat()
            published.append(pd)
            approve(item["id"], "approved")
            approved += 1
        elif choice == "r":
            reason = input("  Reason: ").strip()
            reject(item["id"], reason or "rejected")
            rejected += 1

    if approved:
        pred_path.parent.mkdir(parents=True, exist_ok=True)
        pred_path.write_text(json.dumps(published, indent=2, ensure_ascii=False))
        print(f"  Saved {len(published)} predictions to data/predictions.json")

    print(f"\n  Predictions: approved={approved} rejected={rejected}")
    return approved


def _run_case_review() -> int:
    from tools.queue import list_queue, approve, reject
    items = [i for i in list_queue("pending") if i.get("type") == "historical_case"]
    if not items:
        return 0

    print(f"\n  {len(items)} historical case draft(s) to review.")
    approved = 0
    hist_path = PROJECT_ROOT / "data" / "historical" / "historical_cases.json"
    cases = json.loads(hist_path.read_text()) if hist_path.exists() else []
    if isinstance(cases, dict):
        cases = cases.get("cases", [])
    existing_ids = {c.get("case_id") for c in cases}

    for i, item in enumerate(items, 1):
        cd = item.get("case_data", {})
        print(f"\n  [{i}/{len(items)}]  {cd.get('case_id','?')} — {cd.get('country_name','?')} {cd.get('period','')}")
        print(f"    Trigger: {cd.get('trigger','')[:160]}")
        print(f"    Cambodia: {cd.get('cambodia_2029_relevance','')[:160]}")
        print(f"    Risk: {cd.get('implementation_risk','?')}")

        choice = input("  [a]pprove [r]eject [s]kip > ").strip().lower()
        if choice == "a":
            case_id = cd.get("case_id", item["id"])
            cases = [c for c in cases if c.get("case_id") != case_id]
            cases.append(cd)
            existing_ids.add(case_id)
            hist_path.parent.mkdir(parents=True, exist_ok=True)
            hist_path.write_text(json.dumps(cases, indent=2, ensure_ascii=False))
            approve(item["id"], "approved")
            approved += 1
            print(f"  → Added: {case_id}")
        elif choice == "r":
            reason = input("  Reason: ").strip()
            reject(item["id"], reason or "rejected")

    return approved


def _merge_if_approved(approved_count: int) -> None:
    if approved_count == 0:
        return
    print(f"\n  Merging {approved_count} approved claim(s) into profiles...")
    result = subprocess.run(
        [sys.executable, "tools/merge_approved.py"],
        capture_output=True, text=True,
        cwd=PROJECT_ROOT,
    )
    if result.returncode == 0:
        print("  Merge complete.")
    else:
        print(f"  Merge warning: {result.stderr[:200]}")


def _rebuild_site() -> None:
    print("\n  Rebuilding site...")
    result = subprocess.run(
        [sys.executable, "site/build.py"],
        capture_output=True, text=True,
        cwd=PROJECT_ROOT,
    )
    if result.returncode == 0:
        print("  Site built successfully.")
    else:
        print(f"  Build warning: {result.stderr[:200]}")


def _check_expiring_predictions() -> None:
    pred_path = PROJECT_ROOT / "data" / "predictions.json"
    if not pred_path.exists():
        return
    preds = json.loads(pred_path.read_text())
    if isinstance(preds, dict):
        preds = preds.get("predictions", [])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    overdue = [
        p for p in preds
        if p.get("status") == "active" and p.get("timeframe_date", "9999") < today
    ]
    if overdue:
        print(f"\n  ⚠ {len(overdue)} prediction(s) past their timeframe — mark resolved or expired:")
        for p in overdue:
            print(f"    [{p.get('timeframe_date','?')}] {p.get('prediction','')[:120]}")
        print("  Use: python tools/prediction_drafter.py --list")


def run(quick: bool = False) -> None:
    queues = _counts()
    _show_dashboard(queues)

    if not any(queues.values()):
        print("\n  Queue is empty. Nothing to review today.\n")
        _check_expiring_predictions()
        return

    total_approved = 0

    _header("Step 1 of 4 — Claim extractions")
    total_approved += _run_claim_review(quick)

    _header("Step 2 of 4 — Prediction drafts")
    total_approved += _run_prediction_review()

    _header("Step 3 of 4 — Historical case drafts")
    _run_case_review()

    _header("Step 4 of 4 — Wrap up")
    _check_expiring_predictions()
    _merge_if_approved(total_approved)
    _rebuild_site()

    print(f"\n{'='*60}")
    print(f"  SUNDAY REVIEW COMPLETE")
    print(f"  Approved {total_approved} item(s) → profiles updated → site rebuilt.")
    print(f"  See you next Sunday.")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="30-minute Sunday review session.")
    parser.add_argument("--quick", action="store_true", help="Skip detailed prompts — just show and auto-skip.")
    args = parser.parse_args()
    run(quick=args.quick)


if __name__ == "__main__":
    main()
