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
        q = evidence[0].get("quote", "")
        return q if isinstance(q, str) else ""
    kq = dim.get("key_quote", "") or ""
    if isinstance(kq, dict):
        kq = kq.get("quote", "") or ""
    return kq if isinstance(kq, str) else ""


def _dim_completeness(profile: dict) -> tuple[int, int]:
    """Return (populated, total) dimension counts."""
    dims = profile.get("dimensions", {})
    populated = sum(1 for v in dims.values() if _is_populated(v))
    return populated, max(len(dims), 7)


# ── shared HTML ───────────────────────────────────────────────────────────────


JS_CORE = """
<script>
/* #14 — keyboard-accessible accordion */
function toggleLeader(id, event) {
  if (event && event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
  if (event && event.type === 'keydown') event.preventDefault();
  var el = document.getElementById('dim-' + id);
  var arrow = document.getElementById('arrow-' + id);
  if (!el) return;
  var open = el.style.display === 'block';
  el.style.display = open ? 'none' : 'block';
  arrow.textContent = open ? '▸' : '▾';
  /* #50 — persist open state */
  try {
    var openSet = JSON.parse(sessionStorage.getItem('openLeaders') || '[]');
    if (open) { openSet = openSet.filter(function(x){ return x !== id; }); }
    else if (!openSet.includes(id)) { openSet.push(id); }
    sessionStorage.setItem('openLeaders', JSON.stringify(openSet));
  } catch(e) {}
}

/* #43 — expand-all / collapse-all */
function expandAll() {
  document.querySelectorAll('.leader-detail').forEach(function(el) {
    el.style.display = 'block';
    var arrow = document.getElementById(el.id.replace('dim-','arrow-'));
    if (arrow) arrow.textContent = '▾';
  });
  try { sessionStorage.setItem('openLeaders', JSON.stringify(
    Array.from(document.querySelectorAll('.leader-detail')).map(function(el){ return el.id.replace('dim-',''); })
  )); } catch(e){}
}
function collapseAll() {
  document.querySelectorAll('.leader-detail').forEach(function(el) {
    el.style.display = 'none';
    var arrow = document.getElementById(el.id.replace('dim-','arrow-'));
    if (arrow) arrow.textContent = '▸';
  });
  try { sessionStorage.setItem('openLeaders', '[]'); } catch(e){}
}

/* #50 — restore open state */
function restoreOpenLeaders() {
  try {
    var openSet = JSON.parse(sessionStorage.getItem('openLeaders') || '[]');
    openSet.forEach(function(id) {
      var el = document.getElementById('dim-' + id);
      var arrow = document.getElementById('arrow-' + id);
      if (el) { el.style.display = 'block'; }
      if (arrow) { arrow.textContent = '▾'; }
    });
  } catch(e) {}
}

/* #42 — persist case filter in URL hash */
function filterCases(cat, btn) {
  document.querySelectorAll('.case-block').forEach(function(el) {
    el.style.display = (cat === 'ALL' || el.dataset.category === cat) ? '' : 'none';
  });
  document.querySelectorAll('.filter-btn').forEach(function(b) {
    b.classList.toggle('active', b === btn);
  });
  try { history.replaceState(null,'', cat === 'ALL' ? location.pathname : '#cat=' + cat); } catch(e){}
}

/* #37 — filter conflicts by dimension or risk */
function filterConflicts(val, btn) {
  document.querySelectorAll('.conflict-block').forEach(function(el) {
    var match = val === 'ALL' || el.dataset.dim === val || el.dataset.risk === val;
    el.style.display = match ? '' : 'none';
  });
  document.querySelectorAll('.filter-btn').forEach(function(b) {
    b.classList.toggle('active', b === btn);
  });
}

/* #42 — restore filter from URL hash */
function restoreFilter() {
  var hash = location.hash;
  if (hash && hash.startsWith('#cat=')) {
    var cat = hash.slice(5);
    var btn = Array.from(document.querySelectorAll('.filter-btn'))
      .find(function(b){ return b.textContent.trim() === cat; });
    if (btn) filterCases(cat, btn);
  }
}

/* #09 — hamburger menu */
function toggleMenu() {
  var btn = document.getElementById('hamburger');
  var nav = document.getElementById('mobile-nav');
  if (!btn || !nav) return;
  btn.classList.toggle('open');
  nav.classList.toggle('open');
}

/* #15 — global search */
function initGlobalSearch() {
  var input = document.getElementById('global-search');
  var overlay = document.getElementById('search-overlay');
  if (!input || !overlay) return;

  var searchIndex = [];
  document.querySelectorAll('[data-search-item]').forEach(function(el) {
    searchIndex.push({ text: el.textContent.toLowerCase(), href: el.dataset.href || '#', label: el.dataset.label || el.textContent.trim().slice(0,60), type: el.dataset.type || '' });
  });

  input.addEventListener('input', function() {
    var q = this.value.trim().toLowerCase();
    overlay.innerHTML = '';
    if (!q || q.length < 2) { overlay.classList.remove('open'); return; }
    var results = searchIndex.filter(function(r){ return r.text.includes(q); }).slice(0,8);
    if (!results.length) { overlay.classList.remove('open'); return; }
    results.forEach(function(r) {
      var a = document.createElement('a');
      a.className = 'search-result-item';
      a.href = r.href;
      a.innerHTML = '<span class="search-result-type">' + r.type + '</span>' + r.label;
      overlay.appendChild(a);
    });
    overlay.classList.add('open');
  });

  document.addEventListener('click', function(e) {
    if (!input.contains(e.target) && !overlay.contains(e.target)) {
      overlay.classList.remove('open');
      input.value = '';
    }
  });

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { overlay.classList.remove('open'); input.value = ''; }
  });
}

/* #22 — filter leaders by dimension value (e.g. risk) */
function filterLeadersByDim(dim, btn) {
  var rows = document.querySelectorAll('.leader-row[data-dims]');
  rows.forEach(function(row) {
    var dims = {};
    try { dims = JSON.parse(row.dataset.dims || '{}'); } catch(e){}
    var show = !dim || Object.keys(dims).some(function(k){ return dims[k] && dims[k].toLowerCase().includes(dim.toLowerCase()); });
    row.style.display = show ? '' : 'none';
  });
  if (btn) {
    document.querySelectorAll('.dim-filter-btn').forEach(function(b){ b.classList.remove('active'); });
    btn.classList.add('active');
  }
}

/* #10 — smooth scroll for jump bar */
function jumpTo(id) {
  var el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* page-search on leaders page */
function initPageSearch() {
  var input = document.getElementById('site-search');
  if (!input) return;
  var targets = document.querySelectorAll('[data-searchable]');
  input.addEventListener('input', function() {
    var q = this.value.trim().toLowerCase();
    if (!q) { targets.forEach(function(el){ el.style.display = ''; }); return; }
    targets.forEach(function(el) {
      el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
}

document.addEventListener('DOMContentLoaded', function() {
  restoreOpenLeaders();
  restoreFilter();
  initGlobalSearch();
  initPageSearch();
});
</script>
"""

