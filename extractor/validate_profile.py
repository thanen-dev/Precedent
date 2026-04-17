#!/usr/bin/env python3
"""
Validate a leader profile JSON against the LeaderProfile schema.

Usage
-----
    python extractor/validate_profile.py data/leaders/hun_manet_profile.json
    python extractor/validate_profile.py data/leaders/hun_manet_profile.json --strict
    python extractor/validate_profile.py data/leaders/hun_manet_profile.json --json

Flags
-----
--strict    Exit 1 if any of the 7 dimensions are missing (not just malformed).
--json      Print machine-readable JSON result instead of human output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from extractor.schema import DIMENSION_KEYS, LeaderProfile


# ── formatting ────────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"


def _c(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if sys.stdout.isatty() else text


# ── core validation ───────────────────────────────────────────────────────────

def validate(path: Path, strict: bool) -> dict:
    result: dict = {
        "file": str(path),
        "valid": False,
        "errors": [],
        "warnings": [],
        "profile_id": None,
        "completeness": None,
        "dimensions_present": [],
        "dimensions_missing": [],
    }

    if not path.exists():
        result["errors"].append(f"File not found: {path}")
        return result

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result["errors"].append(f"Invalid JSON: {exc}")
        return result

    try:
        profile = LeaderProfile.model_validate(raw)
    except ValidationError as exc:
        for error in exc.errors():
            loc = " → ".join(str(p) for p in error["loc"])
            result["errors"].append(f"{loc}: {error['msg']}")
        return result

    result["valid"] = True
    result["profile_id"] = profile.id
    result["completeness"] = round(profile.completeness, 2)
    result["dimensions_present"] = profile.populated_dimensions
    result["dimensions_missing"] = [
        k for k in DIMENSION_KEYS if k not in profile.populated_dimensions
    ]

    if result["dimensions_missing"]:
        msg = f"Missing dimensions: {', '.join(result['dimensions_missing'])}"
        if strict:
            result["valid"] = False
            result["errors"].append(msg)
        else:
            result["warnings"].append(msg)

    return result


# ── output ────────────────────────────────────────────────────────────────────

def print_human(result: dict) -> None:
    valid = result["valid"]
    completeness = result["completeness"]

    status = _c("PASS", GREEN) if valid else _c("FAIL", RED)
    print(f"\n{BOLD}Precedent — profile validator{RESET}")
    print(_c("─" * 44, DIM))
    print(f"  File        {result['file']}")
    if result["profile_id"]:
        print(f"  Profile ID  {result['profile_id']}")
    if completeness is not None:
        pct = f"{completeness * 100:.0f}%"
        color = GREEN if completeness == 1.0 else YELLOW if completeness >= 0.5 else RED
        print(f"  Complete    {_c(pct, color)}")
    if result["dimensions_present"]:
        print(f"  Dimensions  {', '.join(result['dimensions_present'])}")
    print(f"  Status      {status}")
    print()

    for msg in result["errors"]:
        print(f"  {_c('✗', RED)}  {msg}")
    for msg in result["warnings"]:
        print(f"  {_c('⚠', YELLOW)}  {msg}")
    if not result["errors"] and not result["warnings"]:
        print(f"  {_c('✓', GREEN)}  All checks passed")
    print()


def print_json(result: dict) -> None:
    print(json.dumps(result, indent=2))


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a leader profile JSON against the LeaderProfile schema."
    )
    parser.add_argument("file", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any of the 7 dimensions are missing",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    args = parser.parse_args()

    result = validate(args.file, strict=args.strict)

    if args.as_json:
        print_json(result)
    else:
        print_human(result)

    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
