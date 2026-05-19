#!/usr/bin/env python3
"""
Research and draft a historical case for the Precedent database.
Drafts go to the review queue before entering data/historical/.

Usage:
    python tools/case_researcher.py
    python tools/case_researcher.py --batch cases_to_research.json
    python tools/case_researcher.py --approve   # review and approve pending cases
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

PROJECT_ROOT = Path(__file__).parent.parent
HIST_PATH    = PROJECT_ROOT / "data" / "historical" / "historical_cases.json"
DRAFTS_DIR   = PROJECT_ROOT / "data" / "queue" / "pending"

CASE_SCHEMA = {
    "case_id":               "string — e.g. BGD_GARMENT_2013",
    "country":               "ISO country name",
    "country_name":          "full display name",
    "period":                "e.g. 2010–2015",
    "trigger":               "what caused the crisis/transition",
    "mechanism":             "causal chain — how trigger led to outcome",
    "outcome_1yr":           "what happened in the first year",
    "outcome_3yr":           "what happened by year three",
    "outcome_5yr":           "what happened by year five",
    "causal_mechanisms":     {"key": "description"},
    "lessons":               {"key": "lesson text"},
    "cambodia_2029_relevance": "why this matters for Cambodia by 2029",
    "implementation_risk":   "HIGH / MEDIUM / LOW",
    "sources":               ["list of sources used"],
}

RESEARCH_PROMPT = """You are a researcher for Precedent, a political intelligence database focused on Cambodia.

Your task is to research and draft a historical case entry for the database. This case will be used for structural analogues analysis — comparing Cambodia's current situation to historical precedents.

Country: {country}
Event/Period: {event}
Time period: {period}

Research the case thoroughly and return a valid JSON object with EXACTLY these fields:

{schema}

Requirements:
- Be specific. Use real numbers, dates, and named officials where available.
- "mechanism" must explain the causal chain clearly, not just restate the trigger.
- "cambodia_2029_relevance" must be specific to Cambodia's current situation — EU EBA status, Chinese FDI concentration, garment sector dependency, political succession.
- Mark any claim you're uncertain about with [UNCERTAIN].
- "sources" must list real sources (academic papers, news outlets, government reports) — do not invent sources.
- implementation_risk: HIGH = direct structural analogue; MEDIUM = partial analogue; LOW = weak analogue.

Return ONLY the JSON object, no markdown, no explanation."""


def _research_case(country: str, event: str, period: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    prompt = RESEARCH_PROMPT.format(
        country=country,
        event=event,
        period=period,
        schema=json.dumps(CASE_SCHEMA, indent=2),
    )

    log.info("Researching: %s — %s (%s)...", country, event, period)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # strip markdown code blocks if present
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"):
        raw = "\n".join(raw.split("\n")[:-1])

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("JSON parse failed: %s\nRaw: %s", exc, raw[:300])
        return {"_raw": raw, "_parse_error": str(exc)}


def _submit_case_draft(case: dict, country: str, event: str) -> str:
    """Submit a researched case to the pending queue."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    item_id = f"case-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    item = {
        "id":             item_id,
        "type":           "historical_case",
        "leader_id":      "__historical__",
        "dimension":      None,
        "source_url":     "",
        "source_date":    datetime.utcnow().strftime("%Y-%m-%d"),
        "extracted_claim": f"Historical case: {country} — {event}",
        "exact_quote":    "",
        "confidence":     0.75,
        "extracted_by":   "claude-sonnet-4-6",
        "extracted_at":   datetime.utcnow().isoformat(),
        "status":         "pending",
        "reviewer_notes": "",
        "case_data":      case,
    }
    path = DRAFTS_DIR / f"{item_id}.json"
    path.write_text(json.dumps(item, indent=2, ensure_ascii=False))
    log.info("Draft queued: %s", path)
    return item_id


def _load_historical() -> list[dict]:
    if not HIST_PATH.exists():
        return []
    data = json.loads(HIST_PATH.read_text())
    return data if isinstance(data, list) else data.get("cases", [])