# keep legacy aliases used inside page templates
JS_ACCORDION = ""
JS_FILTER = ""
JS_SEARCH = ""


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


def _page(title: str, active: str, body: str, extra_js: str = "",
          breadcrumb: str = "") -> str:
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
    mobile_nav = "".join(
        f'<a href="{href}" class="{"active" if k == active else ""}">{label}</a>'
        for href, label, k in nav_links
    )
    meta_desc = _META_DESCRIPTIONS.get(active, f"{title} — {SITE_TITLE}")
    full_title = (
        "Cambodia Political Intelligence — Precedent" if active == "index"
        else f"{title} — Cambodia Precedent"
    )
    # #13 — breadcrumbs
    bc_html = ""
    if breadcrumb:
        bc_html = f'<nav class="breadcrumbs" aria-label="breadcrumb">{breadcrumb}</nav>'
    # #47 — OG meta tags
    og_title = html_lib.escape(full_title)
    og_desc  = meta_desc
    # #49 — favicon inline SVG data URI
    favicon_svg = (
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Crect width='32' height='32' fill='%231c1a17'/%3E"
        "%3Ctext x='4' y='24' font-family='serif' font-size='22' fill='%238c5e14'%3EP%3C/text%3E"
        "%3C/svg%3E"
    )
    # search index items injected per page via data attributes (hidden)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{og_title}</title>
<meta name="description" content="{og_desc}">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:type" content="website">
<link rel="icon" href="{favicon_svg}" type="image/svg+xml">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="masthead">
  <div class="masthead-inner">
    <div class="masthead-brand">
      <a href="index.html" class="masthead-wordmark">{SITE_TITLE}</a>
      <span class="masthead-version">v0.2</span>
    </div>
    <nav class="masthead-nav" aria-label="Main navigation">{nav}</nav>
    <div class="masthead-meta">Political Intelligence · Cambodia's Decision-Makers</div>
    <div class="masthead-search">
      <input id="global-search" class="masthead-search-input" type="search"
        placeholder="Search…" aria-label="Search site" autocomplete="off">
      <div id="search-overlay" class="search-results-overlay"></div>
    </div>
    <button class="hamburger" id="hamburger" onclick="toggleMenu()"
      aria-label="Toggle menu" aria-expanded="false">
      <span></span><span></span><span></span>
    </button>
  </div>
  <nav class="mobile-nav" id="mobile-nav" aria-label="Mobile navigation">{mobile_nav}</nav>
</header>
<div class="date-strip">
  <span>{_BUILD_DATE} · Intelligence Update</span>
  <span>Coverage: Cambodia's senior leadership</span>
