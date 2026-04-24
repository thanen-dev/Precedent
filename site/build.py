#!/usr/bin/env python3
"""
Build the Precedent static site into site/docs/.

Reads from:
  data/leaders/*.json
  data/historical/historical_cases.json
  data/twins/*.json           (may be empty)
  data/conflicts/*.json       (may be empty)

Writes to site/docs/:
  index.html, leaders.html, cases.html, conflicts.html, twins.html

Usage
-----
    python site/build.py
    python site/build.py --clean   # delete docs/ before building
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = Path(__file__).parent / "docs"

SITE_TITLE = "Precedent"
SITE_TAGLINE = "Political intelligence — Cambodia's decision-makers"


# ── data loading ──────────────────────────────────────────────────────────────

def load_leaders() -> list[dict]:
    profiles = []
    for path in sorted((DATA_DIR / "leaders").glob("*_profile.json")):
        try:
            profiles.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return profiles


def load_cases() -> list[dict]:
    path = DATA_DIR / "historical" / "historical_cases.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def load_twins() -> list[dict]:
    twins_dir = DATA_DIR / "twins"
    if not twins_dir.exists():
        return []
    results = []
    for path in sorted(twins_dir.glob("*.json")):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


def load_conflicts() -> list[dict]:
    conflicts_dir = DATA_DIR / "conflicts"
    if not conflicts_dir.exists():
        return []
    results = []
    for path in sorted(conflicts_dir.glob("*.json")):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


# ── shared HTML fragments ─────────────────────────────────────────────────────

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=IBM+Plex+Mono:wght@400;500&'
    'family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">'
)

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:       #0a0a08;
  --surface:  #111110;
  --border:   #222220;
  --text:     #f2f0eb;
  --muted:    #8a8880;
  --accent:   #d4930a;
  --accent-dim: #7a5406;
  --danger:   #c0392b;
  --warn:     #d4930a;
  --ok:       #27ae60;

  --mono: 'IBM Plex Mono', monospace;
  --sans: 'IBM Plex Sans', system-ui, sans-serif;

  --space-xs: 0.375rem;
  --space-sm: 0.75rem;
  --space-md: 1.25rem;
  --space-lg: 2.5rem;
  --space-xl: 5rem;

  --radius: 3px;
}

html { font-size: 16px; scroll-behavior: smooth; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-weight: 300;
  line-height: 1.65;
  min-height: 100vh;
}

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── layout ── */
.site-header {
  border-bottom: 1px solid var(--border);
  padding: var(--space-sm) var(--space-lg);
  display: flex;
  align-items: center;
  gap: var(--space-lg);
}

.site-header .wordmark {
  font-family: var(--mono);
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
}

.site-header nav {
  display: flex;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.site-header nav a {
  font-family: var(--mono);
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  transition: color 0.15s;
}

.site-header nav a:hover,
.site-header nav a.active { color: var(--text); text-decoration: none; }

.container {
  max-width: 1100px;
  margin: 0 auto;
  padding: var(--space-xl) var(--space-lg);
}

.page-heading {
  font-family: var(--mono);
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: var(--space-sm);
}

h1 {
  font-size: clamp(1.75rem, 3vw + 1rem, 3rem);
  font-weight: 300;
  line-height: 1.2;
  margin-bottom: var(--space-lg);
}

h2 {
  font-size: 1.125rem;
  font-weight: 500;
  margin-bottom: var(--space-sm);
}

h3 {
  font-family: var(--mono);
  font-size: 0.8rem;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: var(--space-xs);
}

p { margin-bottom: var(--space-sm); }
p:last-child { margin-bottom: 0; }

/* ── cards ── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-lg);
  margin-bottom: var(--space-md);
}

.card + .card { border-top: none; margin-top: calc(-1 * var(--space-md)); }

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.card-grid .card { margin-bottom: 0; }

/* ── leader card ── */
.leader-title {
  font-family: var(--mono);
  font-size: 0.7rem;
  color: var(--muted);
  margin-bottom: var(--space-xs);
}

.leader-name {
  font-size: 1.25rem;
  font-weight: 500;
  margin-bottom: var(--space-sm);
}

.completeness-bar {
  height: 2px;
  background: var(--border);
  border-radius: 1px;
  margin-bottom: var(--space-sm);
  overflow: hidden;
}

.completeness-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 1px;
}

.completeness-label {
  font-family: var(--mono);
  font-size: 0.65rem;
  color: var(--muted);
  margin-bottom: var(--space-md);
}

/* ── dimension grid ── */
.dim-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-sm) var(--space-lg);
  margin-bottom: var(--space-md);
}

.dim-item {}

.dim-key {
  font-family: var(--mono);
  font-size: 0.65rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent-dim);
  margin-bottom: 0.2rem;
}

.dim-value {
  font-size: 0.875rem;
  color: var(--text);
}

.dim-null {
  font-size: 0.8rem;
  color: var(--border);
  font-style: italic;
}

/* ── blockquote ── */
blockquote {
  border-left: 2px solid var(--accent-dim);
  padding-left: var(--space-md);
  margin: var(--space-md) 0;
  color: var(--muted);
  font-size: 0.9rem;
  font-style: italic;
}

/* ── badges ── */
.badge {
  display: inline-block;
  font-family: var(--mono);
  font-size: 0.6rem;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 0.2em 0.6em;
  border-radius: 2px;
  vertical-align: middle;
}

.badge-primary   { background: var(--accent-dim); color: var(--accent); }
.badge-secondary { background: var(--border); color: var(--muted); }
.badge-high      { background: rgba(192,57,43,0.15); color: var(--danger); }
.badge-medium    { background: rgba(212,147,10,0.15); color: var(--warn); }
.badge-low       { background: rgba(39,174,96,0.12); color: var(--ok); }

/* ── case card ── */
.case-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
}

.case-id {
  font-family: var(--mono);
  font-size: 0.7rem;
  color: var(--accent);
  margin-bottom: 0.2rem;
}

.case-period {
  font-family: var(--mono);
  font-size: 0.65rem;
  color: var(--muted);
}

/* ── conflict card ── */
.conflict-dim {
  font-family: var(--mono);
  font-size: 0.65rem;
  color: var(--accent);
  margin-bottom: var(--space-xs);
}

.conflict-leaders {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
  margin: var(--space-md) 0;
}

.conflict-side h4 {
  font-family: var(--mono);
  font-size: 0.7rem;
  color: var(--muted);
  margin-bottom: var(--space-xs);
}

.conflict-explanation {
  border-top: 1px solid var(--border);
  padding-top: var(--space-md);
  margin-top: var(--space-md);
}

.prediction-label {
  font-family: var(--mono);
  font-size: 0.65rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: var(--space-xs);
}

/* ── empty state ── */
.empty-state {
  text-align: center;
  padding: var(--space-xl) var(--space-lg);
  color: var(--muted);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}

.empty-state code {
  font-family: var(--mono);
  font-size: 0.8rem;
  color: var(--accent-dim);
}

/* ── source link ── */
.source-link {
  font-family: var(--mono);
  font-size: 0.65rem;
  color: var(--muted);
}

.source-link a { color: var(--muted); }
.source-link a:hover { color: var(--accent); }

/* ── score ── */
.score {
  font-family: var(--mono);
  font-size: 1.5rem;
  font-weight: 500;
  color: var(--accent);
}

/* ── stat row ── */
.stat-row {
  display: flex;
  gap: var(--space-xl);
  margin-bottom: var(--space-lg);
  flex-wrap: wrap;
}

.stat { text-align: left; }

.stat-value {
  font-family: var(--mono);
  font-size: 2rem;
  font-weight: 500;
  color: var(--accent);
  line-height: 1;
  margin-bottom: 0.25rem;
}

.stat-label {
  font-family: var(--mono);
  font-size: 0.65rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

/* ── mobile ── */
@media (max-width: 640px) {
  .container { padding: var(--space-lg) var(--space-md); }
  .site-header { padding: var(--space-sm) var(--space-md); gap: var(--space-md); }
  .dim-grid { grid-template-columns: 1fr; }
  .conflict-leaders { grid-template-columns: 1fr; }
  .stat-row { gap: var(--space-lg); }
  .case-header { flex-direction: column; }
}
"""


