#!/usr/bin/env python3
"""
Migrate all_10_leaders.json into data/leaders/{id}_profile.json files.
"""
from __future__ import annotations
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LEADERS_DIR = PROJECT_ROOT / "data" / "leaders"
SOURCE = Path("/Users/thanenpeou/Downloads/all_10_leaders.json")

ENCODING_LAT = "latin-1"
ENCODING_UTF = "utf-8"


def fix(s):
    if not isinstance(s, str):
        return s
    try:
        return s.encode(ENCODING_LAT).decode(ENCODING_UTF)
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def fix_deep(obj):
    if isinstance(obj, str):
        return fix(obj)
    if isinstance(obj, dict):
        return {k: fix_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fix_deep(v) for v in obj]
    return obj


def build_profile(leader_id: str, raw: dict) -> dict:
    ldr = raw["leader"]
    dims_raw = raw.get("dimensions", {})
    consistency_ratings = raw.get("consistency_ratings", [])
    synth_raw = raw.get("synthesis", {})

    # Build dimensions — embed consistency_ratings into consistency_score
    dimensions = {}
    for key in ("growth_theory", "risk_tolerance", "time_horizon",
                "dependency_assumptions", "institution_vs_relationship",
                "global_positioning_logic", "consistency_score"):
        dim = fix_deep(dims_raw.get(key)) or {}
        if key == "consistency_score" and consistency_ratings:
            dim["ratings"] = fix_deep(consistency_ratings)
        dimensions[key] = dim if dim else None

    # guiding_principles from predictive_principles
    raw_principles = synth_raw.get("predictive_principles", [])
    guiding_principles = []
    for item in (raw_principles if isinstance(raw_principles, list) else []):
        if isinstance(item, dict):
            guiding_principles.append(fix_deep(item))
        else:
            guiding_principles.append({"dimension": "", "insight": fix(str(item))})

    # key_external_analysis_quote
    anchor = synth_raw.get("anchor_quote", "")
    if isinstance(anchor, dict):
        key_quote = fix_deep(anchor)
        if "quote" not in key_quote:
            key_quote = {"quote": "", "source": ""}
    else:
        key_quote = {"quote": fix(str(anchor)) if anchor else "", "source": ""}

    # Merge bio into purpose
    purpose = fix(ldr.get("purpose", ""))
    bio = fix(ldr.get("bio", ""))
    if bio and bio not in purpose:
        purpose = bio if not purpose else purpose + " " + bio

    # Normalise compiled date
    compiled = ldr.get("compiled", "April 2026")
    updated = "2026-04-25"

    return {
        "id": leader_id,
        "full_name": fix(ldr.get("name", leader_id)),
        "title": fix(ldr.get("full_title", ldr.get("position", ""))),
        "updated": updated,
        "leader": {
            "name": fix(ldr.get("name", "")),
            "position": fix(ldr.get("position", "")),
            "in_office_since": fix(ldr.get("in_office_since", "")),
            "compiled": fix(compiled),
            "purpose": purpose,
            "based_on": fix_deep(ldr.get("based_on", [])),
        },
        "dimensions": dimensions,
        "synthesis": {
            "guiding_principles": guiding_principles,
            "key_external_analysis_quote": key_quote,
            "sources": fix_deep(synth_raw.get("sources", [])),
        },
    }


def merge_into_existing(existing: dict, new_profile: dict) -> dict:
    merged = dict(existing)
    existing_dims = existing.get("dimensions", {})
    new_dims = new_profile.get("dimensions", {})

    updated_dims = dict(existing_dims)
    for key, new_dim in new_dims.items():
        if new_dim is None:
            continue
        existing_dim = existing_dims.get(key) or {}
        has_evidence = bool(existing_dim.get("_evidence"))
        has_position = bool(
            existing_dim.get("assessed_position") or
            existing_dim.get("core_thesis") or
            existing_dim.get("overall_assessment")
        )
        if not has_evidence and not has_position:
            updated_dims[key] = new_dim
        elif key == "consistency_score":
            existing_cs = dict(existing_dim)
            if not existing_cs.get("ratings") and new_dim.get("ratings"):
                existing_cs["ratings"] = new_dim["ratings"]
                updated_dims[key] = existing_cs

    merged["dimensions"] = updated_dims
    if not merged.get("title") and new_profile.get("title"):
        merged["title"] = new_profile["title"]
    if not merged.get("full_name") and new_profile.get("full_name"):
        merged["full_name"] = new_profile["full_name"]
    return merged


def main():
    with open(SOURCE, encoding=ENCODING_UTF) as f:
        all_data = json.load(f)

    LEADERS_DIR.mkdir(parents=True, exist_ok=True)

    for leader_id, raw in all_data.items():
        path = LEADERS_DIR / (leader_id + "_profile.json")
        new_profile = build_profile(leader_id, raw)

        if path.exists():
            with open(path, encoding=ENCODING_UTF) as f:
                existing = json.load(f)
            final = merge_into_existing(existing, new_profile)
            action = "MERGED "
        else:
            final = new_profile
            action = "CREATED"

        path.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding=ENCODING_UTF)
        print(f"  {action}: {path.name}")

    print(f"\nDone — {len(all_data)} profiles written.")


if __name__ == "__main__":
    main()
