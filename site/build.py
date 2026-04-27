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
    python site/build.py --clean
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

SITE_TITLE = "PRECEDENT"
SITE_TAGLINE = "Political intelligence — Cambodia's decision-makers"

# Priority order for extracting a dimension's primary assessed position.
# Each dimension uses bespoke keys; try these in order until one has content.
_POSITION_KEYS = (
    "assessed_position",
    "core_thesis", "overall_assessment", "summary", "theory",
    "stated_horizon", "verdict", "explicit_assumptions", "method",
    "revealed_horizon", "description",
)


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
    d = DATA_DIR / "twins"
    if not d.exists():
        return []
    results = []
    for path in sorted(d.glob("*.json")):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


def load_conflicts() -> list[dict]:
    d = DATA_DIR / "conflicts"
    if not d.exists():
        return []
    results = []
    for path in sorted(d.glob("*.json")):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


# ── dimension helpers ─────────────────────────────────────────────────────────

def _is_populated(dim: object) -> bool:
    """True if the dimension dict has any non-null, non-empty value (ignoring _evidence)."""
    if not isinstance(dim, dict):
        return False
    return any(
        v is not None and v != "" and v != [] and v != {}
        for k, v in dim.items()
        if k != "_evidence"
    )


def _extract_position(dim: dict) -> str:
    """Return the best single-string summary of a dimension's assessed position."""
    for key in _POSITION_KEYS:
        val = dim.get(key)
        if val is None:
            continue
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            # e.g. stated_theory = {"summary": "...", ...}
            for subkey in ("summary", "description", "text"):
                sub = val.get(subkey)
                if isinstance(sub, str) and sub.strip():
                    return sub.strip()
            # fall back to first string value in the dict
            for v in val.values():
                if isinstance(v, str) and v.strip():
                    return v.strip()
    # Last resort: first non-evidence string value in the dict
    for k, v in dim.items():
        if k == "_evidence":
            continue
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _extract_confidence(dim: dict) -> float | None:
    """Return confidence from first evidence entry, or None."""
    evidence = dim.get("_evidence", [])
    if evidence and isinstance(evidence[0], dict):
        c = evidence[0].get("confidence")
        if c is not None:
            return float(c)
    return None


def _extract_source(dim: dict) -> tuple[str, str]:
    """Return (url, date) from first evidence entry."""
    evidence = dim.get("_evidence", [])
    if evidence and isinstance(evidence[0], dict):
        return evidence[0].get("url", ""), evidence[0].get("date", "")
    return "", ""


def _extract_quote(dim: dict) -> str:
    evidence = dim.get("_evidence", [])
    if evidence and isinstance(evidence[0], dict):
        return evidence[0].get("quote", "")
    return dim.get("key_quote", "") or ""


def _dim_completeness(profile: dict) -> tuple[int, int]:
    """Return (populated, total) dimension counts."""
    dims = profile.get("dimensions", {})
    populated = sum(1 for v in dims.values() if _is_populated(v))
    return populated, max(len(dims), 7)


# ── shared HTML ───────────────────────────────────────────────────────────────

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Bebas+Neue&"
    "family=IBM+Plex+Mono:wght@400;500&"
    'family=IBM+Plex+Sans:ital,wght@0,300;0,400;0,500;0,600;1,300&display=swap" rel="stylesheet">'
)

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #0a0a08;
  --surface:   #0f0f0d;
  --b-dim:     rgba(242,240,235,0.12);
  --b-mid:     rgba(242,240,235,0.28);
  --text:      #f2f0eb;
  --muted:     #8a8880;
  --accent:    #d4930a;
  --danger:    #c0392b;
  --warn:      #d4930a;
  --ok:        #1e6b3c;

  --bebas:  'Bebas Neue', 'Arial Narrow', sans-serif;
  --mono:   'IBM Plex Mono', monospace;
  --sans:   'IBM Plex Sans', system-ui, sans-serif;
}

html { font-size: 16px; scroll-behavior: smooth; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-weight: 300;
  line-height: 1.6;
  min-height: 100vh;
}

a { color: inherit; text-decoration: none; }
a:hover { color: var(--accent); }

/* ── masthead ── */
.masthead {
  border-bottom: 1px solid var(--b-mid);
  padding: 0 3rem;
}

.masthead-top {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding: 2rem 0 0.75rem;
  border-bottom: 1px solid var(--b-dim);
}

.masthead-wordmark {
  font-family: var(--bebas);
  font-size: clamp(3.5rem, 6vw, 4.5rem);
  line-height: 1;
  color: var(--text);
  letter-spacing: 0.04em;
}

.masthead-tagline {
  font-family: var(--mono);
  font-size: 0.65rem;
  color: var(--muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding-bottom: 0.5rem;
}

.masthead-nav {
  display: flex;
  gap: 0;
  padding: 0.5rem 0;
}

.masthead-nav a {
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  padding: 0.35rem 1rem;
  border-right: 1px solid var(--b-dim);
  transition: color 0.1s;
}

.masthead-nav a:first-child { padding-left: 0; }
.masthead-nav a:last-child { border-right: none; }
.masthead-nav a:hover,
.masthead-nav a.active { color: var(--text); }
.masthead-nav a.active {
  color: var(--accent);
  border-bottom: 1px solid var(--accent);
  margin-bottom: -1px;
}

/* ── layout ── */
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 3rem;
}

/* ── section label ── */
.section-label {
  font-family: var(--mono);
  font-size: 0.6rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.5rem;
}

.section-marker {
  color: var(--accent);
  margin-right: 0.4rem;
}

/* ── display heading ── */
h1 {
  font-family: var(--bebas);
  font-size: clamp(2.5rem, 4vw, 3.5rem);
  font-weight: 400;
  letter-spacing: 0.05em;
  line-height: 1;
  margin-bottom: 2rem;
}

h2 {
  font-family: var(--bebas);
  font-size: 1.5rem;
  letter-spacing: 0.04em;
  font-weight: 400;
  line-height: 1;
}

h3 {
  font-family: var(--mono);
  font-size: 0.65rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.5rem;
}

/* ── stat block ── */
.stat-row {
  display: flex;
  gap: 0;
  border: 1px solid var(--b-mid);
  margin-bottom: 3rem;
}

.stat-cell {
  flex: 1;
  padding: 1.25rem 1.75rem;
  border-right: 1px solid var(--b-dim);
}

.stat-cell:last-child { border-right: none; }

.stat-value {
  font-family: var(--bebas);
  font-size: 2.75rem;
  color: var(--accent);
  line-height: 1;
  margin-bottom: 0.25rem;
}

.stat-label {
  font-family: var(--mono);
  font-size: 0.6rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}

/* ── leader row (accordion) ── */
.leader-row {
  border-left: 3px solid var(--accent);
  border-bottom: 1px solid var(--b-dim);
  margin-bottom: 0;
}

.leader-row:last-child { border-bottom: 1px solid var(--b-mid); }

.leader-row-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.75rem 1.25rem 1.5rem;
  cursor: pointer;
  user-select: none;
  transition: background 0.1s;
}

.leader-row-header:hover { background: rgba(212,147,10,0.04); }

.leader-row-meta {
  display: flex;
  align-items: baseline;
  gap: 1.5rem;
}

.leader-name {
  font-family: var(--bebas);
  font-size: 1.75rem;
  letter-spacing: 0.04em;
  color: var(--text);
  line-height: 1;
}

.leader-title-tag {
  font-family: var(--mono);
  font-size: 0.65rem;
  color: var(--muted);
  letter-spacing: 0.06em;
}