def _page(title: str, active_nav: str, body: str) -> str:
    nav_links = [
        ("index.html",     "Index",     "index"),
        ("leaders.html",   "Leaders",   "leaders"),
        ("cases.html",     "Cases",     "cases"),
        ("twins.html",     "Twins",     "twins"),
        ("conflicts.html", "Conflicts", "conflicts"),
    ]
    nav_html = " ".join(
        f'<a href="{href}" class="{"active" if key == active_nav else ""}">{label}</a>'
        for href, label, key in nav_links
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_lib.escape(title)} — {SITE_TITLE}</title>
{FONTS}
<style>{CSS}</style>
</head>
<body>
<header class="site-header">
  <span class="wordmark">{SITE_TITLE}</span>
  <nav>{nav_html}</nav>
</header>
{body}
</body>
</html>"""


def e(text: object) -> str:
    """HTML-escape a value; return em-dash for None/empty."""
    s = str(text) if text is not None else ""
    return html_lib.escape(s) if s.strip() else "<span class='dim-null'>—</span>"


# ── index page ────────────────────────────────────────────────────────────────

def build_index(leaders: list[dict], cases: list[dict], twins: list[dict], conflicts: list[dict]) -> str:
    total_conflicts = sum(len(c.get("conflicts", [])) for c in conflicts)
    total_twins = sum(len(t.get("matches", [])) for t in twins)

    stats = f"""
