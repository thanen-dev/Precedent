#!/usr/bin/env python3
"""
Draft falsifiable predictions based on current leader profiles, conflicts, and cases.
Drafts go to review queue; you approve before publishing.

Usage:
    python tools/prediction_drafter.py [--count 5]
    python tools/prediction_drafter.py --approve    # review pending predictions
    python tools/prediction_drafter.py --list       # show active predictions
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(format="%(levelname)-8s  %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

PROJECT_ROOT  = Path(__file__).parent.parent
PRED_PATH     = PROJECT_ROOT / "data" / "predictions.json"
LEADERS_DIR   = PROJECT_ROOT / "data" / "leaders"
CONFLICTS_DIR = PROJECT_ROOT / "data" / "conflicts"
HIST_PATH     = PROJECT_ROOT / "data" / "historical" / "historical_cases.json"


def _load_profiles() -> list[dict]:
    profiles = []
    for p in sorted(LEADERS_DIR.glob("*_profile.json")):
        try:
            profiles.append(json.loads(p.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return profiles


def _load_conflicts() -> list[dict]:
    results = []
    if not CONFLICTS_DIR.exists():
        return results
    for f in sorted(CONFLICTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            results.extend(data.get("conflicts", []))
        except (json.JSONDecodeError, OSError):
            pass
    return results


def _load_cases(limit: int = 10) -> list[dict]:
    if not HIST_PATH.exists():
        return []
    data = json.loads(HIST_PATH.read_text())
    cases = data if isinstance(data, list) else data.get("cases", [])
    return cases[:limit]


def _leader_summary(p: dict) -> str:
    name  = p.get("full_name", p.get("id", "?"))
    dims  = p.get("dimensions", {})
    lines = [f"{name}:"]
    for key in ("growth_theory", "risk_tolerance", "global_positioning_logic", "time_horizon"):
        d = dims.get(key, {})
        if not isinstance(d, dict):
            continue
        for field in ("assessed_position", "core_thesis", "position"):
            v = d.get(field, "")
            if isinstance(v, str) and len(v) > 20:
                lines.append(f"  {key}: {v[:180]}")
                break
    return "\n".join(lines)


def _conflict_summary(c: dict) -> str:
    dim  = c.get("dimension", "?").replace("_", " ")
    la   = c.get("leader_a", "?")
    lb   = c.get("leader_b", "?")
    expl = c.get("conflict_explanation", "")[:200]
    pred = c.get("prediction", "")[:200]
    return f"CONFLICT [{dim}] {la} vs {lb}: {expl} | Breaking point: {pred}"


DRAFT_PROMPT = """You are the lead analyst for Precedent, a political intelligence system tracking Cambodia.

Based on the data below, draft {count} specific, falsifiable predictions about Cambodia's political economy.

Each prediction MUST have these exact fields:
{{
  "id": "unique string like pred-2026-001",
  "prediction": "specific statement about what will happen",
  "mechanism": "why — traced to specific doctrine, conflict, or structural pressure",
  "timeframe_date": "YYYY-MM-DD or YYYY-QN (specific, not vague)",
  "falsifier": "exact observable event that would prove this prediction wrong",
  "confidence": 0.0-1.0,
  "historical_basis": "which historical case supports this and why",
  "related_leaders": ["leader_id_1", "leader_id_2"],
  "related_conflict_dim": "dimension_key or null",
  "status": "active"
}}

Rules:
- Predictions must be falsifiable. "Cambodia will struggle with trade" is NOT a prediction.
- Timeframes must be specific dates or quarters, not "in the next few years".
- Confidence 0.7+ means you have strong structural basis. 0.5 means the mechanism is plausible but uncertain.
- Do not invent facts. If uncertain, lower the confidence.
- Focus on the 2025-2029 window — EU EBA restoration, Chinese FDI, Hun Manet legitimacy, garment sector.

LEADER PROFILES:
{profiles}

ACTIVE CONFLICTS:
{conflicts}

HISTORICAL CASES (most relevant):
{cases}