def _save_historical(cases: list[dict]) -> None:
    HIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    HIST_PATH.write_text(json.dumps(cases, indent=2, ensure_ascii=False))
    log.info("Saved %d cases to %s", len(cases), HIST_PATH)


def approve_pending_cases() -> None:
    """Interactive: review pending historical case drafts and approve/reject."""
    from tools.queue import list_queue, approve, reject
    drafts = [i for i in list_queue("pending") if i.get("type") == "historical_case"]

    if not drafts:
        print("No pending historical case drafts.")
        return

    cases = _load_historical()
    existing_ids = {c.get("case_id") for c in cases}

    for item in drafts:
        case_data = item.get("case_data", {})
        print(f"\n{'='*72}")
        print(f"Case: {case_data.get('case_id', '?')}  —  {case_data.get('country_name', '?')}")
        print(f"Period: {case_data.get('period', '?')}")
        print(f"Trigger: {case_data.get('trigger', '')[:200]}")
        print(f"Cambodia relevance: {case_data.get('cambodia_2029_relevance', '')[:200]}")
        print(f"Risk: {case_data.get('implementation_risk', '?')}")
        print(f"{'='*72}")

        while True:
            choice = input("\n[a]pprove  [r]eject  [v]iew full  [s]kip > ").strip().lower()
            if choice == "a":
                case_id = case_data.get("case_id", item["id"])
                if case_id in existing_ids:
                    print(f"Case {case_id} already exists. [o]verwrite or [s]kip?")
                    if input("> ").strip().lower() != "o":
                        break
                    cases = [c for c in cases if c.get("case_id") != case_id]
                cases.append(case_data)
                existing_ids.add(case_id)
                _save_historical(cases)
                approve(item["id"], "approved and added to historical_cases.json")
                print(f"  → APPROVED and added: {case_id}")
                break
            elif choice == "r":
                reason = input("  Reason: ").strip()
                reject(item["id"], reason or "rejected")
                print("  → REJECTED")
                break
            elif choice == "v":
                print(json.dumps(case_data, indent=2))
            elif choice == "s":
                break


def run_batch(items: list[dict]) -> list[str]:
    """Research multiple cases. items = [{"country":..., "event":..., "period":...}]"""
    item_ids = []
    for it in items:
        try:
            case = _research_case(it["country"], it["event"], it["period"])
            if "_parse_error" not in case:
                iid = _submit_case_draft(case, it["country"], it["event"])
                item_ids.append(iid)
            else:
                log.error("Skipping %s/%s — parse error", it["country"], it["event"])
        except Exception as exc:
            log.error("Failed %s/%s: %s", it["country"], it["event"], exc)
    return item_ids


def run_interactive() -> None:
    print("\n=== Case Researcher ===")
    print("Enter case details. Leave blank to cancel.\n")
    country = input("Country: ").strip()
    if not country:
        return
    event  = input("Event/scenario: ").strip()
    period = input("Period (e.g. 2010-2015): ").strip()

    case = _research_case(country, event, period)
    if "_parse_error" in case:
        print("\nParse error. Raw output saved for debugging.")
        Path("data/case_draft_error.txt").write_text(case.get("_raw", ""))
        return

    print("\n--- Draft ---")
    print(json.dumps(case, indent=2)[:1500])
    print("...")

    if input("\nSubmit to queue for review? [y/n]: ").strip().lower() == "y":
        iid = _submit_case_draft(case, country, event)
        print(f"Queued: {iid}")
        print("Run `python tools/case_researcher.py --approve` to review.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Research and draft historical cases.")
    parser.add_argument("--approve", action="store_true", help="Review pending case drafts.")
    parser.add_argument("--batch", type=Path, default=None,
                        help="JSON file with list of {country, event, period} objects.")
    args = parser.parse_args()

    if args.approve:
        approve_pending_cases()
    elif args.batch:
        items = json.loads(args.batch.read_text())
        ids = run_batch(items)
        print(f"Queued {len(ids)} case drafts. Run --approve to review.")
    else:
        run_interactive()


if __name__ == "__main__":
    main()