<div class="stat-row">
  <div class="stat">
    <div class="stat-value">{len(leaders)}</div>
    <div class="stat-label">Leaders profiled</div>
  </div>
  <div class="stat">
    <div class="stat-value">{len(cases)}</div>
    <div class="stat-label">Historical cases</div>
  </div>
  <div class="stat">
    <div class="stat-value">{total_twins}</div>
    <div class="stat-label">Twin matches</div>
  </div>
  <div class="stat">
    <div class="stat-value">{total_conflicts}</div>
    <div class="stat-label">Detected conflicts</div>
  </div>
</div>"""

    leader_cards = ""
    for p in leaders:
        name = e(p.get("full_name", p.get("id", "")))
        title = e(p.get("title", ""))
        dims = p.get("dimensions", {})
        populated = sum(
            1 for v in dims.values()
            if isinstance(v, dict) and any(v.get(k) for k in ("core_thesis", "stated_theory", "revealed_preference"))
        )
        total = len(dims) or 7
        pct = int((populated / total) * 100)
        leader_cards += f"""
<a href="leaders.html" style="text-decoration:none">
<div class="card">
  <div class="leader-title">{title}</div>
  <div class="leader-name">{name}</div>
  <div class="completeness-bar"><div class="completeness-bar-fill" style="width:{pct}%"></div></div>
  <div class="completeness-label">{pct}% profiled · {populated}/{total} dimensions</div>
</div>
</a>"""

    body = f"""
<div class="container">
  <div class="page-heading">Precedent / Cambodia Intelligence Engine</div>
  <h1>{SITE_TAGLINE}</h1>
  {stats}
  <h3>Leaders</h3>
  <div class="card-grid">{leader_cards}</div>
  <div class="card-grid">
    <a href="cases.html" style="text-decoration:none">
      <div class="card">
        <div class="page-heading">Historical Cases</div>
        <p style="color:var(--muted);font-size:.875rem">{len(cases)} documented structural analogues with causal analysis and policy lessons.</p>
      </div>
    </a>
    <a href="twins.html" style="text-decoration:none">
      <div class="card">
        <div class="page-heading">Twin Matches</div>
        <p style="color:var(--muted);font-size:.875rem">{total_twins} signal-to-case matches. Run twin_matcher.py to populate.</p>
      </div>
    </a>
    <a href="conflicts.html" style="text-decoration:none">
      <div class="card">
        <div class="page-heading">Detected Conflicts</div>
        <p style="color:var(--muted);font-size:.875rem">{total_conflicts} logical contradictions between leader doctrines. Run conflict_detector.py to populate.</p>
      </div>
    </a>
  </div>
</div>"""
    return _page("Overview", "index", body)


# ── leaders page ─────────────────────────────────────────────────────────────

def _dim_row(key: str, dim: object) -> str:
    label = key.replace("_", " ")
    if not isinstance(dim, dict):
        return f'<div class="dim-item"><div class="dim-key">{e(label)}</div><div class="dim-null">No data</div></div>'

    thesis = dim.get("core_thesis")
    stated = dim.get("stated_theory")
    if isinstance(stated, dict):
        stated = stated.get("summary")
    value = thesis or stated or dim.get("revealed_preference")

    evidence = dim.get("_evidence", [])
    source_html = ""
    if evidence and isinstance(evidence[0], dict):
        url = evidence[0].get("url", "")
        quote = evidence[0].get("quote", "")
        date = evidence[0].get("date", "")
        if url:
            source_html = f'<div class="source-link"><a href="{html_lib.escape(url)}" target="_blank" rel="noopener">↗ {e(date)}</a></div>'
        if quote:
            source_html = f'<blockquote>"{e(quote)}"</blockquote>' + source_html

    return f"""<div class="dim-item">
  <div class="dim-key">{e(label)}</div>
  <div class="dim-value">{e(value) if value else '<span class="dim-null">No data yet</span>'}</div>
  {source_html}
