#!/usr/bin/env python3
"""
Precedent MCP Server
Exposes project data and queue operations as MCP tools so Claude can
read live data and take actions during conversations.

Setup (once):
    pip install fastmcp
    # Add to ~/.claude/settings.json:
    {
      "mcpServers": {
        "precedent": {
          "command": "python",
          "args": ["mcp/server.py"],
          "cwd": "/path/to/precedent"
        }
      }
    }

Run manually:
    python mcp/server.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from fastmcp import FastMCP
except ImportError:
    print("fastmcp not installed. Run: pip install fastmcp", file=sys.stderr)
    sys.exit(1)

from tools.queue import (
    PROJECT_ROOT, approve, list_queue, reject, submit
)

mcp = FastMCP("Precedent — Cambodia Political Intelligence")

LEADERS_DIR   = PROJECT_ROOT / "data" / "leaders"
CONFLICTS_DIR = PROJECT_ROOT / "data" / "conflicts"
TWINS_DIR     = PROJECT_ROOT / "data" / "twins"
HIST_PATH     = PROJECT_ROOT / "data" / "historical" / "historical_cases.json"
BRIEF_DIR     = PROJECT_ROOT / "site" / "docs" / "brief"


# ── queue tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def get_pending_queue() -> list[dict]:
    """Return all items pending review, sorted oldest first."""
    return list_queue("pending")


@mcp.tool()
def get_queue_stats() -> dict:
    """Return counts of pending/approved/rejected items."""
    return {
        "pending":  len(list_queue("pending")),
        "approved": len(list_queue("approved")),
        "rejected": len(list_queue("rejected")),
    }


@mcp.tool()
def approve_item(item_id: str, notes: str = "") -> dict:
    """Approve a pending queue item. Optionally add notes."""
    return approve(item_id, notes)


@mcp.tool()
def reject_item(item_id: str, reason: str) -> dict:
    """Reject a pending queue item with a required reason."""
    if not reason:
        raise ValueError("reason is required")
    return reject(item_id, reason)


@mcp.tool()
def add_to_queue(
    leader_id: str,
    dimension: str,
    source_url: str,
    source_date: str,
    extracted_claim: str,
    exact_quote: str = "",
    confidence: float = 0.8,
) -> str:
    """Submit a new claim to the pending review queue. Returns the item_id."""
    return submit(
        item_type="claim_extraction",
        leader_id=leader_id,
        dimension=dimension,
        source_url=source_url,
        source_date=source_date,
        extracted_claim=extracted_claim,
        exact_quote=exact_quote,
        confidence=confidence,
    )


# ── data read tools ───────────────────────────────────────────────────────────

@mcp.tool()
def get_leader_profile(leader_id: str) -> dict:
    """Return the full current profile for a leader by ID (e.g. hun_manet)."""
    path = LEADERS_DIR / f"{leader_id}_profile.json"
    if not path.exists():
        raise FileNotFoundError(f"No profile found for leader_id={leader_id!r}")
    return json.loads(path.read_text())


@mcp.tool()
def list_leaders() -> list[dict]:
    """Return id, full_name, and title for all leaders."""
    result = []
    for p in sorted(LEADERS_DIR.glob("*_profile.json")):
        try:
            data = json.loads(p.read_text())
            result.append({
                "id":        data.get("id", p.stem.replace("_profile", "")),
                "full_name": data.get("full_name", ""),
                "title":     data.get("title", ""),
            })
        except (json.JSONDecodeError, OSError):
            pass
    return result


@mcp.tool()
def get_conflicts(leader_id: str | None = None) -> list[dict]:
    """Return detected conflicts, optionally filtered by leader_id."""
    results = []
    if not CONFLICTS_DIR.exists():
        return results
    for f in sorted(CONFLICTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            for c in data.get("conflicts", []):
                if leader_id is None or leader_id in (c.get("leader_a"), c.get("leader_b")):
                    results.append(c)
        except (json.JSONDecodeError, OSError):
            pass
    return results


@mcp.tool()
def get_historical_cases(category: str | None = None) -> list[dict]:
    """Return historical cases, optionally filtered by category or keyword."""
    if not HIST_PATH.exists():
        return []
    data = json.loads(HIST_PATH.read_text())
    cases = data if isinstance(data, list) else data.get("cases", [])
    if category:
        kw = category.lower()
        cases = [c for c in cases if kw in json.dumps(c).lower()]
    return cases


@mcp.tool()
def get_twin_matches(leader_id: str | None = None) -> list[dict]:
    """Return twin match results, optionally filtered by leader_id."""
    results = []
    if not TWINS_DIR.exists():
        return results
    for f in sorted(TWINS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if leader_id is None or data.get("leader_id") == leader_id:
                results.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return results


@mcp.tool()
def get_predictions(status: str = "active") -> list[dict]:
    """
    Return predictions filtered by status (active/resolved/expired).
    Predictions are stored in data/predictions.json.
    """
    pred_path = PROJECT_ROOT / "data" / "predictions.json"
    if not pred_path.exists():
        return []
    data = json.loads(pred_path.read_text())
    preds = data if isinstance(data, list) else data.get("predictions", [])
    if status == "all":
        return preds
    return [p for p in preds if p.get("status", "active") == status]


@mcp.tool()
def update_prediction_status(prediction_id: str, status: str, outcome: str = "") -> dict:
    """
    Update the status of a prediction (active → resolved or expired).
    status must be 'active', 'resolved', or 'expired'.
    """
    pred_path = PROJECT_ROOT / "data" / "predictions.json"
    if not pred_path.exists():
        raise FileNotFoundError("data/predictions.json not found")

    data = json.loads(pred_path.read_text())
    preds = data if isinstance(data, list) else data.get("predictions", [])

    for p in preds:
        if p.get("id") == prediction_id:
            p["status"]     = status
            p["outcome"]    = outcome
            p["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            break
    else:
        raise ValueError(f"Prediction {prediction_id!r} not found")

    if isinstance(data, list):
        pred_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        data["predictions"] = preds
        pred_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return {"updated": prediction_id, "status": status}


@mcp.tool()
def check_position_drift(leader_id: str) -> dict:
    """
    Compare the most recent extraction for each dimension against the
    current profile and flag dimensions where the extracted claim differs
    significantly from the published position.
    """
    extracted_dir = PROJECT_ROOT / "data" / "extracted" / leader_id
    if not extracted_dir.exists():
        return {"leader_id": leader_id, "drift": [], "message": "No extractions found"}

    profile_path = LEADERS_DIR / f"{leader_id}_profile.json"
    if not profile_path.exists():
        return {"leader_id": leader_id, "drift": [], "message": "No profile found"}

    profile = json.loads(profile_path.read_text())
    dims = profile.get("dimensions", {})

    # collect latest extraction per dimension
    latest: dict[str, dict] = {}
    for f in sorted(extracted_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            for dim_key in dims:
                if dim_key in data:
                    latest[dim_key] = {"file": f.name, "data": data[dim_key]}
        except (json.JSONDecodeError, OSError):
            pass

    drift = []
    for dim_key, ext in latest.items():
        pub = dims.get(dim_key, {})
        pub_pos = pub.get("assessed_position", pub.get("position", "")) if isinstance(pub, dict) else ""
        ext_pos = ""
        if isinstance(ext["data"], dict):
            ext_pos = ext["data"].get("assessed_position", ext["data"].get("position", ""))

        if pub_pos and ext_pos and pub_pos[:100] != ext_pos[:100]:
            drift.append({
                "dimension":           dim_key,
                "published_position":  pub_pos[:200],
                "extracted_position":  ext_pos[:200],
                "source_file":         ext["file"],
            })

    return {
        "leader_id": leader_id,
        "drift_count": len(drift),
        "drift": drift,
    }


@mcp.tool()
def get_latest_brief() -> str:
    """Return the content of the latest weekly brief (HTML stripped to text)."""
    latest = BRIEF_DIR / "latest.html"
    if not latest.exists():
        return "No brief generated yet. Run: python site/generate_brief.py"
    import re
    html = latest.read_text()
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:4000]


# ── run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