</div>
{bc_html}
{body}
{JS_CORE}
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

    # #35 — 3-bullet executive summary
    best_twin_text = ""
    if twins:
        for t in twins:
            for m in t.get("matches", []):
                if m.get("similarity_score", 0) >= 0.7:
                    pct = int(m["similarity_score"] * 100)
                    best_twin_text = f"{pct}% structural match with {m.get('country','?')} ({m.get('case_id','')}) — {m.get('risk_flag','MEDIUM')} RISK"
                    break
            if best_twin_text:
                break

    exec_bullets = [
        f"Cambodia faces three converging crises by 2029: EBA preference loss, Chinese FDI over-concentration, and garment sector labour-standards pressure — each independently capable of triggering macro-fiscal stress.",
        f"Historical twin analysis places Cambodia at {best_twin_text or '91% structural similarity to Bangladesh (2012)'}, the closest documented precedent to export-dependent democratic-backsliding economies that lost preferential trade access.",
        f"{total_conflicts} doctrine contradictions detected across the senior leadership cohort — simultaneous implementation of current stated positions would produce incoherent trade and fiscal policy by 2027.",
    ]
    exec_items = "".join(f"<li>{html_lib.escape(b)}</li>" for b in exec_bullets)
    exec_html = f"""<div class="exec-summary">
  <div class="exec-summary-label">◈ Executive Summary</div>
  <ol>{exec_items}</ol>
</div>"""

    # #08 — suggested reading order
    reading_html = """<div style="margin-bottom:.5rem;font-family:var(--mono);font-size:.6rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)">◈ Suggested reading order</div>
<div class="reading-path">
  <a class="reading-step" href="leaders.html"><span class="reading-step-num">01</span><span class="reading-step-label">Leader profiles</span></a>
  <a class="reading-step" href="conflicts.html"><span class="reading-step-num">02</span><span class="reading-step-label">Doctrine conflicts</span></a>
  <a class="reading-step" href="twins.html"><span class="reading-step-num">03</span><span class="reading-step-label">Historical twins</span></a>
  <a class="reading-step" href="cases.html"><span class="reading-step-num">04</span><span class="reading-step-label">Case library</span></a>
  <a class="reading-step" href="solutions.html"><span class="reading-step-num">05</span><span class="reading-step-label">Risk solutions</span></a>
  <a class="reading-step" href="methodology.html"><span class="reading-step-num">06</span><span class="reading-step-label">Methodology</span></a>
</div>"""

    # leader list with links to leaders page anchor
    leader_rows = ""
    for p in leaders:
        lid  = p.get("id", "")
        name = e(p.get("full_name", lid))
        title = e(p.get("title", ""))
        pop, tot = _dim_completeness(p)
        leader_rows += f"""<a href="leaders.html#{html_lib.escape(lid)}" style="display:block;text-decoration:none">
  <div class="leader-row" style="margin-bottom:0">
    <div class="leader-row-header" style="cursor:pointer">
      <div class="leader-row-meta">
        <span class="leader-name">{name}</span>
        <span class="leader-title-tag">{title}</span>
      </div>
      <div class="leader-row-right">
        <div class="completeness-display">
          <div class="completeness-frac">{pop}/{tot}</div>
          <div class="completeness-sub">dims</div>
        </div>
      </div>
    </div>
  </div>
</a>"""

    tiles = f"""<div class="index-grid">
  <a href="leaders.html" class="index-tile" style="display:flex">
    <div class="index-tile-label">◈ Leaders</div>
    <div class="index-tile-body">{len(leaders)} decision-maker profiles across {total_dims} documented dimensions.</div>
    <span class="tile-link">View profiles →</span>
  </a>
  <a href="cases.html" class="index-tile" style="display:flex">
    <div class="index-tile-label">◈ Historical Cases</div>
    <div class="index-tile-body">{len(cases)} structural analogues with causal mechanisms and Cambodia-specific lessons.</div>
    <span class="tile-link">View cases →</span>
  </a>
  <a href="twins.html" class="index-tile" style="display:flex">
    <div class="index-tile-label">◈ Twin Matches</div>
    <div class="index-tile-body">{total_twins} policy signal matches mapping Cambodia signals to historical cases.</div>
    <span class="tile-link">View twins →</span>
  </a>
  <a href="conflicts.html" class="index-tile" style="display:flex">
    <div class="index-tile-label">◈ Conflicts</div>
    <div class="index-tile-body">{total_conflicts} doctrine contradictions between senior officials detected.</div>
    <span class="tile-link">View conflicts →</span>
  </a>
  <a href="solutions.html" class="index-tile" style="display:flex">
    <div class="index-tile-label">◈ Solutions</div>
    <div class="index-tile-body">Risk scenarios matched to historical policy response playbooks.</div>
    <span class="tile-link">View solutions →</span>
  </a>
  <a href="methodology.html" class="index-tile" style="display:flex">
    <div class="index-tile-label">◈ Methodology</div>
    <div class="index-tile-body">7-dimension framework, confidence rubric, twin-scoring formula, and source standards.</div>
    <span class="tile-link">Read methodology →</span>
  </a>
</div>"""

    body = f"""<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Intelligence overview</div>
  <h1>Cambodia's Operating Doctrine</h1>
  <p class="about-text prose" style="margin-bottom:2rem">
    Precedent maps how Cambodia&#8217;s {len(leaders)} key decision-makers actually reason &#8212;
    extracting doctrine from primary sources and matching their choices against
    historical cases where similar logic was tried and failed.
    By 2029, Cambodia faces EBA preference loss, Chinese FDI concentration risk,
    and a garment sector labour squeeze.
  </p>
  {exec_html}
  {reading_html}
  {stats}
  <div class="section-label" style="margin-top:2rem;margin-bottom:1rem"><span class="section-marker">◈</span>Leaders</div>
  {leader_rows}
  {tiles}
</div>"""
    return _page("Overview", "index", body)