</div>"""


def build_leaders(leaders: list[dict]) -> str:
    sections = ""
    for p in leaders:
        leader_id = p.get("id", "")
        name = e(p.get("full_name", leader_id))
        title = e(p.get("title", ""))
        meta = p.get("leader", {})
        since = e(meta.get("in_office_since", ""))
        purpose = e(meta.get("purpose", ""))

        dims = p.get("dimensions", {})
        dim_html = '<div class="dim-grid">' + "".join(
            _dim_row(k, dims.get(k)) for k in (
                "growth_theory", "risk_tolerance", "time_horizon",
                "dependency_assumptions", "institution_vs_relationship",
                "global_positioning_logic", "consistency_score",
            )
        ) + "</div>"

        synth = p.get("synthesis", {})
        principles = synth.get("guiding_principles", [])
        principles_html = ""
        if principles:
            items = "".join(
                f"<li style='margin-bottom:.5rem'><strong style='font-family:var(--mono);font-size:.7rem;color:var(--accent-dim)'>{e(pr.get('dimension',''))}</strong><br>{e(pr.get('insight',''))}</li>"
                for pr in principles if isinstance(pr, dict)
            )
            principles_html = f"<h3>Synthesis</h3><ul style='padding-left:1.25rem;margin-bottom:var(--space-md)'>{items}</ul>"

        keq = synth.get("key_external_analysis_quote", {})
        keq_html = ""
        if isinstance(keq, dict) and keq.get("quote"):
            keq_html = f'<blockquote>"{e(keq["quote"])}" <span class="source-link">— {e(keq.get("source",""))}</span></blockquote>'

        sources = meta.get("based_on", [])
        sources_html = ""
        if sources:
            src_items = " · ".join(f"<span>{e(s)}</span>" for s in sources)
            sources_html = f'<div class="source-link" style="margin-top:var(--space-md)">Based on: {src_items}</div>'

        sections += f"""
<div class="card" id="{html_lib.escape(leader_id)}">
  <div class="leader-title">{title}</div>
  <h2>{name}</h2>
  <div style="font-family:var(--mono);font-size:.65rem;color:var(--muted);margin-bottom:var(--space-md)">
    In office since {since} &nbsp;·&nbsp; <code style="color:var(--accent-dim)">{html_lib.escape(leader_id)}</code>
  </div>
  {dim_html}
  {principles_html}
  {keq_html}
  {sources_html}
</div>"""

    body = f"""<div class="container">
  <div class="page-heading">Leaders</div>
  <h1>Decision-maker profiles</h1>
  {sections}
</div>"""
    return _page("Leaders", "leaders", body)


# ── cases page ────────────────────────────────────────────────────────────────

def build_cases(cases: list[dict]) -> str:
    if not cases:
        body = '<div class="container"><div class="empty-state"><p>No historical cases loaded.</p><code>data/historical/historical_cases.json</code></div></div>'
        return _page("Cases", "cases", body)

    cards = ""
    for case in cases:
        case_id = case.get("case_id", "")
        country = e(case.get("country", ""))
        period = e(case.get("period", ""))
        label = e(case.get("label", ""))
        category = e(case.get("category", ""))
        context = e(case.get("context", ""))
        trigger = e(case.get("shock_or_trigger", ""))
        lessons = e(case.get("lessons", ""))

        outcomes = case.get("outcomes", {})
        outcome_rows = "".join(
            f"<tr><td style='font-family:var(--mono);font-size:.65rem;color:var(--muted);padding:.25rem .5rem .25rem 0'>{e(k.replace('_',' '))}</td>"
            f"<td style='font-size:.8rem;padding:.25rem 0'>{e(v)}</td></tr>"
            for k, v in outcomes.items()
        )
        outcomes_html = f"<table style='width:100%;border-collapse:collapse;margin-bottom:var(--space-md)'>{outcome_rows}</table>" if outcome_rows else ""

        mechanisms = case.get("causal_mechanisms", [])
        mech_html = ""
        if mechanisms:
            items = "".join(f"<li style='margin-bottom:.375rem'>{e(m)}</li>" for m in mechanisms)
            mech_html = f"<h3>Causal mechanisms</h3><ul style='padding-left:1.25rem;margin-bottom:var(--space-md)'>{items}</ul>"

        sources = case.get("sources", [])
        src_html = ""
        if sources:
            src_items = " · ".join(f"<span>{e(s)}</span>" for s in sources)
            src_html = f'<div class="source-link">{src_items}</div>'

        sp = case.get("structural_profile", {})
        sp_html = ""
        if sp:
            sp_rows = " ".join(
                f'<span class="badge badge-secondary">{e(k.replace("_"," "))}: {e(v)}</span>'
                for k, v in sp.items()
            )
            sp_html = f'<div style="margin-bottom:var(--space-md)">{sp_rows}</div>'

        cards += f"""
