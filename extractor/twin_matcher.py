#!/usr/bin/env python3
"""
Match a policy signal to the 2 closest historical twin cases.

Loads all cases from data/historical/historical_cases.json, optionally loads
a leader profile for additional context, then calls Claude Sonnet to score
structural similarity across 5 dimensions and return exactly 2 matches.

The 5 scoring dimensions:
  - trade_preference_dependency   How reliant the economy is on preferential market access
  - export_concentration          Degree to which exports cluster in one sector
  - governance_type               Structural type of political authority
  - development_stage             Income/industrialisation stage at time of signal
  - external_market_dependency    Breadth of exposure to a single foreign market/buyer network

Output saved to data/twins/{slug}.json and printed to stdout.

Usage
-----
    python extractor/twin_matcher.py "SIGNAL TEXT" [--leader LEADER_ID]

Example
-------
    python extractor/twin_matcher.py \\
        "Cambodia's Funan Techo Canal signals infrastructure-led growth prioritised over trade diversification" \\
        --leader hun_manet
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date as Date
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

MODEL = "claude-sonnet-4-6"

PROJECT_ROOT = Path(__file__).parent.parent
HISTORICAL_PATH = PROJECT_ROOT / "data" / "historical" / "historical_cases.json"
LEADERS_DIR = PROJECT_ROOT / "data" / "leaders"
TWINS_DIR = PROJECT_ROOT / "data" / "twins"


# ── data loading ──────────────────────────────────────────────────────────────

def load_cases() -> list[dict]:
    if not HISTORICAL_PATH.exists():
        log.error("Historical cases not found: %s", HISTORICAL_PATH)
        sys.exit(1)
    return json.loads(HISTORICAL_PATH.read_text(encoding="utf-8"))


def load_leader_profile(leader_id: str) -> dict | None:
    path = LEADERS_DIR / f"{leader_id}_profile.json"
    if not path.exists():
        log.warning("Leader profile not found: %s", path)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ── prompt construction ───────────────────────────────────────────────────────

_SYSTEM = """\
You are a comparative political-economy analyst specialising in developing-country \
structural trajectories.

You will receive:
  1. A POLICY SIGNAL — a statement describing a specific policy move or economic event.
  2. LEADER CONTEXT — optional mental-model profile of the leader behind the signal.
  3. HISTORICAL CASES — a numbered list of documented cases with structural profiles.

Your task: identify the 2 cases that are STRUCTURALLY closest to the signal, \
score them, and extract actionable intelligence.

Scoring is across 5 dimensions (each scored 0.0–1.0 similarity to the signal context):
  - trade_preference_dependency
  - export_concentration
  - governance_type
  - development_stage
  - external_market_dependency

similarity_score = weighted average of the 5 dimension scores.

Rules:
  - Return EXACTLY 2 matches. No more, no fewer.
  - Do NOT hedge. State the most structurally likely outcome.
  - similarity_rationale: 2-3 sentences — WHY this case is structurally analogous.
  - outcome_summary: what actually happened in the historical case (1-2 sentences, factual).
  - cambodia_lesson: the single most actionable lesson for Cambodia given this signal.
  - risk_flag: HIGH if the historical outcome was crisis/reversal; MEDIUM if mixed; LOW if positive.

OUTPUT: strict JSON only — no prose, no markdown fences.

