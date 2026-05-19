#!/usr/bin/env python3
"""
Self-feedback loop: analyze rejection history and generate an improved
extraction prompt candidate. Run monthly.

Usage:
    python tools/feedback_loop.py [--min-rejections 5]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(format="%(levelname)-8s  %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


def _load_rejections() -> list[dict]:
    from tools.queue import list_queue
    return list_queue("rejected")


def _load_current_prompt() -> str:
    path = PROJECT_ROOT / "extractor" / "claude_prompts.py"
    return path.read_text() if path.exists() else ""


def _analyze_patterns(rejections: list[dict]) -> str:
    """Group rejections by reason and dimension."""
    by_dim: dict[str, list[str]] = {}
    for r in rejections:
        dim    = r.get("dimension", "unknown")
        reason = r.get("reviewer_notes", "")
        by_dim.setdefault(dim, []).append(reason)

    lines = []
    for dim, reasons in sorted(by_dim.items()):
        lines.append(f"  {dim} ({len(reasons)} rejections):")
        for r in reasons[:3]:
            lines.append(f"    - {r}")
    return "\n".join(lines)


def run(min_rejections: int = 5) -> None:
    import anthropic

    rejections = _load_rejections()
    if len(rejections) < min_rejections:
        log.info("Only %d rejections — need at least %d to run. Skipping.",
                 len(rejections), min_rejections)
        return

    log.info("Analyzing %d rejections...", len(rejections))
    pattern_summary = _analyze_patterns(rejections)
    current_prompt  = _load_current_prompt()

    rejection_detail = "\n".join(
        f"- Leader: {r.get('leader_id')}  Dim: {r.get('dimension')}\n"
        f"  Claim: {r.get('extracted_claim','')[:150]}\n"
        f"  Reason: {r.get('reviewer_notes','')}"
        for r in rejections[-30:]
    )

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{
            "role": "user",
            "content": f"""You are improving an AI extraction prompt based on human reviewer feedback.

The current extraction prompt file is:
```python
{current_prompt[:3000]}
```

Rejection pattern summary:
{pattern_summary}

Detailed recent rejections (last 30):
{rejection_detail}

Your task:
1. Identify the 3 most common failure patterns from the rejections.
2. Write specific, concrete improvements to the extraction instructions to prevent these patterns.
3. Output ONLY the improved prompt text — not the full Python file, just the system/user prompt strings.
4. Maintain all existing correct behaviors.
5. Add explicit examples of what to AVOID based on the rejection patterns.

Be specific. Do not be vague. If the rejections show Claude is inventing quotes, add an explicit instruction not to invent quotes."""
        }]
    )

    improved = response.content[0].text
    candidate_path = PROJECT_ROOT / "extractor" / "claude_prompts_candidate.txt"
    candidate_path.write_text(improved)
    log.info("Improved prompt candidate saved: %s", candidate_path)
    log.info("Review the candidate, then manually update extractor/claude_prompts.py")

    # save analysis summary
    summary = {
        "run_date": __import__("datetime").datetime.utcnow().isoformat(),
        "rejection_count": len(rejections),
        "pattern_summary": pattern_summary,
        "candidate_path": str(candidate_path),
    }
    (PROJECT_ROOT / "data" / "feedback_loop_summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    log.info("Summary saved to data/feedback_loop_summary.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate improved extraction prompt from rejections.")
    parser.add_argument("--min-rejections", type=int, default=5,
                        help="Minimum rejections needed to run (default: 5)")
    args = parser.parse_args()
    run(min_rejections=args.min_rejections)


if __name__ == "__main__":
    main()