Return a JSON array of {count} prediction objects. Nothing else — no markdown, no explanation."""


def draft_predictions(count: int = 5) -> list[dict]:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    profiles   = _load_profiles()
    conflicts  = _load_conflicts()
    cases      = _load_cases(8)

    profile_text  = "\n\n".join(_leader_summary(p) for p in profiles[:8])
    conflict_text = "\n".join(_conflict_summary(c) for c in conflicts[:10])
    case_text     = "\n".join(
        f"{c.get('case_id','?')} | {c.get('country_name','?')} {c.get('period','')}: "
        f"trigger={c.get('trigger','')[:100]} | lesson={str(c.get('lessons',''))[:150]}"
        for c in cases
    )

    prompt = DRAFT_PROMPT.format(
        count=count,
        profiles=profile_text,
        conflicts=conflict_text,
        cases=case_text,
    )

    log.info("Drafting %d predictions...", count)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"):
        raw = "\n".join(raw.split("\n")[:-1])

    try:
        preds = json.loads(raw)
        if isinstance(preds, dict):
            preds = [preds]
        return preds
    except json.JSONDecodeError as exc:
        log.error("JSON parse failed: %s\nRaw: %s", exc, raw[:500])
        return []


def _queue_drafts(preds: list[dict]) -> list[str]:
    from tools.queue import PENDING_DIR
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    item_ids = []
    for p in preds:
        item_id = f"pred-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
        item = {
            "id":             item_id,
            "type":           "prediction_draft",
            "leader_id":      (p.get("related_leaders") or ["__prediction__"])[0],
            "dimension":      p.get("related_conflict_dim"),
            "source_url":     "",
            "source_date":    datetime.utcnow().strftime("%Y-%m-%d"),
            "extracted_claim": p.get("prediction", ""),
            "exact_quote":    "",
            "confidence":     p.get("confidence", 0.6),
            "extracted_by":   "claude-sonnet-4-6",
            "extracted_at":   datetime.utcnow().isoformat(),
            "status":         "pending",
            "reviewer_notes": "",
            "prediction_data": p,
        }
        path = PENDING_DIR / f"{item_id}.json"
        path.write_text(json.dumps(item, indent=2, ensure_ascii=False))
        item_ids.append(item_id)
        log.info("Queued prediction: %s — %s", item_id, p.get("prediction", "")[:80])
    return item_ids


def _load_predictions() -> list[dict]:
    if not PRED_PATH.exists():
        return []
    data = json.loads(PRED_PATH.read_text())
    return data if isinstance(data, list) else data.get("predictions", [])


def _save_predictions(preds: list[dict]) -> None:
    PRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRED_PATH.write_text(json.dumps(preds, indent=2, ensure_ascii=False))
    log.info("Saved %d predictions to %s", len(preds), PRED_PATH)


def approve_pending() -> None:
    from tools.queue import list_queue, approve, reject
    drafts = [i for i in list_queue("pending") if i.get("type") == "prediction_draft"]

    if not drafts:
        print("No pending prediction drafts.")
        return

    published = _load_predictions()
    existing_ids = {p.get("id") for p in published}

    for item in drafts:
        pd = item.get("prediction_data", {})
        print(f"\n{'='*72}")
        print(f"Prediction: {pd.get('prediction','')}")
        print(f"Mechanism:  {pd.get('mechanism','')[:200]}")
        print(f"Timeframe:  {pd.get('timeframe_date','?')}")
        print(f"Falsifier:  {pd.get('falsifier','')[:200]}")
        print(f"Confidence: {pd.get('confidence',0):.0%}")
        print(f"History:    {pd.get('historical_basis','')[:150]}")
        print(f"{'='*72}")

        while True:
            choice = input("\n[a]pprove  [r]eject  [e]dit prediction text  [s]kip > ").strip().lower()
            if choice == "a":
                pred_id = pd.get("id") or f"pred-{uuid.uuid4().hex[:8]}"
                pd["id"] = pred_id
                pd.setdefault("status", "active")
                pd["published_at"] = datetime.utcnow().isoformat()
                if pred_id not in existing_ids:
                    published.append(pd)
                    existing_ids.add(pred_id)
                _save_predictions(published)
                approve(item["id"], "approved and added to predictions.json")
                print(f"  → APPROVED: {pred_id}")
                break
            elif choice == "r":
                reason = input("  Reason: ").strip()
                reject(item["id"], reason or "rejected")
                print("  → REJECTED")
                break
            elif choice == "e":
                new_text = input("  New prediction text: ").strip()
                if new_text:
                    pd["prediction"] = new_text
                    print(f"  Updated to: {new_text}")
            elif choice == "s":
                break


def list_predictions() -> None:
    preds = _load_predictions()
    if not preds:
        print("No predictions yet. Run: python tools/prediction_drafter.py --count 5")
        return
    active   = [p for p in preds if p.get("status") == "active"]
    resolved = [p for p in preds if p.get("status") == "resolved"]
    expired  = [p for p in preds if p.get("status") == "expired"]
    print(f"\n{len(active)} active  |  {len(resolved)} resolved  |  {len(expired)} expired\n")
    for p in sorted(active, key=lambda x: x.get("timeframe_date", "")):
        print(f"[{p.get('timeframe_date','?')}] {p.get('confidence',0):.0%}  {p.get('prediction','')[:100]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft and manage predictions.")
    parser.add_argument("--count", type=int, default=5, help="Number of predictions to draft.")
    parser.add_argument("--approve", action="store_true", help="Review pending prediction drafts.")
    parser.add_argument("--list",    action="store_true", help="List active predictions.")
    args = parser.parse_args()

    if args.approve:
        approve_pending()
    elif args.list:
        list_predictions()
    else:
        preds = draft_predictions(count=args.count)
        if preds:
            ids = _queue_drafts(preds)
            print(f"\nQueued {len(ids)} prediction draft(s). Review with:")
            print("  python tools/prediction_drafter.py --approve")
        else:
            print("No predictions drafted (check ANTHROPIC_API_KEY and logs).")


if __name__ == "__main__":
    main()