.leader-row-right {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.completeness-display {
  text-align: right;
}

.completeness-frac {
  font-family: var(--bebas);
  font-size: 1.25rem;
  color: var(--accent);
  line-height: 1;
}

.completeness-sub {
  font-family: var(--mono);
  font-size: 0.55rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.expand-arrow {
  font-size: 0.875rem;
  color: var(--muted);
  width: 1rem;
  text-align: center;
  transition: transform 0.15s;
}

/* ── dimension table ── */
.leader-detail {
  display: none;
  border-top: 1px solid var(--b-dim);
  padding: 0 1.75rem 1.5rem 1.5rem;
}

.dim-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1.5rem;
}

.dim-table th {
  font-family: var(--mono);
  font-size: 0.58rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
  text-align: left;
  padding: 0.75rem 0.75rem 0.75rem 0;
  border-bottom: 1px solid var(--b-mid);
}

.dim-table td {
  font-size: 0.8125rem;
  padding: 0.875rem 0.75rem 0.875rem 0;
  border-bottom: 1px solid var(--b-dim);
  vertical-align: top;
}

.dim-table tr:last-child td { border-bottom: none; }

.dim-name-cell {
  font-family: var(--mono);
  font-size: 0.65rem;
  letter-spacing: 0.06em;
  color: var(--accent);
  white-space: nowrap;
  width: 22%;
}

.dim-position-cell { width: 46%; }
.dim-position-cell.empty { color: var(--muted); font-style: italic; }

.conf-cell { width: 12%; white-space: nowrap; }
.conf-bar-wrap {
  height: 2px;
  background: var(--b-mid);
  margin-top: 0.4rem;
  width: 100%;
}
.conf-bar-fill { height: 2px; background: var(--accent); }
.conf-val {
  font-family: var(--mono);
  font-size: 0.6rem;
  color: var(--muted);
}

.source-cell {
  width: 20%;
  font-family: var(--mono);
  font-size: 0.6rem;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.source-cell a { color: var(--muted); }
.source-cell a:hover { color: var(--accent); }

/* ── blockquote ── */
blockquote {
  border-left: 2px solid var(--accent);
  padding: 0.75rem 1rem;
  margin: 1rem 0;
  color: var(--muted);
  font-size: 0.875rem;
  font-style: italic;
}

blockquote .bq-source {
  display: block;
  font-style: normal;
  font-family: var(--mono);
  font-size: 0.6rem;
  color: var(--muted);
  margin-top: 0.4rem;
}

blockquote .bq-source a { color: var(--muted); }
blockquote .bq-source a:hover { color: var(--accent); }

/* ── synthesis block ── */
.synthesis-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
  border: 1px solid var(--b-dim);
  margin-top: 1rem;
}

.synth-cell {
  padding: 1rem 1.25rem;
  border-right: 1px solid var(--b-dim);
  border-bottom: 1px solid var(--b-dim);
}

.synth-cell:nth-child(2n) { border-right: none; }
.synth-cell:nth-last-child(-n+2) { border-bottom: none; }

.synth-dim {
  font-family: var(--mono);
  font-size: 0.58rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 0.35rem;
}

.synth-insight { font-size: 0.8rem; color: var(--muted); }

/* ── badges / pills ── */
.pill {
  display: inline-block;
  font-family: var(--mono);
  font-size: 0.58rem;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 0.2em 0.55em;
  border-radius: 2px;
  vertical-align: middle;
}

.pill-high    { background: rgba(192,57,43,0.18);   color: #e74c3c; border: 1px solid rgba(192,57,43,0.4); }
.pill-medium  { background: rgba(212,147,10,0.15);  color: #d4930a; border: 1px solid rgba(212,147,10,0.4); }
.pill-low     { background: rgba(30,107,60,0.18);   color: #2ecc71; border: 1px solid rgba(30,107,60,0.4); }
.pill-primary { background: rgba(212,147,10,0.12);  color: var(--accent); border: 1px solid rgba(212,147,10,0.3); }
.pill-muted   { background: rgba(242,240,235,0.06); color: var(--muted);  border: 1px solid var(--b-dim); }

/* ── case blocks ── */
.filter-bar {
  display: flex;
  gap: 0;
  margin-bottom: 2rem;
  border: 1px solid var(--b-mid);
  width: fit-content;
}

.filter-btn {
  font-family: var(--mono);
  font-size: 0.65rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  background: none;
  border: none;
  border-right: 1px solid var(--b-dim);
  padding: 0.5rem 1rem;
  cursor: pointer;
  transition: color 0.1s, background 0.1s;
}

.filter-btn:last-child { border-right: none; }
.filter-btn:hover { color: var(--text); background: rgba(242,240,235,0.04); }
.filter-btn.active { color: var(--accent); background: rgba(212,147,10,0.08); }

.case-block {
  border: 1px solid var(--b-dim);
  border-left: 3px solid var(--b-mid);
  margin-bottom: 1rem;
}

.case-head {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 1.5rem;
  align-items: start;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--b-dim);
  background: var(--surface);
}

.case-id-label {
  font-family: var(--mono);
  font-size: 0.6rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 0.3rem;
}

.case-country {
  font-family: var(--bebas);
  font-size: 1.375rem;
  letter-spacing: 0.05em;
  line-height: 1;
}

.case-period-tag {
  font-family: var(--mono);
  font-size: 0.62rem;
  color: var(--muted);
  margin-top: 0.25rem;
}

.case-body {
  padding: 1.25rem 1.5rem;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

.case-section h3 { margin-bottom: 0.4rem; }
.case-section p { font-size: 0.8125rem; color: var(--muted); }

.case-mechanisms {
  padding: 0 1.5rem 1.25rem;
}

.case-mechanisms ul {
  list-style: none;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.35rem;
}

.case-mechanisms ul li {
  font-size: 0.75rem;
  color: var(--muted);
  padding-left: 1rem;
  position: relative;
}

.case-mechanisms ul li::before {
  content: "→";
  position: absolute;
  left: 0;
  color: var(--accent);
  font-family: var(--mono);
}

.case-lesson {
  border-top: 1px solid var(--b-dim);
  padding: 1rem 1.5rem;
  background: rgba(212,147,10,0.04);
  font-size: 0.8125rem;
}

.case-lesson strong {
  font-family: var(--mono);
  font-size: 0.58rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  display: block;
  margin-bottom: 0.35rem;
}

/* ── twin match ── */
.twin-block {
  border: 1px solid var(--b-dim);
  margin-bottom: 1.5rem;
}

.twin-signal {
  background: var(--surface);
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--b-dim);
}

.twin-signal-label {
  font-family: var(--mono);
  font-size: 0.58rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.4rem;
}

.twin-signal-text {
  font-size: 0.9rem;
  font-style: italic;
  color: var(--muted);
}

.twin-matches { display: grid; grid-template-columns: 1fr 1fr; }

.twin-match-card {
  padding: 1.25rem 1.5rem;
  border-right: 1px solid var(--b-dim);
}

.twin-match-card:last-child { border-right: none; }

.twin-score {
  font-family: var(--bebas);
  font-size: 3rem;
  color: var(--accent);
  line-height: 1;
}

.twin-score-label {
  font-family: var(--mono);
  font-size: 0.58rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.75rem;
}

.twin-match-country {
  font-family: var(--bebas);
  font-size: 1.25rem;
  letter-spacing: 0.04em;
  margin-bottom: 0.25rem;
}

.twin-section { margin-top: 0.75rem; }
.twin-section h3 { margin-bottom: 0.25rem; }
.twin-section p { font-size: 0.8rem; color: var(--muted); }

/* ── conflict block ── */
.conflict-block {
  border: 1px solid var(--b-dim);
  border-left: 3px solid var(--danger);
  margin-bottom: 1.25rem;
}

.conflict-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.875rem 1.25rem;
  background: var(--surface);
  border-bottom: 1px solid var(--b-dim);
}

.conflict-dim-label {
  font-family: var(--mono);
  font-size: 0.65rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
}

.conflict-leaders-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid var(--b-dim);
}

.conflict-side {
  padding: 1.25rem 1.5rem;
  border-right: 1px solid var(--b-dim);
}

.conflict-side:last-child { border-right: none; }

.conflict-leader-name {
  font-family: var(--bebas);
  font-size: 1.25rem;
  letter-spacing: 0.04em;
  margin-bottom: 0.5rem;
}

.conflict-pos { font-size: 0.8125rem; margin-bottom: 0.5rem; }

.conflict-footer {
  padding: 1rem 1.5rem;
}

.conflict-footer h3 { margin-bottom: 0.4rem; }
.conflict-footer p { font-size: 0.8125rem; color: var(--muted); }

.prediction-block {
  border-top: 1px solid var(--b-dim);
  padding-top: 0.75rem;
  margin-top: 0.75rem;
}

/* ── index quick-links ── */
.index-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border: 1px solid var(--b-mid);
  margin-top: 3rem;
}

