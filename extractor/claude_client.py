"""
Claude API client for extracting mental-model fields from a single document.

Usage
-----
    from extractor.claude_client import extract_fields

    fields = extract_fields(
        document="<raw text>",
        leader_id="hun_manet",
        source_url="https://akp.gov.kh/...",
        source_date="2024-08-17",
    )
    # fields is a dict ready to merge into a LeaderProfile

Environment
-----------
    ANTHROPIC_API_KEY   Required. Raises KeyError if absent.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import anthropic

from extractor.claude_prompts import EXTRACTION_SYSTEM

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"


def _load_api_key() -> str:
    return os.environ["ANTHROPIC_API_KEY"]


def _build_user_message(document: str, leader_id: str) -> str:
    return f"Leader ID: {leader_id}\n\nDocument:\n{document}"


def _parse_response(text: str) -> dict[str, Any]:
    """Extract the JSON object from Claude's response text."""
    # Strip markdown code fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    payload = match.group(1) if match else text.strip()
    return json.loads(payload)


def _attach_source_meta(
    fields: dict[str, Any],
    source_url: str,
    source_date: str,
) -> dict[str, Any]:
    """
    Merge caller-supplied url + date into each field's source block.
    Claude returns value, quote, confidence; we add the document provenance.
    """
    result: dict[str, Any] = {}
    for field_name, field_data in fields.items():
        if field_data is None:
            continue
        result[field_name] = {
            "value": field_data["value"],
            "source": {
                "url": source_url,
                "date": source_date,
                "quote": field_data["quote"],
                "confidence": field_data["confidence"],
            },
        }
    return result


def extract_fields(
    document: str,
    leader_id: str,
    source_url: str,
    source_date: str,
) -> dict[str, Any]:
    """
    Send one document to Claude Sonnet and return a partial LeaderProfile dict.

    Parameters
    ----------
    document    Raw text of the speech, article, or policy document.
    leader_id   Snake-case leader identifier, e.g. 'hun_manet'.
    source_url  Canonical URL of the source document.
    source_date ISO 8601 date string, e.g. '2024-08-17'.

    Returns
    -------
    Dict with up to 7 field entries, each shaped as:
        { "value": str, "source": { url, date, quote, confidence } }
    Fields absent from the document are omitted entirely.

    Raises
    ------
    KeyError        ANTHROPIC_API_KEY not set.
    json.JSONDecodeError  Claude returned malformed JSON.
    anthropic.APIError   Network or API-level failure.
    """
    client = anthropic.Anthropic(api_key=_load_api_key())

    logger.info("Sending document to Claude (%d chars) for leader=%s", len(document), leader_id)

    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=EXTRACTION_SYSTEM,
        messages=[
            {"role": "user", "content": _build_user_message(document, leader_id)},
        ],
    )

    raw_text: str = message.content[0].text
    logger.debug("Claude raw response:\n%s", raw_text)

    fields = _parse_response(raw_text)
    return _attach_source_meta(fields, source_url, source_date)