<div class="card" id="{html_lib.escape(case_id)}">
  <div class="case-header">
    <div>
      <div class="case-id">{html_lib.escape(case_id)}</div>
      <h2>{label}</h2>
      <div class="case-period">{country} · {period} · <span class="badge badge-secondary">{category}</span></div>
    </div>
  </div>
  {sp_html}
  <h3>Context</h3>
  <p style="font-size:.875rem;margin-bottom:var(--space-md)">{context}</p>
  <h3>Trigger</h3>
  <p style="font-size:.875rem;margin-bottom:var(--space-md)">{trigger}</p>
  {outcomes_html}
  {mech_html}
  <h3>Lesson for Cambodia</h3>
  <p style="font-size:.875rem;margin-bottom:var(--space-md)">{lessons}</p>
  {src_html}
</div>"""

    body = f"""<div class="container">
  <div class="page-heading">Historical Cases</div>
  <h1>Structural analogues</h1>
  {cards}
</div>"""
    return _page("Cases", "cases", body)


# ── twins page ────────────────────────────────────────────────────────────────

def build_twins(twins: list[dict]) -> str:
    if not twins:
        body = """<div class="container">
  <div class="page-heading">Twin Matches</div>
  <h1>Structural twins</h1>
  <div class="empty-state">
    <p>No twin matches yet.</p>
    <p style="margin-top:.75rem"><code>python extractor/twin_matcher.py "signal text" --leader hun_manet</code></p>
  </div>
</div>"""
        return _page("Twins", "twins", body)

    cards = ""
    for t in twins:
        signal = e(t.get("signal", ""))
        leader_id = e(t.get("leader_id", ""))
        date = e(t.get("analysis_date", ""))
        matches = t.get("matches", [])

        match_html = ""
        for m in matches:
            case_id = e(m.get("case_id", ""))
            country = e(m.get("country", ""))
            score = m.get("similarity_score", 0)
            rationale = e(m.get("similarity_rationale", ""))
            outcome = e(m.get("outcome_summary", ""))
            lesson = e(m.get("cambodia_lesson", ""))
            risk = m.get("risk_flag", "MEDIUM")
            risk_class = {"HIGH": "badge-high", "MEDIUM": "badge-medium", "LOW": "badge-low"}.get(risk, "badge-secondary")

            match_html += f"""
<div style="border:1px solid var(--border);border-radius:var(--radius);padding:var(--space-md);margin-bottom:var(--space-sm)">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--space-sm)">
    <div>
      <div class="case-id">{case_id}</div>
      <div style="font-size:.875rem">{country}</div>
    </div>
    <div style="text-align:right">
      <div class="score">{score:.0%}</div>
      <div><span class="badge {risk_class}">{html_lib.escape(risk)}</span></div>
    </div>
  </div>
  <h3>Why structurally analogous</h3>
  <p style="font-size:.875rem;margin-bottom:var(--space-sm)">{rationale}</p>
  <h3>Historical outcome</h3>
  <p style="font-size:.875rem;margin-bottom:var(--space-sm)">{outcome}</p>
  <h3>Cambodia lesson</h3>
  <p style="font-size:.875rem">{lesson}</p>
</div>"""

        cards += f"""
<div class="card">
  <div class="page-heading">Signal · {leader_id} · {date}</div>
  <blockquote style="margin-bottom:var(--space-md)">{signal}</blockquote>
  {match_html}