{
  "matches": [
    {
      "case_id": "...",
      "country": "...",
      "similarity_score": 0.00,
      "similarity_rationale": "...",
      "outcome_summary": "...",
      "cambodia_lesson": "...",
      "risk_flag": "HIGH|MEDIUM|LOW"
    },
    {
      "case_id": "...",
      "country": "...",
      "similarity_score": 0.00,
      "similarity_rationale": "...",
      "outcome_summary": "...",
      "cambodia_lesson": "...",
      "risk_flag": "HIGH|MEDIUM|LOW"
    }
  ]
}
"""


def _build_cases_block(cases: list[dict]) -> str:
    lines = []
    for i, case in enumerate(cases, 1):
        lines.append(f"CASE {i}: {case['case_id']}")
        lines.append(f"  Country: {case['country']}  |  Period: {case['period']}")
        lines.append(f"  Label: {case['label']}")
        lines.append(f"  Category: {case['category']}")
        lines.append(f"  Context: {case['context']}")
        lines.append(f"  Trigger: {case['shock_or_trigger']}")
        lines.append(f"  Lessons: {case['lessons']}")
        sp = case.get("structural_profile", {})
        lines.append(
            f"  Structural profile: "
            f"trade_pref_dep={sp.get('trade_preference_dependency', '?')}  "
            f"export_conc={sp.get('export_concentration', '?')}  "
            f"governance={sp.get('governance_type', '?')}  "
            f"dev_stage={sp.get('development_stage', '?')}  "
            f"ext_market_dep={sp.get('external_market_dependency', '?')}"
        )
        lines.append("")
    return "\n".join(lines)


def _build_leader_block(profile: dict) -> str:
    dims = profile.get("dimensions", {})
    lines = [
        f"Leader: {profile.get('full_name', '')} — {profile.get('title', '')}",
    ]
    for key, dim in dims.items():
        if isinstance(dim, dict) and dim.get("core_thesis"):
            lines.append(f"  {key}: {dim['core_thesis'][:200]}")
    return "\n".join(lines)


def _build_user_message(
    signal: str,
    cases: list[dict],
    leader_profile: dict | None,
) -> str:
    parts = [f"POLICY SIGNAL:\n{signal}\n"]

    if leader_profile:
        parts.append(f"LEADER CONTEXT:\n{_build_leader_block(leader_profile)}\n")

    parts.append(f"HISTORICAL CASES:\n{_build_cases_block(cases)}")
    return "\n".join(parts)


# ── Claude call ───────────────────────────────────────────────────────────────

def _call_claude(user_message: str) -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    log.info("Calling %s for twin matching...", MODEL)
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.BadRequestError as exc:
        log.error("API rejected request: %s", exc.message)
        sys.exit(1)
    except anthropic.AuthenticationError:
        log.error("ANTHROPIC_API_KEY is invalid or expired")
        sys.exit(1)
    except anthropic.PermissionDeniedError as exc:
        log.error("API permission error (check billing/credits): %s", exc.message)
        sys.exit(1)
    except anthropic.APIError as exc:
        log.error("API error (%s): %s", type(exc).__name__, exc)
        sys.exit(1)

    raw: str = message.content[0].text
    log.debug("Claude raw response:\n%s", raw)

    # Strip markdown fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    payload = match.group(1) if match else raw.strip()

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        log.error("Claude returned malformed JSON: %s\n---\n%s", exc, payload)
        sys.exit(1)





# ── output assembly ───────────────────────────────────────────────────────────

def _slug(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:max_len]


def assemble_output(
    signal: str,
    leader_id: str | None,
    claude_response: dict,
) -> dict:
    matches = claude_response.get("matches", [])
    if len(matches) != 2:
        log.warning("Claude returned %d match(es) instead of 2 — proceeding with what was returned", len(matches))

    return {
        "signal": signal,
        "leader_id": leader_id,
        "matches": matches,
        "analysis_date": str(Date.today()),
    }


def save_output(output: dict) -> Path:
    TWINS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(output["signal"])
    path = TWINS_DIR / f"{output['analysis_date']}_{slug}.json"
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Saved → %s", path.relative_to(PROJECT_ROOT))
    return path


# ── orchestration ─────────────────────────────────────────────────────────────

def match(signal: str, leader_id: str | None) -> dict:
    cases = load_cases()
    leader_profile = load_leader_profile(leader_id) if leader_id else None

    user_message = _build_user_message(signal, cases, leader_profile)
    log.info("Signal: %s", signal[:80] + ("..." if len(signal) > 80 else ""))
    if leader_id:
        log.info("Leader context: %s", leader_id)

    claude_response = _call_claude(user_message)
    output = assemble_output(signal, leader_id, claude_response)

    save_output(output)
    return output


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Match a policy signal to 2 historical twin cases via Claude Sonnet."
    )
    parser.add_argument(
        "signal",
        help="Policy signal text, e.g. 'Cambodia's Funan Techo Canal signals infrastructure-led growth...'",
    )
    parser.add_argument(
        "--leader",
        dest="leader_id",
        metavar="LEADER_ID",
        help="Snake-case leader ID to include profile context, e.g. hun_manet",
    )
    args = parser.parse_args()

    output = match(args.signal, args.leader_id)
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