.index-tile {
  padding: 1.5rem;
  border-right: 1px solid var(--b-dim);
  transition: background 0.1s;
}

.index-tile:last-child { border-right: none; }
.index-tile:hover { background: rgba(242,240,235,0.02); }

.index-tile-label {
  font-family: var(--mono);
  font-size: 0.58rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 0.6rem;
}

.index-tile-body {
  font-size: 0.8rem;
  color: var(--muted);
  line-height: 1.5;
}

.index-tile a.tile-link {
  display: inline-block;
  font-family: var(--mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  color: var(--muted);
  margin-top: 0.75rem;
  text-transform: uppercase;
}

.index-tile a.tile-link:hover { color: var(--accent); }

/* ── empty state ── */
.empty-state {
  padding: 4rem 2rem;
  text-align: center;
  border: 1px dashed var(--b-mid);
  color: var(--muted);
}

.empty-state code {
  display: block;
  font-family: var(--mono);
  font-size: 0.75rem;
  color: rgba(212,147,10,0.6);
  margin-top: 1rem;
}

/* ── divider ── */
.rule { border: none; border-top: 1px solid var(--b-dim); margin: 2rem 0; }

/* ── mobile ── */
@media (max-width: 700px) {
  .masthead { padding: 0 1.25rem; }
  .container { padding: 2rem 1.25rem; }
  .masthead-top { flex-direction: column; gap: 0.5rem; }
  .masthead-nav { flex-wrap: wrap; }
  .stat-row { flex-direction: column; }
  .stat-cell { border-right: none; border-bottom: 1px solid var(--b-dim); }
  .case-body { grid-template-columns: 1fr; }
  .case-mechanisms ul { grid-template-columns: 1fr; }
  .twin-matches { grid-template-columns: 1fr; }
  .conflict-leaders-grid { grid-template-columns: 1fr; }
  .index-grid { grid-template-columns: 1fr; }
  .synthesis-grid { grid-template-columns: 1fr; }
  .leader-row-meta { flex-direction: column; gap: 0.25rem; }
  .dim-table { font-size: 0.75rem; }
}
"""

JS_ACCORDION = """
<script>
function toggleLeader(id) {
  var el = document.getElementById('dim-' + id);
  var arrow = document.getElementById('arrow-' + id);
  if (!el) return;
  if (el.style.display === 'block') {
    el.style.display = 'none';
    arrow.textContent = '▸';
  } else {
    el.style.display = 'block';
    arrow.textContent = '▾';
  }
}
</script>
"""

JS_FILTER = """
<script>
function filterCases(cat, btn) {
  document.querySelectorAll('.case-block').forEach(function(el) {
    el.style.display = (cat === 'ALL' || el.dataset.category === cat) ? '' : 'none';
  });
  document.querySelectorAll('.filter-btn').forEach(function(b) {
    b.classList.toggle('active', b === btn);
  });
}
</script>
"""

JS_SEARCH = """
<script>
function initSearch() {
  var input = document.getElementById('site-search');
  if (!input) return;
  var targets = document.querySelectorAll('[data-searchable]');
  input.addEventListener('input', function() {
    var q = this.value.trim().toLowerCase();
    if (!q) { targets.forEach(function(el){ el.style.display = ''; }); return; }
    targets.forEach(function(el) {
      var text = el.textContent.toLowerCase();
      el.style.display = text.includes(q) ? '' : 'none';
    });
  });
}
document.addEventListener('DOMContentLoaded', initSearch);
</script>
"""


_BUILD_DATE = "2026-04-27"

_META_DESCRIPTIONS = {
    "index": "Precedent maps how Cambodia&#8217;s 11 key decision-makers reason — extracting doctrine from primary sources and matching decisions against historical cases. Cambodia faces critical inflection points by 2029.",
    "leaders": "Decision-maker profiles for Cambodia&#8217;s 11 key leaders — 7-dimension doctrine maps with confidence ratings, primary sources, and performance evaluations.",
    "cases": "9 historical structural analogues matched to Cambodia&#8217;s 2029 risk scenarios: trade preference loss, fiscal collapse, regulatory shock, and more.",
    "twins": "Historical twin matches for Cambodia policy signals — structural similarity scoring across 5 dimensions.",
    "conflicts": "Detected doctrine contradictions between Cambodia&#8217;s senior officials — logical conflicts where simultaneous implementation would produce incoherent policy.",
    "solutions": "Risk mitigation options for Cambodia&#8217;s three major 2029 risk scenarios, matched to historical response playbooks.",
    "methodology": "How Precedent works: 7-dimension framework, source methodology, confidence scoring, and twin-matching algorithm.",
}


def _page(title: str, active: str, body: str, extra_js: str = "") -> str:
    nav_links = [
        ("index.html",       "Index",       "index"),
        ("leaders.html",     "Leaders",     "leaders"),
        ("cases.html",       "Cases",       "cases"),
        ("twins.html",       "Twins",       "twins"),
        ("conflicts.html",   "Conflicts",   "conflicts"),
        ("solutions.html",   "Solutions",   "solutions"),
        ("methodology.html", "Methodology", "methodology"),
    ]
    nav = "".join(
        f'<a href="{href}" class="{"active" if k == active else ""}">{label}</a>'
        for href, label, k in nav_links
    )
    meta_desc = _META_DESCRIPTIONS.get(active, f"{title} — {SITE_TITLE}")
    full_title = (
        "Cambodia Political Intelligence — Precedent" if active == "index"
        else f"{title} — Cambodia Precedent"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_lib.escape(full_title)}</title>
<meta name="description" content="{meta_desc}">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="masthead">
  <div class="masthead-inner">
    <div class="masthead-brand">
      <a href="index.html" class="masthead-wordmark">{SITE_TITLE}</a>
      <span class="masthead-version">v0.2</span>
    </div>
    <nav class="masthead-nav">{nav}</nav>
    <div class="masthead-meta">Political Intelligence · Cambodia's Decision-Makers</div>
  </div>
</header>
<div class="date-strip">
  <span>{_BUILD_DATE} · Intelligence Update</span>
  <span>Coverage: Cambodia's senior leadership</span>
</div>
{body}
{extra_js}
<footer class="site-footer">
  <span>{SITE_TITLE} · Cambodia Political Intelligence · v0.2</span>
  <span>Data updated: {_BUILD_DATE}</span>
</footer>
</body>
</html>"""


def e(v: object, fallback: str = "") -> str:
    s = str(v) if v is not None else ""
    return html_lib.escape(s.strip()) if s.strip() else html_lib.escape(fallback)


def pill(label: str, risk: str) -> str:
    cls = {"HIGH": "pill-high", "MEDIUM": "pill-medium", "LOW": "pill-low"}.get(
        risk.upper(), "pill-muted"
    )
    icon = {"HIGH": "⚠ ", "MEDIUM": "◈ ", "LOW": "◈ "}.get(risk.upper(), "")
    return f'<span class="pill {cls}">{icon}{html_lib.escape(label)}</span>'


# ── index ─────────────────────────────────────────────────────────────────────

def build_index(leaders, cases, twins, conflicts) -> str:
    total_conflicts = sum(len(c.get("conflicts", [])) for c in conflicts)
    total_twins = sum(len(t.get("matches", [])) for t in twins)
    total_dims = sum(_dim_completeness(p)[0] for p in leaders)

    def stat_cell(val, label):
        if val == 0:
            return ""
        return f'<div class="stat-cell"><div class="stat-value">{val}</div><div class="stat-label">{label}</div></div>'
    stats = f"""<div class="stat-row">
  {stat_cell(len(leaders), "Leaders profiled")}
  {stat_cell(total_dims, "Dimensions populated")}
  {stat_cell(len(cases), "Historical cases")}
  {stat_cell(total_twins, "Twin analyses")}
  {stat_cell(total_conflicts, "Conflicts detected")}
</div>"""

    leader_rows = ""
    for p in leaders:
        name = e(p.get("full_name", p.get("id", "")))
        title = e(p.get("title", ""))
        pop, tot = _dim_completeness(p)
        leader_rows += f"""<div class="leader-row" style="margin-bottom:0.5rem">
  <div class="leader-row-header" style="cursor:default">
    <div class="leader-row-meta">
      <span class="leader-name">{name}</span>
      <span class="leader-title-tag">{title}</span>
    </div>
    <div class="leader-row-right">
      <div class="completeness-display">
        <div class="completeness-frac">{pop}/{tot}</div>
        <div class="completeness-sub">dimensions</div>
      </div>
    </div>
  </div>
</div>"""

    tiles = f"""<div class="index-grid">
  <a href="leaders.html" class="index-tile" style="display:block">
    <div class="index-tile-label">◈ Leaders</div>
    <div class="index-tile-body">{len(leaders)} decision-maker profiles across {total_dims} documented dimensions.</div>
    <span class="tile-link">View profiles →</span>
  </a>
  <a href="cases.html" class="index-tile" style="display:block">
    <div class="index-tile-label">◈ Historical Cases</div>
    <div class="index-tile-body">{len(cases)} structural analogues with causal mechanisms and Cambodia-specific lessons.</div>
    <span class="tile-link">View cases →</span>
  </a>
  <a href="twins.html" class="index-tile" style="display:block">
    <div class="index-tile-label">◈ Twin Matches</div>
    <div class="index-tile-body">{total_twins} policy signal matches. Run <code style="font-size:.65rem">twin_matcher.py</code> to populate.</div>
    <span class="tile-link">View twins →</span>
  </a>
</div>"""

    # ABOUT SECTION
    about_html = """<div style="margin-bottom:2.5rem;padding:1.5rem 0;border-bottom:1px solid var(--b-dim)">
  <p style="font-size:1.05rem;line-height:1.75;max-width:68ch;color:var(--text)">
    Precedent maps how Cambodia&#8217;s 11 key decision-makers actually reason &#8212;
    extracting doctrine from primary sources and matching their choices against
    historical cases where similar logic was tried and failed.
    By 2029, Cambodia faces EBA preference loss, Chinese FDI concentration risk,
    and a garment sector labour squeeze. This site gives you the decision-maker
    profiles, the historical precedents, and the predicted breaking points.
  </p>
</div>"""

    # KEY FINDINGS
    best_twin = ""
    if twins:
        for t in twins:
            for m in t.get("matches", []):
                score = m.get("similarity_score", 0)
                if score >= 0.7:
                    pct = int(score * 100)
                    risk = m.get("risk_flag", "MEDIUM")
                    best_twin = f"{pct}% structural match with {m.get('country','?')} ({m.get('case_id','')}) — {risk} RISK"
                    break
            if best_twin:
                break

    twin_finding = ""
    if best_twin:
        twin_finding = f'<div style="margin-bottom:.75rem"><span class="pill pill-high" style="margin-right:.5rem">TWIN</span>{html_lib.escape(best_twin)}</div>'

    conflict_finding = f'<div style="margin-bottom:.75rem"><span class="pill pill-medium" style="margin-right:.5rem">CONFLICTS</span>{total_conflicts} doctrine contradictions detected across {len(conflicts)} leader pairs</div>' if total_conflicts else ""

    trajectory = (
        "Cambodia faces a structural squeeze by 2029: EBA preference erosion threatens "
        "the garment sector, Chinese FDI dependency creates debt-trap exposure, and the "
        "Funan Techo Canal signals infrastructure-led growth over trade diversification. "
        "Historical twins suggest HIGH risk of export concentration collapse without "
        "accelerated diversification. The current leadership cohort shows coherent "
        "short-term FDI doctrine but LOW long-term institution-building commitment."
    )

    findings_html = f"""<div style="margin:2.5rem 0;padding:1.5rem;border:1px solid var(--b-dim);background:var(--surface)">
  <div class="section-label" style="margin-bottom:1rem"><span class="section-marker">◈</span>Key Findings</div>
  {twin_finding}
  {conflict_finding}
  <div style="margin-bottom:.75rem"><span class="pill pill-muted" style="margin-right:.5rem">TRAJECTORY</span></div>
  <p style="font-size:.8125rem;line-height:1.7;color:var(--muted)">{html_lib.escape(trajectory)}</p>
  <div style="font-family:var(--mono);font-size:.58rem;color:var(--muted);margin-top:.75rem">Last updated: 2026-04-25 · Data: {len(leaders)} leaders, {len(cases)} cases, {total_twins} twin analyses</div>
</div>"""

    body = f"""<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Intelligence overview</div>
  <h1>Cambodia's Operating Doctrine</h1>
  {about_html}
  {stats}
  {findings_html}
  <div class="section-label" style="margin-bottom:1rem"><span class="section-marker">◈</span>Leaders</div>
  {leader_rows}
  {tiles}
</div>"""
    return _page("Overview", "index", body)


# ── leaders ───────────────────────────────────────────────────────────────────

def _dim_table_row(key: str, dim: object) -> str:
    label = key.replace("_", " ").upper()
    if not isinstance(dim, dict) or not _is_populated(dim):
        return (
            f"<tr>"
            f'<td class="dim-name-cell">{html_lib.escape(label)}</td>'
            f'<td class="dim-position-cell empty">No data yet</td>'
            f'<td class="conf-cell"><span class="conf-val">—</span></td>'
            f'<td class="source-cell">—</td>'
            f"</tr>"
        )
    dim_d = dim
    position = _extract_position(dim_d)
    conf = _extract_confidence(dim_d)
    url, date_str = _extract_source(dim_d)
    quote = _extract_quote(dim_d)

    # Also pull primary_quote and subfields from new-format dims
    primary_q = dim_d.get("primary_quote", "")
    primary_src = dim_d.get("primary_source", "")
    subfields = dim_d.get("subfields", [])

    # Use primary_quote if no evidence quote
    if not quote and primary_q:
        quote = primary_q if isinstance(primary_q, str) else ""

    conf_html = ""
    if conf is not None:
        pct = int(conf * 100)
        conf_html = (
            f'<span class="conf-val">{pct}%</span>'
            f'<div class="conf-bar-wrap"><div class="conf-bar-fill" style="width:{pct}%"></div></div>'
        )
    else:
        conf_html = '<span class="conf-val">—</span>'

    source_html = "—"
    if url:
        source_html = f'<a href="{html_lib.escape(url)}" target="_blank" rel="noopener">↗ {e(date_str)}</a>'
    elif primary_src:
        source_html = e(primary_src)

    position_html = e(position, "—")
    if quote:
        src_inner = ""
        if url:
            src_inner = f'<span class="bq-source"><a href="{html_lib.escape(url)}" target="_blank" rel="noopener">↗ {e(date_str)}</a></span>'
        elif primary_src:
            src_inner = f'<span class="bq-source">{e(primary_src)}</span>'
        position_html += f'<blockquote style="margin:.5rem 0 0;font-size:.75rem">"{e(quote)}"{src_inner}</blockquote>'

    if subfields and isinstance(subfields, list):
        sf_items = "".join(f"<li>{e(sf)}</li>" for sf in subfields if sf)
        position_html += f'<ul style="margin:.5rem 0 0;padding-left:1.25rem;font-size:.75rem;color:var(--muted)">{sf_items}</ul>'

    return (
        f"<tr>"
        f'<td class="dim-name-cell">{html_lib.escape(label)}</td>'
        f'<td class="dim-position-cell">{position_html}</td>'
        f'<td class="conf-cell">{conf_html}</td>'
        f'<td class="source-cell">{source_html}</td>'
        f"</tr>"
    )


def _consistency_ratings_html(ratings: list) -> str:
    if not ratings:
        return ""
    rows = "".join(
        f"<tr>"
        f'<td style="font-family:var(--mono);font-size:.6rem;color:var(--muted);text-transform:uppercase;padding:.35rem .75rem .35rem 0;white-space:nowrap">{e(r.get("dimension",""))}</td>'
        f'<td style="padding:.35rem .75rem .35rem 0">{pill(r.get("verdict",""), r.get("verdict","MEDIUM"))}</td>'
        f'<td style="font-size:.78rem;color:var(--muted)">{e(r.get("evidence",""))}</td>'
        f"</tr>"
        for r in ratings if isinstance(r, dict)
    )
    return (
        f'<div style="margin:1.25rem 0 0"><h3 style="margin-bottom:.6rem">Consistency Ratings</h3>'
        f'<table style="width:100%;border-collapse:collapse"><tbody>{rows}</tbody></table></div>'
    )


def _perf_eval_html(profile: dict) -> str:
    """Performance evaluation table — Hun Manet only."""
    dims = profile.get("dimensions", {})
    cs = dims.get("consistency_score") or {}
    ratings = cs.get("ratings", [])
    if not ratings:
        return ""

    DIM_KEYS = (
        "growth_theory", "risk_tolerance", "time_horizon",
        "dependency_assumptions", "institution_vs_relationship",
        "global_positioning_logic",
    )
    ratings_by_dim = {r.get("dimension", "").lower().replace(" ", "_"): r for r in ratings if isinstance(r, dict)}

    rows = ""
    for key in DIM_KEYS:
        label = key.replace("_", " ").title()
        dim = dims.get(key) or {}
        stated = _extract_position(dim) if dim else ""
        # Try to find matching rating
        rating = ratings_by_dim.get(key) or next(
            (r for r in ratings if isinstance(r, dict) and key.split("_")[0] in r.get("dimension","").lower()),
            {}
        )
        revealed = e(rating.get("evidence", "—"))
        verdict = rating.get("verdict", "MEDIUM")
        rows += (
            f"<tr>"
            f'<td style="font-family:var(--mono);font-size:.6rem;color:var(--muted);text-transform:uppercase;padding:.5rem .75rem .5rem 0;white-space:nowrap;vertical-align:top">{html_lib.escape(label)}</td>'
            f'<td style="font-size:.78rem;padding:.5rem .75rem .5rem 0;vertical-align:top">{e(stated[:200])}</td>'
            f'<td style="font-size:.78rem;padding:.5rem .75rem .5rem 0;vertical-align:top;color:var(--muted)">{revealed}</td>'
            f'<td style="vertical-align:top;padding:.5rem 0">{pill(verdict, verdict)}</td>'
            f"</tr>"
        )

    return f"""<div style="margin:2rem 0 0;padding:1.5rem;border:1px solid var(--b-dim);background:var(--surface)">
  <h3 style="margin-bottom:1rem;font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:var(--accent)">Performance Evaluation</h3>
  <table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="border-bottom:1px solid var(--b-dim)">
        <th style="font-family:var(--mono);font-size:.58rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);text-align:left;padding:.35rem .75rem .35rem 0">Dimension</th>
        <th style="font-family:var(--mono);font-size:.58rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);text-align:left;padding:.35rem .75rem .35rem 0">Stated Position</th>
        <th style="font-family:var(--mono);font-size:.58rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);text-align:left;padding:.35rem .75rem .35rem 0">Revealed Behavior</th>
        <th style="font-family:var(--mono);font-size:.58rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);text-align:left;padding:.35rem 0">Verdict</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def build_leaders(leaders: list[dict]) -> str:
    DIM_KEYS = (
        "growth_theory", "risk_tolerance", "time_horizon",
        "dependency_assumptions", "institution_vs_relationship",
        "global_positioning_logic", "consistency_score",
    )

    rows_html = ""
    for p in leaders:
        lid = p.get("id", "")
        lid_safe = html_lib.escape(lid)
        name = e(p.get("full_name", lid))
        title = e(p.get("title", ""))
        meta = p.get("leader", {})
        pop, tot = _dim_completeness(p)

        # Bio from purpose
        purpose = meta.get("purpose", "")
        bio_html = ""
        if purpose:
            bio_html = f'<div style="font-size:.8125rem;color:var(--muted);margin:.4rem 0 .75rem;max-width:72ch">{e(purpose[:300])}</div>'

        dims = p.get("dimensions", {})
        dim_rows = "".join(_dim_table_row(k, dims.get(k)) for k in DIM_KEYS)

        # Consistency ratings from consistency_score.ratings
        cs_dim = dims.get("consistency_score") or {}
        ratings = cs_dim.get("ratings", []) if isinstance(cs_dim, dict) else []
        cr_html = _consistency_ratings_html(ratings)

        # Performance evaluation (hun_manet only)
        perf_html = _perf_eval_html(p) if lid == "hun_manet" else ""

        synth = p.get("synthesis", {})
        principles = synth.get("guiding_principles", [])
        PLACEHOLDER_PREFIXES = ("Use ", "use ", "primary signal", "behavior as primary")
        real_principles = [
            pr for pr in principles
            if isinstance(pr, dict) and pr.get("insight","") and
            not any(pr.get("insight","").startswith(p) or p in pr.get("insight","") for p in PLACEHOLDER_PREFIXES)
        ]
        synth_html = ""
        if real_principles:
            cells = "".join(
                f'<div class="synth-cell">'
                f'<div class="synth-dim">{e(pr.get("dimension",""))}</div>'
                f'<div class="synth-insight">{e(pr.get("insight",""))}</div>'
                f'</div>'
                for pr in real_principles
            )
            synth_html = f'<h3 style="margin:1.25rem 0 0.75rem">Synthesis</h3><div class="synthesis-grid">{cells}</div>'

        keq = synth.get("key_external_analysis_quote", {})
        keq_html = ""
        if isinstance(keq, dict) and keq.get("quote"):
            src = e(keq.get("source", ""))
            keq_html = f'<blockquote>"{e(keq["quote"])}"<span class="bq-source">— {src}</span></blockquote>'

        sources = meta.get("based_on", [])
        sources_str = " · ".join(e(s) for s in sources) if sources else ""
        src_line = f'<div style="font-family:var(--mono);font-size:.6rem;color:var(--muted);margin-top:1rem">Based on: {sources_str}</div>' if sources_str else ""

        detail = f"""<div class="leader-detail" id="dim-{lid_safe}" style="display:none">
  <table class="dim-table">
    <thead>
      <tr>
        <th>Dimension</th>
        <th>Assessed position</th>
        <th>Confidence</th>
        <th>Source</th>
      </tr>
    </thead>
    <tbody>{dim_rows}</tbody>
  </table>
  {cr_html}
  {perf_html}
  {keq_html}
  {synth_html}
  {src_line}
</div>"""

        rows_html += f"""<div class="leader-row" id="{lid_safe}" data-searchable>
  <div class="leader-row-header" onclick="toggleLeader('{lid_safe}')">
    <div class="leader-row-meta">
      <span class="leader-name">{name}</span>
      <span class="leader-title-tag">{title}</span>
    </div>
    <div class="leader-row-right">
      <div class="completeness-display">
        <div class="completeness-frac">{pop}/{tot}</div>
        <div class="completeness-sub">dims populated</div>
      </div>
      <span class="expand-arrow" id="arrow-{lid_safe}">▸</span>
    </div>
  </div>
  {bio_html}
  {detail}
</div>"""

    body = f"""<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Decision-maker profiles</div>
  <h1>Leaders</h1>
  <div style="display:flex;align-items:center;gap:1rem;margin-bottom:2rem">
    <p style="font-size:.8rem;color:var(--muted)">
      {len(leaders)} decision-makers — click to expand.
    </p>
    <input id="site-search" type="search" placeholder="Search leaders…"
      style="margin-left:auto;background:var(--surface);border:1px solid var(--b-mid);color:var(--text);font-family:var(--mono);font-size:.7rem;padding:.4rem .75rem;border-radius:2px;min-width:200px">
  </div>
  {rows_html}
</div>"""
    return _page("Leaders", "leaders", body, JS_ACCORDION + JS_SEARCH)


# ── cases ─────────────────────────────────────────────────────────────────────

_CATEGORY_MAP = {
    "trade_liberalisation":         "TRADE",
    "export_zone_industrialisation": "TRADE",
    "export_concentration_trap":    "TRADE",
    "trade_agreement_preference_trap": "TRADE",
    "infrastructure_debt_trap":     "FISCAL",
    "fiscal_collapse":              "FISCAL",
    "regulatory_shock":             "REGULATORY",
}


def build_cases(cases: list[dict]) -> str:
    if not cases:
        body = '<div class="container"><div class="empty-state"><p>No historical cases loaded.</p></div></div>'
        return _page("Cases", "cases", body)

    cards = ""
    for case in cases:
        cid = case.get("case_id", "")
        country = e(case.get("country", ""))
        period = e(case.get("period", ""))
        label = e(case.get("label", ""))
        cat = case.get("category", "")
        cat_display = _CATEGORY_MAP.get(cat, "REGULATORY")
        # context: old=str, new=dict
        ctx_raw = case.get("context", "")
        if isinstance(ctx_raw, dict):
            context = e(ctx_raw.get("political_economy", "") or next(iter(ctx_raw.values()), ""))
        else:
            context = e(ctx_raw)

        # policy_response
        pr_raw = case.get("policy_response", "")
        if isinstance(pr_raw, dict):
            pr_text = pr_raw.get("growth_model_invoked", "") or next((v for v in pr_raw.values() if isinstance(v, str)), "")
        else:
            pr_text = str(pr_raw) if pr_raw else ""
        policy_html = (f'<div class="case-section"><h3>Policy response</h3><p>{e(pr_text)}</p></div>' if pr_text else "")

        # shock_or_trigger: old=str, new=dict with "event" key
        trig_raw = case.get("shock_or_trigger", "")
        if isinstance(trig_raw, dict):
            trigger = e(trig_raw.get("event", "") or next(iter(trig_raw.values()), ""))
        else:
            trigger = e(trig_raw)

        # lessons: old=str, new=dict with what_worked/what_failed/cambodia_2029_relevance
        les_raw = case.get("lessons", "")
        if isinstance(les_raw, dict):
            lessons = e(les_raw.get("what_worked", ""))
            lessons_failed = e(les_raw.get("what_failed", ""))
            cam_relevance = e(les_raw.get("cambodia_2029_relevance", ""))
        else:
            lessons = e(les_raw)
            lessons_failed = ""
            cam_relevance = ""

        outcomes = case.get("outcomes", {})
        outcome_rows = "".join(
            f"<tr>"
            f'<td style="font-family:var(--mono);font-size:.58rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;padding:.3rem .75rem .3rem 0;white-space:nowrap">{e(k.replace("_"," "))}</td>'
            f'<td style="font-size:.78rem;padding:.3rem 0">{e(v)}</td>'
            f"</tr>"
            for k, v in outcomes.items()
        )
        outcomes_html = (
            f'<table style="width:100%;border-collapse:collapse;border-top:1px solid var(--b-dim);padding:1rem 1.5rem">'
            f'<tbody style="display:block;padding:1rem 1.5rem">{outcome_rows}</tbody></table>'
            if outcome_rows else ""
        )

        mechanisms = case.get("causal_mechanisms", [])
        mech_items = "".join(f"<li>{e(m)}</li>" for m in mechanisms)
        mech_html = (
            f'<div class="case-mechanisms">'
            f'<h3 style="margin-bottom:.5rem">Causal mechanisms</h3>'
            f"<ul>{mech_items}</ul>"
            f"</div>"
            if mech_items else ""
        )

        sources = case.get("sources", [])
        src_html = ""
        if sources:
            items = " · ".join(f"<span>{e(s)}</span>" for s in sources)
            src_html = f'<div style="font-family:var(--mono);font-size:.6rem;color:var(--muted);padding:.75rem 1.5rem;border-top:1px solid var(--b-dim)">{items}</div>'

        sp = case.get("structural_profile", {})
        sp_pills = " ".join(
            f'<span class="pill pill-muted">{e(k.replace("_"," "))}: {e(v)}</span>'
            for k, v in sp.items()
        ) if sp else ""
        sp_html = f'<div style="padding:.75rem 1.5rem;border-top:1px solid var(--b-dim)">{sp_pills}</div>' if sp_pills else ""

        cards += f"""<div class="case-block" id="{html_lib.escape(cid)}" data-category="{html_lib.escape(cat_display)}">
  <div class="case-head">
    <div>
      <div class="case-id-label">{html_lib.escape(cid)}</div>
      <div class="case-country">{country}</div>
      <div class="case-period-tag">{period}</div>
    </div>
    <div>
      <p style="font-size:.8125rem;color:var(--muted)">{label}</p>
    </div>
    <div>
      <span class="pill pill-muted">{html_lib.escape(cat_display)}</span>
    </div>
  </div>
  <div class="case-body">
    <div class="case-section">
      <h3>Context</h3>
      <p>{context}</p>
    </div>
    <div class="case-section">
      <h3>Trigger</h3>
      <p>{trigger}</p>
    </div>
    {policy_html}
  </div>
  {mech_html}
  {sp_html}
  {outcomes_html}
  <div class="case-lesson"><strong>What worked:</strong> {lessons}</div>
  {f'<div class="case-lesson" style="color:var(--danger)"><strong>What failed:</strong> {lessons_failed}</div>' if lessons_failed else ''}
  {f'<div class="case-lesson" style="border-left:3px solid var(--accent);padding-left:.75rem;background:rgba(212,147,10,.06)"><strong>Cambodia 2029 relevance:</strong> {cam_relevance}</div>' if cam_relevance else ''}
  {src_html}
</div>"""

    filter_bar = """<div class="filter-bar">
  <button class="filter-btn active" data-filter="ALL" onclick="filterCases('ALL',this)">All</button>
  <button class="filter-btn" data-filter="TRADE" onclick="filterCases('TRADE',this)">Trade</button>
  <button class="filter-btn" data-filter="FISCAL" onclick="filterCases('FISCAL',this)">Fiscal</button>
  <button class="filter-btn" data-filter="REGULATORY" onclick="filterCases('REGULATORY',this)">Regulatory</button>
</div>"""

    body = f"""<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Structural analogues</div>
  <h1>Historical Cases</h1>
  {filter_bar}
  {cards}
</div>"""
    return _page("Cases", "cases", body, JS_FILTER)


# ── twins ─────────────────────────────────────────────────────────────────────

def build_twins(twins: list[dict]) -> str:
    if not twins:
        body = """<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Structural twins</div>
  <h1>Twin Matches</h1>
  <div class="empty-state">
    <p>No twin matches yet.</p>
    <code>python extractor/twin_matcher.py "signal text" --leader hun_manet</code>
  </div>
</div>"""
        return _page("Twins", "twins", body)

    blocks = ""
    for t in twins:
        signal = e(t.get("signal", ""))
        leader_id = e(t.get("leader_id", ""))
        date = e(t.get("analysis_date", ""))
        matches = t.get("matches", [])

        match_cards = ""
        for m in matches:
            cid = e(m.get("case_id", ""))
            country = e(m.get("country", ""))
            score = m.get("similarity_score", 0)
            pct = int(score * 100)
            rationale = e(m.get("similarity_rationale", ""))
            outcome = e(m.get("outcome_summary", ""))
            lesson = e(m.get("cambodia_lesson", ""))
            risk = m.get("risk_flag", "MEDIUM")
            risk_pill = pill(f"{risk} RISK", risk)

            match_cards += f"""<div class="twin-match-card">
  <div class="twin-score">{pct}%</div>
  <div class="twin-score-label">Structural match</div>
  <div class="twin-match-country">{country}</div>
  <div style="font-family:var(--mono);font-size:.6rem;color:var(--muted);margin-bottom:.75rem">{cid} &nbsp; {risk_pill}</div>
  <div class="twin-section"><h3>Why analogous</h3><p>{rationale}</p></div>
  <div class="twin-section"><h3>Historical outcome</h3><p>{outcome}</p></div>
  <div class="twin-section"><h3>Cambodia lesson</h3><p>{lesson}</p></div>
</div>"""

        blocks += f"""<div class="twin-block">
  <div class="twin-signal">
    <div class="twin-signal-label">◈ Signal · {leader_id} · {date}</div>
    <div class="twin-signal-text">"{signal}"</div>
  </div>
  <div class="twin-matches">{match_cards}</div>
</div>"""

    body = f"""<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Structural twins</div>
  <h1>Twin Matches</h1>
  {blocks}
</div>"""
    return _page("Twins", "twins", body)



# ── solutions ─────────────────────────────────────────────────────────────────

def build_solutions(cases: list[dict]) -> str:
    cases_by_id = {c["case_id"]: c for c in cases}

    def _case_row(case_id: str, note: str) -> str:
        c = cases_by_id.get(case_id)
        if not c:
            return ""
        les = c.get("lessons", "")
        if isinstance(les, dict):
            worked = e(les.get("what_worked", ""))
            cam = e(les.get("cambodia_2029_relevance", ""))
        else:
            worked = e(les)
            cam = ""
        return (
            f"<tr>"
            f'<td style="font-family:var(--mono);font-size:.6rem;color:var(--accent);padding:.5rem .75rem .5rem 0;white-space:nowrap;vertical-align:top">{html_lib.escape(case_id)}</td>'
            f'<td style="font-size:.78rem;padding:.5rem .75rem .5rem 0;vertical-align:top">{e(c.get("country",""))} {e(c.get("period",""))}</td>'
            f'<td style="font-size:.78rem;padding:.5rem .75rem .5rem 0;vertical-align:top">{worked}</td>'
            f'<td style="font-size:.78rem;padding:.5rem 0;vertical-align:top;color:var(--muted)">{html_lib.escape(note)}</td>'
            f"</tr>"
        )

    SCENARIOS = [
        {
            "risk": "EBA preference loss 2029",
            "description": "Cambodia's garment sector (40% of exports) loses EU EBA preferences due to democratic backsliding. 700,000 jobs at risk.",
            "cases": [
                ("VNM_WTO_2007", "Vietnam accelerated WTO-aligned reforms when facing similar trade access risk"),
                ("MUS_EPZ_1970_1995", "Mauritius diversified from sugar EPZ to multi-sector manufacturing over 25 years"),
                ("HND_CAFTA_POST_2005", "Honduras used CAFTA transition period to upgrade labour standards and retain access"),
            ],
        },
        {
            "risk": "Chinese FDI dependency + debt exposure",
            "description": "Cambodia's Chinese FDI (60%+ of inflows) creates structural dependency. Funan Canal debt burden adds fiscal fragility.",
            "cases": [
                ("LKA_FISCAL_COLLAPSE_2010_2022", "Sri Lanka's infrastructure debt trap: Chinese-funded Hambantota port → sovereign default"),
                ("IDN_AFC_RECOVERY_1998", "Indonesia negotiated IMF bailout with structural reforms after FDI flight crisis"),
                ("ARG_FISCAL_COLLAPSE_2001", "Argentina's convertibility collapse: austerity-led recession → default → heterodox recovery"),
            ],
        },
        {
            "risk": "Garment sector labour standards pressure",
            "description": "International brands impose stricter labour and environmental standards. Non-compliance triggers order diversion to Vietnam/Bangladesh.",
            "cases": [
                ("BGD_RANA_PLAZA_2013", "Bangladesh post-Rana Plaza: forced reforms improved standards but cost short-term competitiveness"),
                ("MEX_NAFTA_LABOR_1994", "Mexico used NAFTA side agreements to begin labour reform under trade framework pressure"),
                ("BGD_GARMENT_2012", "Bangladesh pre-Rana Plaza: export concentration trap — 80% garments, no diversification"),
            ],
        },
    ]

    scenarios_html = ""
    for sc in SCENARIOS:
        risk_label = html_lib.escape(sc["risk"])
        desc = html_lib.escape(sc["description"])
        rows = "".join(_case_row(cid, note) for cid, note in sc["cases"])
        table = f"""<table style="width:100%;border-collapse:collapse;margin-top:.75rem">
  <thead>
    <tr style="border-bottom:1px solid var(--b-dim)">
      <th style="font-family:var(--mono);font-size:.58rem;text-transform:uppercase;color:var(--muted);text-align:left;padding:.35rem .75rem .35rem 0">Case</th>
      <th style="font-family:var(--mono);font-size:.58rem;text-transform:uppercase;color:var(--muted);text-align:left;padding:.35rem .75rem .35rem 0">Country / Period</th>
      <th style="font-family:var(--mono);font-size:.58rem;text-transform:uppercase;color:var(--muted);text-align:left;padding:.35rem .75rem .35rem 0">What worked</th>
      <th style="font-family:var(--mono);font-size:.58rem;text-transform:uppercase;color:var(--muted);text-align:left;padding:.35rem 0">Cambodia relevance</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>"""
        scenarios_html += f"""<div style="margin-bottom:2.5rem;padding:1.5rem;border:1px solid var(--b-dim);background:var(--surface)">
  <div style="display:flex;align-items:flex-start;gap:1rem;margin-bottom:.75rem">
    <span class="pill pill-high">RISK</span>
    <div>
      <div style="font-family:var(--bebas);font-size:1.1rem;letter-spacing:.04em;color:var(--text)">{risk_label}</div>
      <div style="font-size:.8125rem;color:var(--muted);margin-top:.25rem">{desc}</div>
    </div>
  </div>
  {table}
</div>"""

    body = f"""<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Risk mitigation options</div>
  <h1>Solutions</h1>
  <p style="font-size:.8rem;color:var(--muted);margin-bottom:2rem">
    Three identified risk scenarios matched to historical response options.
    Each row shows a country that faced an analogous structural challenge and what their policy response achieved.
  </p>
  {scenarios_html}
</div>"""
    return _page("Solutions", "solutions", body)


# ── conflicts ─────────────────────────────────────────────────────────────────

def build_conflicts(conflicts: list[dict]) -> str:
    total = sum(len(c.get("conflicts", [])) for c in conflicts)
    if total == 0:
        body = """<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Doctrine contradictions</div>
  <h1>Detected Conflicts</h1>
  <div class="empty-state">
    <p>No conflicts detected yet.</p>
    <code>python extractor/conflict_detector.py hun_manet hun_sen</code>
  </div>
</div>"""
        return _page("Conflicts", "conflicts", body)

    blocks = ""
    for comp in conflicts:
        leaders_cmp = comp.get("leaders_compared", [])
        date = e(comp.get("analysis_date", ""))
        for cf in comp.get("conflicts", []):
            dim = e(cf.get("dimension", "")).upper().replace("_", " ")
            la = e(cf.get("leader_a", ""))
            la_pos = e(cf.get("leader_a_position", ""))
            la_q = cf.get("leader_a_quote", "")
            lb = e(cf.get("leader_b", ""))
            lb_pos = e(cf.get("leader_b_position", ""))
            lb_q = cf.get("leader_b_quote", "")
            expl = e(cf.get("conflict_explanation", ""))
            risk = cf.get("implementation_risk", "MEDIUM")
            pred = e(cf.get("prediction", ""))

            la_q_html = f'<blockquote style="margin-top:.5rem;font-size:.75rem">"{e(la_q)}"</blockquote>' if la_q else ""
            lb_q_html = f'<blockquote style="margin-top:.5rem;font-size:.75rem">"{e(lb_q)}"</blockquote>' if lb_q else ""

            blocks += f"""<div class="conflict-block">
  <div class="conflict-head">
    <span class="conflict-dim-label">⚠ {dim}</span>
    <div style="display:flex;align-items:center;gap:1rem">
      <span style="font-family:var(--mono);font-size:.6rem;color:var(--muted)">{" vs ".join(e(l) for l in leaders_cmp)} · {date}</span>
      {pill(f"{risk} RISK", risk)}
    </div>
  </div>
  <div class="conflict-leaders-grid">
    <div class="conflict-side">
      <div class="conflict-leader-name">{la}</div>
      <div class="conflict-pos">{la_pos}</div>
      {la_q_html}
    </div>
    <div class="conflict-side">
      <div class="conflict-leader-name">{lb}</div>
      <div class="conflict-pos">{lb_pos}</div>
      {lb_q_html}
    </div>
  </div>
  <div class="conflict-footer">
    <h3>Why simultaneous implementation is impossible</h3>
    <p style="margin-bottom:.75rem">{expl}</p>
    <div class="prediction-block">
      <h3>Predicted breaking point</h3>
      <p>{pred}</p>
    </div>
  </div>
</div>"""

    body = f"""<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Doctrine contradictions</div>
  <h1>Detected Conflicts</h1>
  {blocks}
</div>"""
    return _page("Conflicts", "conflicts", body)



# ── methodology ─────────────────────────────────────────────────────────────────────────

def build_methodology() -> str:
    body = (
        '<div class="container">' +
        '<div class="section-label">Methodology</div>' +
        '<h1>Methodology</h1>' +
        '<div style="max-width:72ch;line-height:1.8">' +
        '<h2 style="font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);margin:2rem 0 .75rem">The 7 Dimensions</h2>' +
        '<p style="font-size:.875rem;color:var(--muted);margin-bottom:1.5rem">Every leader profile maps doctrine across seven dimensions drawn from political economy. Selected because they are the axes along which development policy choices diverge most sharply.</p>' +
        '<h2 style="font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);margin:2rem 0 .75rem">Source Methodology</h2>' +
        '<p style="font-size:.875rem;color:var(--muted);margin-bottom:1rem">Profiles are built from primary sources only: official speeches, policy documents, legislative records. Each dimension requires a source URL, date, verbatim quote, and confidence score (0.0&#8211;1.0).</p>' +
        '<h2 style="font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);margin:2rem 0 .75rem">Historical Twin Matching</h2>' +
        '<p style="font-size:.875rem;color:var(--muted);margin-bottom:1rem">Twin matching scores a Cambodia policy signal against 9 historical cases across 5 structural dimensions, scored 0.0&#8211;1.0 each. Claude Sonnet 4.6 performs the scoring; reasoning is visible in the rationale field.</p>' +
        '<h2 style="font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);margin:2rem 0 .75rem">Conflict Detection</h2>' +
        '<p style="font-size:.875rem;color:var(--muted);margin-bottom:1rem">A conflict is flagged only when two positions, if simultaneously implemented, would produce incoherent policy. Differences in emphasis or timing are not conflicts.</p>' +
        '<h2 style="font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);margin:2rem 0 .75rem">About</h2>' +
        '<p style="font-size:.875rem;color:var(--muted)">Independent political intelligence system built April 2026. Pipeline: scraper &#8594; extractor &#8594; profile &#8594; site. All source URLs are preserved.</p>' +
        '</div></div>'
    )
    return _page("Methodology", "methodology", body)


# ── orchestration ─────────────────────────────────────────────────────────────
def build(clean: bool = False) -> list[Path]:
    if clean and DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    leaders   = load_leaders()
    cases     = load_cases()
    twins     = load_twins()
    conflicts = load_conflicts()

    pages = {
        "index.html":     build_index(leaders, cases, twins, conflicts),
        "leaders.html":   build_leaders(leaders),
        "cases.html":     build_cases(cases),
        "twins.html":     build_twins(twins),
        "conflicts.html": build_conflicts(conflicts),
        "solutions.html":   build_solutions(cases),
        "methodology.html": build_methodology(),
    }

    css_src = Path(__file__).parent / "style.css"
    css_dest = DOCS_DIR / "style.css"
    if css_src.exists():
        shutil.copy2(css_src, css_dest)

    written = []
    for filename, content in pages.items():
        path = DOCS_DIR / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)

    written.insert(0, css_dest)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Precedent static site.")
    parser.add_argument("--clean", action="store_true", help="Delete site/docs/ before building")
    args = parser.parse_args()

    written = build(clean=args.clean)
    for path in written:
        size_kb = path.stat().st_size / 1024
        print(f"  {path.relative_to(PROJECT_ROOT)}  ({size_kb:.1f} KB)")
    print(f"\n{len(written)} files written to site/docs/")


if __name__ == "__main__":
    main()
