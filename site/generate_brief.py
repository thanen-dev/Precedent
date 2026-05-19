#!/usr/bin/env python3
"""
Phase 3 — Weekly Brief Generator
Reads all leader JSON files + conflicts, calls Claude API,
saves output to site/docs/brief/YYYY-MM-DD.html and latest.html

Usage:
  ANTHROPIC_API_KEY=sk-... python3 site/generate_brief.py

Env vars:
  ANTHROPIC_API_KEY  required
  BRIEF_DATE         optional override, default = today (YYYY-MM-DD)
"""

import html as html_lib
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests

# ── paths ──────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent.parent
LEADERS_DIR = ROOT / "data" / "leaders"
HIST_PATH   = ROOT / "data" / "historical" / "historical_cases.json"
TWINS_DIR   = ROOT / "data" / "twins"
BRIEF_DIR   = ROOT / "site" / "docs" / "brief"
BRIEF_DIR.mkdir(parents=True, exist_ok=True)

# ── Claude config ─────────────────────────────────────────────────────────────

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL   = "claude-sonnet-4-6"
MAX_TOK = 2000

# ── data loading ──────────────────────────────────────────────────────────────

def _load_leaders() -> list[dict]:
    profiles = []
    for p in sorted(LEADERS_DIR.glob("*_profile.json")):
        try:
            profiles.append(json.loads(p.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return profiles


def _load_historical() -> list[dict]:
    if not HIST_PATH.exists():
        return []
    try:
        data = json.loads(HIST_PATH.read_text())
        return data if isinstance(data, list) else data.get("cases", [])
    except (json.JSONDecodeError, OSError):
        return []


def _load_twins() -> list[dict]:
    twins = []
    if not TWINS_DIR.exists():
        return twins
    for p in sorted(TWINS_DIR.glob("*.json")):
        try:
            twins.append(json.loads(p.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return twins


def _leader_summary(p: dict) -> str:
    name  = p.get("full_name", p.get("id", "Unknown"))
    title = p.get("title", "")
    dims  = p.get("dimensions", {})

    def _val(key: str) -> str:
        d = dims.get(key)
        if not isinstance(d, dict):
            return ""
        for field in ("assessed_position", "core_thesis", "overall_assessment",
                      "position", "assessment", "summary"):
            v = d.get(field, "")
            if isinstance(v, str) and len(v) > 10:
                return v[:200]
        return ""

    lines = [f"## {name} ({title})"]
    for key in ("growth_theory", "risk_tolerance", "institution_vs_relationship",
                "global_positioning_logic", "time_horizon"):
        val = _val(key)
        if val:
            lines.append(f"- {key.replace('_',' ').title()}: {val}")
    return "\n".join(lines)


def _build_context(leaders: list[dict], cases: list[dict], twins: list[dict]) -> str:
    sections = ["# CAMBODIA POLITICAL INTELLIGENCE CONTEXT\n"]

    sections.append("## LEADER MENTAL MODELS")
    for p in leaders:
        sections.append(_leader_summary(p))

    if cases:
        sections.append("\n## HISTORICAL CASES (abbreviated)")
        for c in cases[:5]:
            cid    = c.get("case_id", "")
            name   = c.get("country_name", "")
            period = c.get("period", "")
            lesson = c.get("lesson", "")
            if isinstance(lesson, dict):
                lesson = next(iter(lesson.values()), "")
            sections.append(f"- {cid} | {name} {period}: {str(lesson)[:200]}")

    if twins:
        sections.append("\n## RECENT TWIN MATCHES")
        for t in twins[:4]:
            sig = t.get("signal", "")[:150]
            for m in (t.get("matches", []) or [])[:1]:
                score   = int(m.get("similarity_score", 0) * 100)
                country = m.get("country", "")
                risk    = m.get("risk_flag", "")
                sections.append(f"- Signal: {sig} → {score}% match {country} ({risk})")

    return "\n".join(sections)


# ── prompt ────────────────────────────────────────────────────────────────────

BRIEF_SYSTEM = """You are the lead analyst for Precedent, a political intelligence system tracking Cambodia's senior leadership. Your task is to generate a structured weekly intelligence brief.

Output EXACTLY five sections with these exact labels (uppercase, followed by colon):

SITUATION ASSESSMENT:
[2-3 sentences on Cambodia's current macro-political and economic situation based on the leader data]

DOCTRINE WATCH:
[The 2-3 most significant leadership positions or doctrine signals worth tracking this week]

CONFLICT ALERT:
[The single most dangerous internal government contradiction and what it means for policy coherence]

HISTORICAL PARALLEL:
[The strongest historical twin match and what it predicts for Cambodia's trajectory]

WATCH LIST:
[3-5 specific things to monitor in the coming week, as a bulleted list]

Be specific, analytical, and grounded in the data provided. Write for a sophisticated reader who understands Southeast Asian political economy. Do not hedge excessively. Make clear assessments."""


def _call_claude(context: str, brief_date: str) -> str:
    if not API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

    user_msg = f"Generate the weekly intelligence brief for the week of {brief_date}.\n\n{context}"

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": MAX_TOK,
            "system": BRIEF_SYSTEM,
            "messages": [{"role": "user", "content": user_msg}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]


# ── HTML rendering ─────────────────────────────────────────────────────────────

SECTION_META = {
    "SITUATION ASSESSMENT": ("◈", "situation"),
    "DOCTRINE WATCH":       ("◈", "doctrine"),
    "CONFLICT ALERT":       ("⚠", "conflict"),
    "HISTORICAL PARALLEL":  ("◈", "parallel"),
    "WATCH LIST":           ("◈", "watchlist"),
}


def _parse_brief(text: str) -> list[tuple[str, str]]:
    """Split brief text into (label, content) pairs."""
    sections = []
    current_label = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        matched = False
        for key in SECTION_META:
            if stripped.upper().startswith(key + ":"):
                if current_label:
                    sections.append((current_label, "\n".join(current_lines).strip()))
                current_label = key
                rest = stripped[len(key) + 1:].strip()
                current_lines = [rest] if rest else []
                matched = True
                break
        if not matched and current_label:
            current_lines.append(line)

    if current_label:
        sections.append((current_label, "\n".join(current_lines).strip()))

    return sections


def _content_to_html(label: str, content: str) -> str:
    """Convert section content to HTML, handling bullet lists."""
    lines = content.splitlines()
    out = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        is_bullet = stripped.startswith(("- ", "• ", "* "))
        if is_bullet:
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = stripped.lstrip("-•* ").strip()
            out.append(f"  <li>{html_lib.escape(item)}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            if stripped:
                out.append(f"<p>{html_lib.escape(stripped)}</p>")

    if in_list:
        out.append("</ul>")

    is_alert = label == "CONFLICT ALERT"
    extra_class = " brief-section-alert" if is_alert else ""
    return "\n".join(out), extra_class


def _render_brief_html(brief_date: str, sections: list[tuple[str, str]],
                       nav_links: str) -> str:
    date_obj = datetime.strptime(brief_date, "%Y-%m-%d")
    date_display = date_obj.strftime("%B %-d, %Y")

    sections_html = ""
    for label, content in sections:
        icon, _ = SECTION_META.get(label, ("◈", ""))
        body_html, extra_class = _content_to_html(label, content)
        sections_html += f"""
<div class="brief-section{extra_class}">
  <div class="brief-section-label">{icon} {html_lib.escape(label)}</div>
  <div class="brief-section-body">{body_html}</div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Brief — {html_lib.escape(date_display)} | Precedent</title>
<link rel="stylesheet" href="../style.css">
<style>
.brief-hero {{
  background: var(--navy);
  color: #f4f6f9;
  padding: 3rem;
}}
.brief-hero-eyebrow {{
  font-family: var(--mono);
  font-size: var(--t-xs);
  letter-spacing: 0.20em;
  text-transform: uppercase;
  color: rgba(244,246,249,0.50);
  margin-bottom: 0.75rem;
}}
.brief-date-display {{
  font-family: var(--bebas);
  font-size: clamp(2rem,1.5rem+3vw,4rem);
  letter-spacing: 0.04em;
  color: #f4f6f9;
  line-height: 1.05;
}}
.brief-nav {{
  display: flex;
  gap: 1rem;
  margin-top: 1.5rem;
  flex-wrap: wrap;
}}
.brief-nav a {{
  font-family: var(--mono);
  font-size: var(--t-xs);
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: rgba(244,246,249,0.60);
  border: 1px solid rgba(244,246,249,0.20);
  padding: 0.3rem 0.8rem;
  transition: color 0.1s, border-color 0.1s;
}}
.brief-nav a:hover {{ color: #f4f6f9; border-color: rgba(244,246,249,0.50); }}

.brief-section {{
  border: 1px solid var(--b-dim);
  border-top: none;
  background: var(--surface);
}}
.brief-section:first-child {{ border-top: 1px solid var(--b-dim); margin-top: 2rem; }}
.brief-section-label {{
  font-family: var(--mono);
  font-size: var(--t-xs);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--navy-mid);
  padding: 0.55rem 1.25rem;
  background: var(--surface2);
  border-bottom: 1px solid var(--b-dim);
  font-weight: 500;
}}
.brief-section-alert .brief-section-label {{
  color: #b02020;
  background: rgba(176,32,32,0.06);
}}
.brief-section-alert {{
  border-left: 3px solid #b02020;
}}
.brief-section-body {{
  padding: 1.25rem 1.5rem;
  font-family: var(--serif);
  font-size: var(--t-base);
  line-height: 1.85;
  color: var(--text);
}}
.brief-section-body p {{ margin-bottom: 0.75rem; }}
.brief-section-body p:last-child {{ margin-bottom: 0; }}
.brief-section-body ul {{
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}}
.brief-section-body li {{
  padding-left: 1.25rem;
  position: relative;
  font-family: var(--serif);
  font-size: var(--t-base);
  line-height: 1.75;
}}
.brief-section-body li::before {{
  content: "→";
  position: absolute;
  left: 0;
  color: var(--accent);
  font-family: var(--mono);
}}
.brief-archive-note {{
  margin-top: 2rem;
  padding: 1rem 1.25rem;
  border: 1px solid var(--b-dim);
  background: var(--surface2);
  font-family: var(--mono);
  font-size: var(--t-xs);
  color: var(--muted);
  letter-spacing: 0.06em;
}}
</style>
</head>
<body>
<nav class="masthead" aria-label="Main navigation">
  <div class="masthead-inner">
    <div class="masthead-brand">
      <a href="../index.html" class="masthead-wordmark">Precedent</a>
      <span class="masthead-version">v0.3</span>
    </div>
    <nav class="masthead-nav">
      <a href="../leaders.html">Leaders</a>
      <a href="../conflicts.html">Conflicts</a>
      <a href="../twins.html">Twins</a>
      <a href="../cases.html">Cases</a>
      <a href="../analyze.html">Analyze</a>
      <a href="latest.html" class="active">Brief</a>
    </nav>
  </div>
</nav>

<div class="brief-hero">
  <div class="brief-hero-eyebrow">Weekly Intelligence Brief</div>
  <div class="brief-date-display">Week of {html_lib.escape(date_display)}</div>
  <div class="brief-nav">
    {nav_links}
  </div>
</div>

<div class="container" style="max-width:860px">
  {sections_html}
  <div class="brief-archive-note">
    Generated by Precedent Intelligence Engine · {html_lib.escape(date_display)} ·
    <a href="../methodology.html" style="color:var(--accent)">Methodology</a>
  </div>
</div>

<footer class="site-footer">
  <div class="footer-inner">
    <div>
      <a href="../index.html" class="footer-wordmark">Precedent</a>
      <p class="footer-about">Cambodia Political Intelligence — Weekly briefs generated from structured leader profiles and historical twin analysis.</p>
    </div>
  </div>
  <div class="footer-base">© 2025 Precedent · Open-source · GitHub Pages</div>
</footer>
</body>
</html>"""


def _render_archive_index(briefs: list[str]) -> str:
    """Render an index page listing all available briefs."""
    items = ""
    for filename in sorted(briefs, reverse=True):
        date_str = filename.replace(".html", "")
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            label = d.strftime("%B %-d, %Y")
        except ValueError:
            label = date_str
        items += (
            f'<a href="{html_lib.escape(filename)}" class="reading-step">'
            f'<span class="reading-step-num">◈</span>'
            f'<span class="reading-step-label">{html_lib.escape(label)}</span>'
            f'</a>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brief Archive | Precedent</title>
<link rel="stylesheet" href="../style.css">
</head>
<body>
<nav class="masthead">
  <div class="masthead-inner">
    <div class="masthead-brand">
      <a href="../index.html" class="masthead-wordmark">Precedent</a>
      <span class="masthead-version">v0.3</span>
    </div>
    <nav class="masthead-nav">
      <a href="../leaders.html">Leaders</a>
      <a href="../conflicts.html">Conflicts</a>
      <a href="../twins.html">Twins</a>
      <a href="../cases.html">Cases</a>
      <a href="../analyze.html">Analyze</a>
      <a href="latest.html" class="active">Brief</a>
    </nav>
  </div>
</nav>
<div class="container" style="max-width:860px">
  <div class="section-label" style="margin-bottom:1.5rem"><span class="section-marker">◈</span>Brief Archive</div>
  <div class="reading-path" style="flex-direction:column;overflow:unset">
    {items if items else '<div class="empty-state">No briefs generated yet.</div>'}
  </div>
</div>
</body>
</html>"""


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Generate weekly intelligence brief.")
    parser.add_argument("--draft-only", action="store_true",
                        help="Save to brief/drafts/ instead of publishing as latest.html")
    parser.add_argument("--date", default=None,
                        help="Override date (YYYY-MM-DD, default: today)")
    args = parser.parse_args()

    brief_date = args.date or os.environ.get("BRIEF_DATE", date.today().isoformat())
    draft_only = args.draft_only

    print(f"Generating brief for {brief_date}{' (draft)' if draft_only else ''}...")

    leaders  = _load_leaders()
    cases    = _load_historical()
    twins    = _load_twins()

    print(f"  Loaded {len(leaders)} leaders, {len(cases)} cases, {len(twins)} twins")

    if not API_KEY:
        print("  ANTHROPIC_API_KEY not set — skipping.")
        return

    context  = _build_context(leaders, cases, twins)
    raw_text = _call_claude(context, brief_date)
    sections = _parse_brief(raw_text)
    print(f"  Parsed {len(sections)} sections")

    existing = sorted([p.name for p in BRIEF_DIR.glob("[0-9]*.html")], reverse=True)
    nav_links = '<a href="index.html">← Archive</a>'
    if existing:
        nav_links += f' <a href="{html_lib.escape(existing[0])}">Latest →</a>'

    html_out = _render_brief_html(brief_date, sections, nav_links)

    if draft_only:
        draft_dir = BRIEF_DIR / "drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = draft_dir / f"{brief_date}.html"
        draft_path.write_text(html_out)
        print(f"  Draft saved: {draft_path}")
        print("  Review with: python tools/review.py --type brief_draft")
    else:
        dated_path  = BRIEF_DIR / f"{brief_date}.html"
        latest_path = BRIEF_DIR / "latest.html"
        dated_path.write_text(html_out)
        latest_path.write_text(html_out)
        print(f"  Written: {dated_path}")
        print(f"  Written: {latest_path}")

        all_briefs = sorted([p.name for p in BRIEF_DIR.glob("[0-9]*.html")], reverse=True)
        archive_html = _render_archive_index(all_briefs)
        (BRIEF_DIR / "index.html").write_text(archive_html)
        print(f"  Updated: {BRIEF_DIR / 'index.html'}")

    print("Done.")


if __name__ == "__main__":
    main()
