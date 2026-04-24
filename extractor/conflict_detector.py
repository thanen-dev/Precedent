#!/usr/bin/env python3
"""
Detect genuine logical contradictions between two or more leader profiles.

Loads profiles from data/leaders/{leader_id}_profile.json, calls Claude Sonnet
to compare them dimension by dimension, and flags only contradictions where
both positions being simultaneously true would be structurally impossible.

Differences in emphasis, tone, or priority are NOT conflicts. A conflict
requires that acting on both positions at once would produce incoherent policy.

Output saved to data/conflicts/{leader_a}_vs_{leader_b}.json and printed stdout.

Usage
-----
    python extractor/conflict_detector.py hun_manet hun_sen
    python extractor/conflict_detector.py hun_manet aun_pornmoniroth cham_nimul
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date as Date
from itertools import combinations
from pathlib import Path

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
LEADERS_DIR = PROJECT_ROOT / "data" / "leaders"
CONFLICTS_DIR = PROJECT_ROOT / "data" / "conflicts"

DIMENSION_KEYS = (
    "growth_theory",
    "risk_tolerance",
    "time_horizon",
    "dependency_assumptions",
    "institution_vs_relationship",
    "global_positioning_logic",
    "consistency_score",
)


# ── data loading ──────────────────────────────────────────────────────────────

def load_profile(leader_id: str) -> dict:
    path = LEADERS_DIR / f"{leader_id}_profile.json"
    if not path.exists():
        log.error("Profile not found: %s", path)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


# ── prompt construction ───────────────────────────────────────────────────────

_SYSTEM = """\
You are a political-economy analyst detecting genuine structural contradictions \
between the operating doctrines of two senior government officials.

You will receive profiles of two leaders, each with positions across 7 dimensions \
of political-economic doctrine.

Your task: identify genuine LOGICAL CONTRADICTIONS — not style differences, not \
emphasis differences, not tactical variations. A conflict must satisfy this test:
  "If both positions were simultaneously implemented as government policy,
   the resulting policy would be incoherent or self-defeating."

Examples of what IS a conflict:
  - Leader A: institutions and rule-of-law are the foundation of FDI attraction.
    Leader B: relationships and personal guarantees are what actually close deals.
    → These produce opposite investment promotion frameworks that cannot both be true.

Examples of what is NOT a conflict:
  - Leader A favours faster growth; Leader B favours more caution.
    → Difference in degree, not structural contradiction.
  - Leader A focuses on manufacturing; Leader B on trade.
    → Different portfolios, not conflicting doctrines.

Rules:
  - Only report genuine contradictions. Zero conflicts is a valid and often correct answer.
  - For each conflict, cite the specific position and a verbatim quote from each leader.
  - conflict_explanation must state WHY simultaneous implementation is structurally impossible.
  - implementation_risk: HIGH if the contradiction is in a dimension where both leaders \
    have active jurisdiction; MEDIUM if adjacent; LOW if theoretical only.
  - prediction: the specific policy failure mode that will emerge when this contradiction \
    is forced to resolve — name the concrete breaking point.

OUTPUT: strict JSON only — no prose, no markdown fences.