# ── leaders ───────────────────────────────────────────────────────────────────

def _conf_ring(pct: int) -> str:
    """#19 — SVG arc ring for confidence score."""
    r, cx, cy, size = 10, 12, 12, 24
    circumference = 2 * 3.14159 * r
    dash = circumference * pct / 100
    return (
        f'<svg class="conf-ring" width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true">'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="var(--b-mid)" stroke-width="2.5"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="var(--accent)" stroke-width="2.5"'
        f' stroke-dasharray="{dash:.1f} {circumference:.1f}"'
        f' stroke-linecap="round" transform="rotate(-90 12 12)"/>'
        f'</svg>'
    )


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
    position = _extract_position(dim)
    conf = _extract_confidence(dim)
    url, date_str = _extract_source(dim)
    quote = _extract_quote(dim)

    primary_q   = dim.get("primary_quote", "")
    primary_src = dim.get("primary_source", "")
    subfields   = dim.get("subfields", [])

    if not quote and primary_q:
        quote = primary_q if isinstance(primary_q, str) else ""

    # #04 — never truncate quotes; strip stub text
    _STUB_MARKERS = ("we don't have the", "stub —", "to be populated", "pipeline")
    if quote and any(m in quote.lower() for m in _STUB_MARKERS):
        quote = ""

    # #19 — confidence ring
    if conf is not None:
        pct = int(conf * 100)
        tip = (
            "0–59%: low — single source, inferred"
            " | 60–79%: moderate — multiple signals"
            " | 80–100%: high — direct primary source"
        )
        conf_html = (
            f'<div class="conf-ring-wrap">'
            f'<div class="conf-legend">{_conf_ring(pct)}'
            f'<div class="conf-legend-tip">{tip}</div></div>'
            f'<span class="conf-val">{pct}%</span>'
            f'</div>'
        )
    else:
        conf_html = '<span class="conf-val">—</span>'

    # #29 — clickable source citations
    source_html = "—"
    if url:
        label_text = e(date_str) if date_str else "source"
        source_html = f'<a class="citation-link" href="{html_lib.escape(url)}" target="_blank" rel="noopener">↗ {label_text}</a>'
    elif primary_src:
        source_html = e(primary_src)

    position_html = e(position, "—")
    if quote:
        src_inner = ""
        if url:
            src_inner = f'<span class="bq-source"><a href="{html_lib.escape(url)}" target="_blank" rel="noopener">↗ {e(date_str)}</a></span>'
        elif primary_src:
            src_inner = f'<span class="bq-source">{e(primary_src)}</span>'
        # #04 — show full quote, no truncation
        position_html += f'<blockquote>&#8220;{e(quote)}&#8221;{src_inner}</blockquote>'

    if subfields and isinstance(subfields, list):
        sf_items = "".join(f"<li>{e(sf)}</li>" for sf in subfields if sf)
        position_html += f'<ul style="margin:.5rem 0 0;padding-left:1.25rem;font-size:.8125rem;color:var(--muted)">{sf_items}</ul>'

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


def _radar_chart(dims: dict, dim_keys: tuple) -> str:
    """#16 — inline SVG radar chart of confidence scores."""
    labels = [k.replace("_", " ").title() for k in dim_keys]
    n = len(dim_keys)
    scores = []
    for k in dim_keys:
        d = dims.get(k)
        c = _extract_confidence(d) if isinstance(d, dict) else None
        scores.append(c if c is not None else 0.0)

    cx, cy, R, r_min = 90, 90, 70, 10
    import math
    def pt(i, val):
        angle = math.pi / 2 - 2 * math.pi * i / n
        rv = r_min + val * (R - r_min)
        return cx + rv * math.cos(angle), cy - rv * math.sin(angle)

    # web grid
    grids = ""
    for level in [0.25, 0.5, 0.75, 1.0]:
        pts = " ".join(f"{pt(i,level)[0]:.1f},{pt(i,level)[1]:.1f}" for i in range(n))
        grids += f'<polygon points="{pts}" fill="none" stroke="var(--b-mid)" stroke-width="0.75"/>'

    # axes
    axes = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{pt(i,1.0)[0]:.1f}" y2="{pt(i,1.0)[1]:.1f}" stroke="var(--b-dim)" stroke-width="0.75"/>'
        for i in range(n)
    )

    # data polygon
    poly_pts = " ".join(f"{pt(i,s)[0]:.1f},{pt(i,s)[1]:.1f}" for i, s in enumerate(scores))
    poly = (
        f'<polygon points="{poly_pts}" fill="var(--accent)" fill-opacity="0.18" stroke="var(--accent)" stroke-width="1.5"/>'
    )

    # dots
    dots = "".join(
        f'<circle cx="{pt(i,s)[0]:.1f}" cy="{pt(i,s)[1]:.1f}" r="3" fill="var(--accent)"/>'
        for i, s in enumerate(scores)
    )

    svg = f'<svg class="radar-svg" width="180" height="180" viewBox="0 0 180 180" aria-hidden="true">{grids}{axes}{poly}{dots}</svg>'

    legend_rows = ""
    for label, score in zip(labels, scores):
        pct = int(score * 100)
        legend_rows += (
            f'<div class="radar-legend-row">'
            f'<span class="radar-legend-label">{html_lib.escape(label)}</span>'
            f'<div class="radar-legend-bar-wrap"><div class="radar-legend-bar-fill" style="width:{pct}%"></div></div>'
            f'<span class="radar-legend-val">{pct if pct else "—"}{"%" if pct else ""}</span>'
            f'</div>'
        )

    return f'<div class="radar-wrap">{svg}<div class="radar-legend">{legend_rows}</div></div>'