</div>"""

    body = f"""<div class="container">
  <div class="page-heading">Twin Matches</div>
  <h1>Structural twins</h1>
  {cards}
</div>"""
    return _page("Twins", "twins", body)


# ── conflicts page ────────────────────────────────────────────────────────────

def build_conflicts(conflicts: list[dict]) -> str:
    total = sum(len(c.get("conflicts", [])) for c in conflicts)

    if total == 0:
        body = """<div class="container">
  <div class="page-heading">Conflicts</div>
  <h1>Detected contradictions</h1>
  <div class="empty-state">
    <p>No conflicts detected yet.</p>
    <p style="margin-top:.75rem"><code>python extractor/conflict_detector.py hun_manet hun_sen</code></p>
  </div>
</div>"""
        return _page("Conflicts", "conflicts", body)

    cards = ""
    for comparison in conflicts:
        leaders_compared = comparison.get("leaders_compared", [])
        date = e(comparison.get("analysis_date", ""))
        items = comparison.get("conflicts", [])

        if not items:
            continue

        for conflict in items:
            dim = e(conflict.get("dimension", ""))
            la = e(conflict.get("leader_a", ""))
            la_pos = e(conflict.get("leader_a_position", ""))
            la_quote = conflict.get("leader_a_quote", "")
            lb = e(conflict.get("leader_b", ""))
            lb_pos = e(conflict.get("leader_b_position", ""))
            lb_quote = conflict.get("leader_b_quote", "")
            explanation = e(conflict.get("conflict_explanation", ""))
            risk = conflict.get("implementation_risk", "MEDIUM")
            prediction = e(conflict.get("prediction", ""))
            risk_class = {"HIGH": "badge-high", "MEDIUM": "badge-medium", "LOW": "badge-low"}.get(risk, "badge-secondary")

            la_quote_html = f'<blockquote>"{e(la_quote)}"</blockquote>' if la_quote else ""
            lb_quote_html = f'<blockquote>"{e(lb_quote)}"</blockquote>' if lb_quote else ""

            cards += f"""
<div class="card">
  <div class="conflict-dim">{dim}</div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-md)">
    <div style="font-family:var(--mono);font-size:.7rem;color:var(--muted)">{" vs ".join(e(l) for l in leaders_compared)} · {date}</div>
    <span class="badge {risk_class}">{html_lib.escape(risk)} risk</span>
  </div>
  <div class="conflict-leaders">
    <div class="conflict-side">
      <h4>{la}</h4>
      <p style="font-size:.875rem">{la_pos}</p>
      {la_quote_html}
    </div>
    <div class="conflict-side">
      <h4>{lb}</h4>
      <p style="font-size:.875rem">{lb_pos}</p>
      {lb_quote_html}
    </div>
  </div>
  <div class="conflict-explanation">
    <h3>Why this is a genuine contradiction</h3>
    <p style="font-size:.875rem;margin-bottom:var(--space-md)">{explanation}</p>
    <div class="prediction-label">Predicted breaking point</div>
    <p style="font-size:.875rem">{prediction}</p>
  </div>
</div>"""

    body = f"""<div class="container">
  <div class="page-heading">Conflicts</div>
  <h1>Detected contradictions</h1>
  {cards}
</div>"""
    return _page("Conflicts", "conflicts", body)


# ── orchestration ─────────────────────────────────────────────────────────────

def build(clean: bool = False) -> list[Path]:
    if clean and DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    leaders = load_leaders()
    cases = load_cases()
    twins = load_twins()
    conflicts = load_conflicts()

    pages = {
        "index.html":     build_index(leaders, cases, twins, conflicts),
        "leaders.html":   build_leaders(leaders),
        "cases.html":     build_cases(cases),
        "twins.html":     build_twins(twins),
        "conflicts.html": build_conflicts(conflicts),
    }

    written = []
    for filename, content in pages.items():
        path = DOCS_DIR / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)

    return written


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Precedent static site.")
    parser.add_argument("--clean", action="store_true",
                        help="Delete site/docs/ before building")
    args = parser.parse_args()

    written = build(clean=args.clean)
    for path in written:
        size_kb = path.stat().st_size / 1024
        print(f"  {path.relative_to(PROJECT_ROOT)}  ({size_kb:.1f} KB)")

    print(f"\n{len(written)} files written to site/docs/")


if __name__ == "__main__":
    main()
