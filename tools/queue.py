"""
Shared queue helpers used by scrapers, extractors, review tools, and the MCP server.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).parent.parent
QUEUE_ROOT   = PROJECT_ROOT / "data" / "queue"
PENDING_DIR  = QUEUE_ROOT / "pending"
APPROVED_DIR = QUEUE_ROOT / "approved"
REJECTED_DIR = QUEUE_ROOT / "rejected"

QueueStatus = Literal["pending", "approved", "rejected"]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _item_path(status: QueueStatus, item_id: str) -> Path:
    dirs = {"pending": PENDING_DIR, "approved": APPROVED_DIR, "rejected": REJECTED_DIR}
    return dirs[status] / f"{item_id}.json"


def submit(
    *,
    item_type: str,
    leader_id: str,
    dimension: str | None = None,
    source_url: str,
    source_date: str,
    extracted_claim: str,
    exact_quote: str = "",
    confidence: float = 0.0,
    extracted_by: str = "claude-sonnet-4-6",
    extra: dict | None = None,
) -> str:
    """Write a new item to pending queue. Returns the item_id."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    item_id = f"{source_date}-{leader_id}-{dimension or item_type}-{uuid.uuid4().hex[:6]}"
    item: dict = {
        "id":              item_id,
        "type":            item_type,
        "leader_id":       leader_id,
        "dimension":       dimension,
        "source_url":      source_url,
        "source_date":     source_date,
        "extracted_claim": extracted_claim,
        "exact_quote":     exact_quote,
        "confidence":      confidence,
        "extracted_by":    extracted_by,
        "extracted_at":    _utcnow(),
        "status":          "pending",
        "reviewer_notes":  "",
        **(extra or {}),
    }
    path = _item_path("pending", item_id)
    path.write_text(json.dumps(item, indent=2, ensure_ascii=False))
    return item_id


def list_queue(status: QueueStatus = "pending") -> list[dict]:
    dirs = {"pending": PENDING_DIR, "approved": APPROVED_DIR, "rejected": REJECTED_DIR}
    d = dirs[status]
    if not d.exists():
        return []
    items = [json.loads(f.read_text()) for f in sorted(d.glob("*.json")) if f.suffix == ".json"]
    return [i for i in items if i.get("id")]  # skip .gitkeep etc


def get_item(item_id: str) -> tuple[dict, QueueStatus] | tuple[None, None]:
    for status in ("pending", "approved", "rejected"):
        path = _item_path(status, item_id)  # type: ignore[arg-type]
        if path.exists():
            return json.loads(path.read_text()), status  # type: ignore[return-value]
    return None, None


def move(item_id: str, from_status: QueueStatus, to_status: QueueStatus,
         notes: str = "") -> dict:
    src = _item_path(from_status, item_id)
    if not src.exists():
        raise FileNotFoundError(f"Queue item not found: {item_id} in {from_status}/")
    item = json.loads(src.read_text())
    item["status"] = to_status
    item["reviewer_notes"] = notes
    item["reviewed_at"] = _utcnow()
    dst_dir = {"pending": PENDING_DIR, "approved": APPROVED_DIR, "rejected": REJECTED_DIR}[to_status]
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    dst.write_text(json.dumps(item, indent=2, ensure_ascii=False))
    src.unlink()
    return item


def approve(item_id: str, notes: str = "") -> dict:
    return move(item_id, "pending", "approved", notes)


def reject(item_id: str, reason: str) -> dict:
    return move(item_id, "pending", "rejected", reason)