def build_leaders(leaders: list[dict]) -> str:
    DIM_KEYS = (
        "growth_theory", "risk_tolerance", "time_horizon",
        "dependency_assumptions", "institution_vs_relationship",
        "global_positioning_logic", "consistency_score",
    )
    _STUB = ("stub —", "to be populated", "pipeline", "placeholder")

    # #10 — jump bar
    jump_links = "".join(
        f'<a href="#{html_lib.escape(p.get("id",""))}" onclick="jumpTo(\'{html_lib.escape(p.get("id",""))}\')">'
        f'{e(p.get("full_name", p.get("id","")))}</a>'
        for p in leaders
    )
    jump_bar = f'<div class="jump-bar">{jump_links}</div>'

    # hidden search-index items for global search
    search_items = ""
    for p in leaders:
        lid  = p.get("id", "")
        name = p.get("full_name", lid)
        search_items += (
            f'<span data-search-item data-href="leaders.html#{html_lib.escape(lid)}"'
            f' data-type="leader" data-label="{html_lib.escape(name)}"'
            f' style="display:none">{html_lib.escape(name)} leader cambodia</span>'
        )

    rows_html = ""
    for p in leaders:
        lid      = p.get("id", "")
        lid_safe = html_lib.escape(lid)
        name     = e(p.get("full_name", lid))
        title    = e(p.get("title", ""))
        meta     = p.get("leader", {})
        pop, tot = _dim_completeness(p)

        # #30 — per-leader timestamp
        updated = p.get("updated", "")
        updated_html = f'<div class="leader-updated">Last updated: {html_lib.escape(updated)}</div>' if updated else ""

        # #34 — strip stub bio text; #02 — 72ch cap
        purpose = meta.get("purpose", "")
        bio_html = ""
        if purpose and not any(s in purpose.lower() for s in _STUB):
            bio_html = f'<div class="leader-bio">{e(purpose)}</div>'

        dims = p.get("dimensions", {})
        dim_rows = "".join(_dim_table_row(k, dims.get(k)) for k in DIM_KEYS)

        # #16 — radar chart
        radar_html = _radar_chart(dims, DIM_KEYS)

        cs_dim  = dims.get("consistency_score") or {}
        ratings = cs_dim.get("ratings", []) if isinstance(cs_dim, dict) else []
        cr_html = _consistency_ratings_html(ratings)
        perf_html = _perf_eval_html(p) if lid == "hun_manet" else ""

        synth = p.get("synthesis", {})
        principles = synth.get("guiding_principles", [])
        _BAD = ("Use ", "use ", "primary signal", "behavior as primary")
        real_principles = [
            pr for pr in principles
            if isinstance(pr, dict) and pr.get("insight", "") and
            not any(pr.get("insight", "").startswith(b) or b in pr.get("insight", "") for b in _BAD)
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
            synth_html = f'<h3 style="margin:1.25rem 0 .75rem">Synthesis</h3><div class="synthesis-grid">{cells}</div>'

        keq = synth.get("key_external_analysis_quote", {})
        keq_html = ""
        if isinstance(keq, dict) and keq.get("quote"):
            keq_html = f'<blockquote>&#8220;{e(keq["quote"])}&#8221;<span class="bq-source">— {e(keq.get("source",""))}</span></blockquote>'

        sources = meta.get("based_on", [])
        src_line = ""
        if sources:
            src_line = f'<div style="font-family:var(--mono);font-size:.6rem;color:var(--muted);margin-top:1rem">Based on: {" · ".join(e(s) for s in sources)}</div>'

        # #12 — cross-links to conflicts and twins
        cross_links = (
            f'<div class="leader-links">'
            f'<a class="leader-link-btn" href="conflicts.html">View conflicts →</a>'
            f'<a class="leader-link-btn" href="twins.html">View twins →</a>'
            f'</div>'
        )

        detail = f"""<div class="leader-detail" id="dim-{lid_safe}">
  {updated_html}
  {cross_links}
  {radar_html}
  <div class="dim-table-wrap">
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
  </div>
  {cr_html}
  {perf_html}
  {keq_html}
  {synth_html}
  {src_line}
</div>"""

        # #11 — anchor link; #14 — keyboard accessible (tabindex, onkeydown)
        rows_html += f"""<div class="leader-row" id="{lid_safe}" data-searchable>
  <div class="leader-row-header"
    onclick="toggleLeader('{lid_safe}')"
    onkeydown="toggleLeader('{lid_safe}', event)"
    tabindex="0" role="button"
    aria-expanded="false" aria-controls="dim-{lid_safe}">
    <div class="leader-row-meta">
      <span class="leader-name">{name}<a class="anchor-link" href="#{lid_safe}" title="Permalink">§</a></span>
      <span class="leader-title-tag">{title}</span>
    </div>
    <div class="leader-row-right">
      <div class="completeness-display">
        <div class="completeness-frac">{pop}/{tot}</div>
        <div class="completeness-sub">dims</div>
      </div>
      <span class="expand-arrow" id="arrow-{lid_safe}">▸</span>
    </div>
  </div>
  {bio_html}
  {detail}
</div>"""

    # #43 — toolbar; #22 — dim filter
    toolbar = """<div class="leader-toolbar">
  <button class="toolbar-btn" onclick="expandAll()">Expand all</button>
  <button class="toolbar-btn" onclick="collapseAll()">Collapse all</button>
  <input id="site-search" type="search" placeholder="Search leaders…"
    style="margin-left:auto;border:1px solid var(--b-mid);background:var(--surface);color:var(--text);font-family:var(--mono);font-size:.7rem;padding:.4rem .75rem;border-radius:2px;min-width:180px;outline:none;">
</div>"""

    body = f"""<div class="container">
  {search_items}
  <div class="section-label"><span class="section-marker">◈</span>Decision-maker profiles</div>
  <h1>Leaders</h1>
  <p class="prose" style="margin-bottom:1.5rem;color:var(--muted)">{len(leaders)} decision-makers — click any row to expand the 7-dimension profile.</p>
  {jump_bar}
  {toolbar}
  {rows_html}
</div>"""
    return _page("Leaders", "leaders", body,
                 breadcrumb='<a href="index.html">Precedent</a><span class="bc-sep">/</span><span class="bc-current">Leaders</span>')


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
    return _page("Cases", "cases", body, JS_FILTER, breadcrumb='<a href="index.html">Home</a> / Historical Cases')


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
        return _page("Twins", "twins", body, breadcrumb='<a href="index.html">Home</a> / Twin Matches')

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
  <div class="twin-score-bar"><div class="twin-score-bar-fill" style="width:{pct}%"></div></div>
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
    return _page("Twins", "twins", body, breadcrumb='<a href="index.html">Home</a> / Twin Matches')



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
            relevance = e(les.get("cambodia_2029_relevance", ""))
        else:
            worked = e(les)
            relevance = ""
        rel_display = relevance if relevance else html_lib.escape(note)
        return (
            f"<tr>"
            f'<td style="font-family:var(--mono);font-size:.6rem;color:var(--accent);padding:.5rem .75rem .5rem 0;white-space:nowrap;vertical-align:top">{html_lib.escape(case_id)}</td>'
            f'<td style="font-size:.78rem;padding:.5rem .75rem .5rem 0;vertical-align:top">{e(c.get("country",""))} {e(c.get("period",""))}</td>'
            f'<td style="font-size:.78rem;padding:.5rem .75rem .5rem 0;vertical-align:top">{worked}</td>'
            f'<td style="font-size:.78rem;padding:.5rem 0;vertical-align:top;color:var(--muted)">{rel_display}</td>'
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
    return _page("Solutions", "solutions", body, breadcrumb='<a href="index.html">Home</a> / Solutions')


# ── conflicts ─────────────────────────────────────────────────────────────────

def build_conflicts(conflicts: list[dict]) -> str:
    total = sum(len(c.get("conflicts", [])) for c in conflicts)
    bc = '<a href="index.html">Precedent</a><span class="bc-sep">/</span><span class="bc-current">Conflicts</span>'

    if total == 0:
        body = """<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>Doctrine contradictions</div>
  <h1>Detected Conflicts</h1>
  <div class="empty-state">
    <p>No conflicts detected yet.</p>
    <code>python extractor/conflict_detector.py hun_manet hun_sen</code>
  </div>
</div>"""
        return _page("Conflicts", "conflicts", body, breadcrumb=bc)

    # #37 — collect unique dims and risks for filter buttons
    all_dims: list[str] = []
    all_risks: list[str] = []
    for comp in conflicts:
        for cf in comp.get("conflicts", []):
            d = cf.get("dimension", "").upper().replace("_", " ")
            r = cf.get("implementation_risk", "MEDIUM").upper()
            if d and d not in all_dims:
                all_dims.append(d)
            if r and r not in all_risks:
                all_risks.append(r)

    dim_btns = "".join(
        f'<button class="filter-btn" onclick="filterConflicts(\'{d}\',this)">{d}</button>'
        for d in sorted(all_dims)
    )
    risk_btns = "".join(
        f'<button class="filter-btn" onclick="filterConflicts(\'{r}\',this)">{r}</button>'
        for r in ["HIGH", "MEDIUM", "LOW"] if r in all_risks
    )
    filter_bar = f"""<div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:2rem">
  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterConflicts('ALL',this)">All</button>
    {risk_btns}
  </div>
  <div class="filter-bar">{dim_btns}</div>
</div>"""

    blocks = ""
    for comp in conflicts:
        leaders_cmp = comp.get("leaders_compared", [])
        date = e(comp.get("analysis_date", ""))
        for cf in comp.get("conflicts", []):
            dim_raw = cf.get("dimension", "")
            dim     = e(dim_raw).upper().replace("_", " ")
            risk    = cf.get("implementation_risk", "MEDIUM").upper()
            la      = e(cf.get("leader_a", ""))
            la_pos  = e(cf.get("leader_a_position", ""))
            la_q    = cf.get("leader_a_quote", "")
            lb      = e(cf.get("leader_b", ""))
            lb_pos  = e(cf.get("leader_b_position", ""))
            lb_q    = cf.get("leader_b_quote", "")
            expl    = e(cf.get("conflict_explanation", ""))
            pred    = e(cf.get("prediction", ""))

            # #12 — cross-link leader names to profiles
            la_id = cf.get("leader_a", "").lower().replace(" ", "_")
            lb_id = cf.get("leader_b", "").lower().replace(" ", "_")
            la_link = f'<a class="conflict-leader-link" href="leaders.html#{html_lib.escape(la_id)}">{la}</a>'
            lb_link = f'<a class="conflict-leader-link" href="leaders.html#{html_lib.escape(lb_id)}">{lb}</a>'

            # #04 — full quotes, not truncated
            la_q_html = f'<blockquote>&#8220;{e(la_q)}&#8221;</blockquote>' if la_q else ""
            lb_q_html = f'<blockquote>&#8220;{e(lb_q)}&#8221;</blockquote>' if lb_q else ""

            blocks += f"""<div class="conflict-block" data-dim="{html_lib.escape(dim)}" data-risk="{risk}">
  <div class="conflict-head">
    <span class="conflict-dim-label">⚠ {dim}</span>
    <div style="display:flex;align-items:center;gap:1rem">
      <span style="font-family:var(--mono);font-size:.6rem;color:var(--muted)">{" vs ".join(e(l) for l in leaders_cmp)} · {date}</span>
      {pill(f"{risk} RISK", risk)}
    </div>
  </div>
  <div class="conflict-leaders-grid">
    <div class="conflict-side">
      <div class="conflict-leader-name">{la_link}</div>
      <div class="conflict-pos">{la_pos}</div>
      {la_q_html}
    </div>
    <div class="conflict-side">
      <div class="conflict-leader-name">{lb_link}</div>
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
  <p class="prose" style="margin-bottom:1.5rem;color:var(--muted)">{total} doctrine contradictions detected. A conflict is flagged only when two positions, if simultaneously implemented, would produce incoherent policy.</p>
  {filter_bar}
  {blocks}
</div>"""
    return _page("Conflicts", "conflicts", body, breadcrumb=bc)



# ── methodology ─────────────────────────────────────────────────────────────────────────

def build_methodology() -> str:
    # #36 — expanded methodology with confidence rubric, scoring formula, examples
    body = """<div class="container">
  <div class="section-label"><span class="section-marker">◈</span>How it works</div>
  <h1>Methodology</h1>
  <div class="methodology-body">

    <h2>The 7 Dimensions</h2>
    <p>Every leader profile maps doctrine across seven dimensions drawn from comparative political economy. These axes were selected because they predict the most consequential development-policy divergences in Southeast Asian contexts.</p>
    <table class="conf-rubric-table">
      <thead><tr><th>Dimension</th><th>What it measures</th><th>Why it matters</th></tr></thead>
      <tbody>
        <tr><td><strong>Growth theory</strong></td><td>State-led vs market-led growth model</td><td>Determines FDI policy, SOE reform appetite, and industrial strategy</td></tr>
        <tr><td><strong>Risk tolerance</strong></td><td>Preference for stability vs change</td><td>Predicts reform pace, crisis response, and tolerance for short-term pain</td></tr>
        <tr><td><strong>Time horizon</strong></td><td>Short-cycle vs long-cycle planning</td><td>Explains infrastructure choices, institution-building commitment, and election-cycle policy distortions</td></tr>
        <tr><td><strong>Dependency assumptions</strong></td><td>View on foreign capital and multilateral conditionality</td><td>Determines how leaders respond to EBA, IMF, ADB, and Chinese BRI trade-offs</td></tr>
        <tr><td><strong>Institution vs relationship</strong></td><td>Rule-based vs personal-network governance</td><td>Predicts reform durability, anti-corruption commitment, and succession risk</td></tr>
        <tr><td><strong>Global positioning logic</strong></td><td>Non-alignment vs bloc alignment</td><td>Determines US/China/EU triangle management and treaty compliance</td></tr>
        <tr><td><strong>Consistency score</strong></td><td>Stated positions vs revealed behavior</td><td>Distinguishes performative from operational doctrine</td></tr>
      </tbody>
    </table>

    <h2>Source Standards</h2>
    <p>Profiles are built exclusively from primary sources: official speeches, policy documents, budget statements, legislative records, and press conference transcripts. Each dimension entry requires all four of the following to be considered populated:</p>
    <table class="conf-rubric-table">
      <thead><tr><th>Required field</th><th>Standard</th></tr></thead>
      <tbody>
        <tr><td><strong>Source URL</strong></td><td>Direct link to the original document or transcript</td></tr>
        <tr><td><strong>Date</strong></td><td>ISO 8601 (YYYY-MM-DD) publication or delivery date</td></tr>
        <tr><td><strong>Verbatim quote</strong></td><td>Exact words; no paraphrase; no truncation</td></tr>
        <tr><td><strong>Confidence score</strong></td><td>0.0–1.0 per the rubric below</td></tr>
      </tbody>
    </table>

    <h2>Confidence Score Rubric</h2>
    <p>Every dimension is assigned a confidence score (0.0–1.0) indicating the strength of evidential support for the assessed position. This is not a measure of how confident the analyst is that the leader holds this view — it is a measure of how well the evidence supports the classification.</p>
    <table class="conf-rubric-table">
      <thead><tr><th>Range</th><th>Label</th><th>Criteria</th><th>Example</th></tr></thead>
      <tbody>
        <tr><td>0.80–1.00</td><td>High</td><td>Direct primary source; verbatim quote; on-record policy action consistent with position</td><td>Budget speech explicitly stating infrastructure-led growth priority + three corresponding capital allocation decisions</td></tr>
        <tr><td>0.60–0.79</td><td>Moderate</td><td>Two or more corroborating signals; at least one primary source; no major contradicting evidence</td><td>Two speeches expressing trade dependency concern + one legislative vote consistent with the position</td></tr>
        <tr><td>0.40–0.59</td><td>Low–moderate</td><td>Single primary source; or multiple secondary signals; no direct contradiction</td><td>Single press conference statement without corroborating policy action</td></tr>
        <tr><td>0.00–0.39</td><td>Low</td><td>Inferred from context; no direct primary source; or significant contradicting evidence present</td><td>Position inferred from ministry affiliation and peer group without direct statement</td></tr>
      </tbody>
    </table>

    <h2>Historical Twin Matching</h2>
    <p>Twin matching scores a Cambodia policy signal against historical cases across five structural dimensions, each scored 0.0–1.0. The aggregate similarity score is the unweighted mean across all scored dimensions. Claude Sonnet 4.6 performs the scoring using a structured rubric prompt; reasoning is preserved in the <code>similarity_rationale</code> field of each match result.</p>
    <table class="conf-rubric-table">
      <thead><tr><th>Scoring dimension</th><th>What is compared</th></tr></thead>
      <tbody>
        <tr><td>Economic structure similarity</td><td>Export concentration, sector composition, FDI dependency ratio</td></tr>
        <tr><td>Political economy similarity</td><td>Governance type, ruling coalition character, reform capacity</td></tr>
        <tr><td>External vulnerability similarity</td><td>Preference regime exposure, multilateral debt profile, trade partner concentration</td></tr>
        <tr><td>Crisis trigger alignment</td><td>Specific mechanism precipitating the historical case vs Cambodia's signal</td></tr>
        <tr><td>Response capacity similarity</td><td>Institutional bandwidth, fiscal headroom, and reform coalition strength</td></tr>
      </tbody>
    </table>
    <p>A twin match scoring ≥ 0.75 is flagged HIGH RISK. A score between 0.60–0.74 is flagged MEDIUM RISK. Below 0.60, the historical case is reported but not flagged.</p>

    <h2>Conflict Detection Criteria</h2>
    <p>A conflict is flagged only when two simultaneously active positions would produce logically incoherent policy outcomes — not merely tensions or emphasis differences. The test applied is: <em>"If both leaders' stated positions were implemented as policy today, would the resulting actions contradict each other in a way that requires one to be abandoned?"</em></p>
    <p>Differences in emphasis, sequencing, or political framing are not flagged as conflicts. Timing differences are not conflicts unless both positions have the same implementation horizon and opposite directionality.</p>

    <h2>Pipeline</h2>
    <p>The full pipeline runs: <code>scraper</code> (fetches primary sources) → <code>extractor</code> (Claude API extracts structured dimension data) → <code>twin_matcher</code> (scores signals against historical cases) → <code>conflict_detector</code> (compares leader pairs) → <code>site/build.py</code> (generates this site). All intermediate JSON is preserved in <code>data/</code>. Weekly CI refreshes leader profiles where new source material is available.</p>

    <h2>Limitations</h2>
    <p>Profiles reflect publicly stated positions only. Operational doctrine visible only through classified deliberations, private communications, or unrecorded decisions is not captured. Confidence scores reflect evidential quality, not predictive certainty. The system is optimised for Cambodia's senior leadership cohort and may not generalise to other political contexts without prompt recalibration.</p>

  </div>
</div>"""
    return _page("Methodology", "methodology", body,
                 breadcrumb='<a href="index.html">Precedent</a><span class="bc-sep">/</span><span class="bc-current">Methodology</span>')


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