{
  "conflicts": [
    {
      "dimension": "<one of the 7 dimension keys>",
      "leader_a": "<leader_id>",
      "leader_a_position": "<1-2 sentence summary of their doctrine on this dimension>",
      "leader_a_quote": "<verbatim quote from their profile, or empty string if none>",
      "leader_b": "<leader_id>",
      "leader_b_position": "<1-2 sentence summary of their doctrine on this dimension>",
      "leader_b_quote": "<verbatim quote from their profile, or empty string if none>",
      "conflict_explanation": "<why simultaneous implementation is structurally impossible>",
      "implementation_risk": "HIGH|MEDIUM|LOW",
      "prediction": "<concrete policy breaking point>"
    }
  ]
}
"""


def _profile_block(profile: dict) -> str:
    """Render a leader profile as a compact text block for the prompt."""
    leader_id = profile.get("id", "unknown")
    name = profile.get("full_name", leader_id)
    title = profile.get("title", "")
    lines = [f"LEADER: {name} ({leader_id})", f"Title: {title}", ""]

    dims = profile.get("dimensions", {})
    for key in DIMENSION_KEYS:
        dim = dims.get(key)
        if not isinstance(dim, dict):
            continue
        thesis = dim.get("core_thesis") or ""
        stated = dim.get("stated_theory")
        if isinstance(stated, dict):
            stated = stated.get("summary", "")
        revealed = dim.get("revealed_preference") or ""

        lines.append(f"[{key}]")
        if thesis:
            lines.append(f"  Core thesis: {thesis[:300]}")
        if stated:
            lines.append(f"  Stated theory: {str(stated)[:200]}")
        if revealed:
            lines.append(f"  Revealed preference: {str(revealed)[:200]}")

        # Pull first evidence quote if available
        evidence = dim.get("_evidence", [])
        if evidence and isinstance(evidence[0], dict):
            quote = evidence[0].get("quote", "")
            if quote:
                lines.append(f"  Quote: \"{quote[:200]}\"")
        lines.append("")

    return "\n".join(lines)


def _build_user_message(profile_a: dict, profile_b: dict) -> str:
    return (
        f"Compare these two leaders and identify genuine logical contradictions "
        f"in their political-economic doctrine.\n\n"
        f"{_profile_block(profile_a)}\n"
        f"{'─' * 60}\n\n"
        f"{_profile_block(profile_b)}"
    )


# ── Claude call ───────────────────────────────────────────────────────────────

def _call_claude(user_message: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    log.info("Calling %s for conflict detection...", MODEL)
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.BadRequestError as exc:
        log.error("API rejected request: %s", exc)
        sys.exit(1)
    except anthropic.AuthenticationError:
        log.error("ANTHROPIC_API_KEY is invalid or expired")
        sys.exit(1)
    except anthropic.PermissionDeniedError as exc:
        log.error("API permission error (check billing/credits): %s", exc)
        sys.exit(1)
    except anthropic.APIError as exc:
        log.error("API error (%s): %s", type(exc).__name__, exc)
        sys.exit(1)

    raw: str = message.content[0].text
    log.debug("Claude raw response:\n%s", raw)

    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    payload = fence.group(1) if fence else raw.strip()

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        log.error("Claude returned malformed JSON: %s\n---\n%s", exc, payload)
        sys.exit(1)


# ── output assembly ───────────────────────────────────────────────────────────

def _conflict_output_path(id_a: str, id_b: str) -> Path:
    CONFLICTS_DIR.mkdir(parents=True, exist_ok=True)
    return CONFLICTS_DIR / f"{id_a}_vs_{id_b}.json"


def detect_pair(id_a: str, id_b: str) -> dict:
    """Detect conflicts between exactly two leaders. Returns the output dict."""
    profile_a = load_profile(id_a)
    profile_b = load_profile(id_b)

    log.info("Comparing %s vs %s", id_a, id_b)
    user_message = _build_user_message(profile_a, profile_b)
    response = _call_claude(user_message)

    conflicts = response.get("conflicts", [])
    log.info("Found %d conflict(s)", len(conflicts))

    output = {
        "leaders_compared": [id_a, id_b],
        "conflicts": conflicts,
        "analysis_date": str(Date.today()),
    }

    path = _conflict_output_path(id_a, id_b)
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Saved → %s", path.relative_to(PROJECT_ROOT))

    return output


# ── orchestration ─────────────────────────────────────────────────────────────

def detect_all_pairs(leader_ids: list[str]) -> list[dict]:
    """
    Run conflict detection for every unique pair in leader_ids.
    Returns list of output dicts, one per pair.
    """
    pairs = list(combinations(leader_ids, 2))
    if not pairs:
        log.error("Need at least 2 leader IDs")
        sys.exit(1)

    results = []
    for id_a, id_b in pairs:
        result = detect_pair(id_a, id_b)
        results.append(result)

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect genuine logical contradictions between leader doctrines."
    )
    parser.add_argument(
        "leader_ids",
        nargs="+",
        metavar="LEADER_ID",
        help="Two or more snake-case leader IDs, e.g. hun_manet hun_sen",
    )
    args = parser.parse_args()

    if len(args.leader_ids) < 2:
        parser.error("Provide at least 2 leader IDs")

    results = detect_all_pairs(args.leader_ids)

    # Print all results to stdout
    if len(results) == 1:
        print(json.dumps(results[0], indent=2, ensure_ascii=False))
    else:
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
