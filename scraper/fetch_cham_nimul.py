#!/usr/bin/env python3
"""
Fetch Cham Nimul trade policy statements from primary sources.

Writes one JSON envelope per document to data/raw/cham_nimul/:
    { leader_id, url, date, title, text }

Sources: moc.gov.kh (Ministry of Commerce), WTO trade policy reviews,
ASEAN trade ministerial statements, Khmer Times.
Supports HTML and PDF. PDFs detected by magic bytes (%PDF).

Usage
-----
    python scraper/fetch_cham_nimul.py             # fetch all, skip existing
    python scraper/fetch_cham_nimul.py --dry-run   # print what would be written
    python scraper/fetch_cham_nimul.py --force      # re-fetch and overwrite
    python scraper/fetch_cham_nimul.py --list       # print sources and exit
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlparse

import pdfplumber
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "cham_nimul"
LEADER_ID = "cham_nimul"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PrecedentResearchBot/1.0)",
    "Accept-Language": "en",
    "Accept": "text/html,application/xhtml+xml,application/pdf",
}
TIMEOUT = 30    # seconds — WTO PDFs can be large
DELAY   = 2.0   # polite pause between requests


# ── source list ───────────────────────────────────────────────────────────────

class Source(TypedDict):
    url: str
    date_hint: str          # ISO-8601 fallback; used if page date not parseable
    title_hint: str         # fallback if title not extractable from document
    tier: Literal["primary", "secondary"]


SOURCES: list[Source] = [
    # ── Primary: moc.gov.kh — official Ministry of Commerce ──────────────────

    # Cham Nimul — Cambodia trade policy statement at ASEAN Economic Ministers
    {
        "url": "https://www.moc.gov.kh/en/news-and-events/news/1692",
        "date_hint": "2024-08-19",
        "title_hint": "Statement at the 56th ASEAN Economic Ministers Meeting",
        "tier": "primary",
    },
    # MOC press release — RCEP implementation progress 2024
    {
        "url": "https://www.moc.gov.kh/en/news-and-events/news/1540",
        "date_hint": "2024-03-15",
        "title_hint": "RCEP Implementation Progress and Cambodia's Trade Outlook",
        "tier": "primary",
    },
    # Cham Nimul — remarks at Cambodia Trade Forum 2023
    {
        "url": "https://www.moc.gov.kh/en/news-and-events/news/1421",
        "date_hint": "2023-11-08",
        "title_hint": "Opening Remarks at the Cambodia Trade Forum 2023",
        "tier": "primary",
    },

    # ── Primary: WTO — Cambodia trade policy reviews ──────────────────────────

    # WTO Trade Policy Review Cambodia 2021 — full report PDF
    {
        "url": "https://docs.wto.org/dol2fe/Pages/SS/directdoc.aspx?filename=q:/WT/TPR/S476.pdf&Open=True",
        "date_hint": "2021-11-03",
        "title_hint": "WTO Trade Policy Review Cambodia 2021 — Secretariat Report",
        "tier": "primary",
    },
    # Cambodia's own WTO Trade Policy Review statement 2021
    {
        "url": "https://docs.wto.org/dol2fe/Pages/SS/directdoc.aspx?filename=q:/WT/TPR/G476.pdf&Open=True",
        "date_hint": "2021-11-03",
        "title_hint": "WTO Trade Policy Review Cambodia 2021 — Government Statement",
        "tier": "primary",
    },

    # ── Secondary: analysis and reporting ────────────────────────────────────

    # Khmer Times — Cambodia garment export targets and trade diversification
    {
        "url": "https://www.khmertimeskh.com/501365240/cambodia-targets-20-billion-in-exports-by-2028-commerce-minister/",
        "date_hint": "2023-08-24",
        "title_hint": "Cambodia targets $20bn in exports by 2028 — Commerce Minister",
        "tier": "secondary",
    },
    # UNCTAD Cambodia trade and investment brief 2024
    {
        "url": "https://unctad.org/system/files/official-document/ditcinf2024d4_en.pdf",
        "date_hint": "2024-06-01",
        "title_hint": "UNCTAD Cambodia Trade and Investment Brief 2024",
        "tier": "secondary",
    },
]


# ── HTTP fetch ────────────────────────────────────────────────────────────────

def _fetch_raw(url: str) -> requests.Response | None:
    """Return a Response or None on any network/HTTP error."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp
    except requests.HTTPError as exc:
        log.warning("HTTP %s — %s", exc.response.status_code, url)
    except requests.RequestException as exc:
        log.warning("Request failed (%s) — %s", type(exc).__name__, url)
    return None


def _is_pdf(response: requests.Response) -> bool:
    """Detect PDF by magic bytes — more reliable than Content-Type."""
    return response.content[:4] == b"%PDF"


# ── per-domain parsers ────────────────────────────────────────────────────────

def _clean(element: BeautifulSoup) -> str:
    """Strip boilerplate tags and return normalised plain text."""
    for tag in element.find_all(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    lines = [ln.strip() for ln in element.get_text(separator="\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _parse_pdf(content: bytes, source: Source) -> tuple[str, str, str]:
    """Extract all text from a PDF. Date/title always come from hints."""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(pages).strip()
    except Exception as exc:
        log.warning("PDF parse failed (%s): %s", type(exc).__name__, exc)
        text = ""
    return source["title_hint"], source["date_hint"], text


def _parse_moc(soup: BeautifulSoup, source: Source) -> tuple[str, str, str]:
    """
    Parse moc.gov.kh news pages.
    MOC uses a CMS with common heading + article body structure.
    """
    title_el = (
        soup.find("h1", class_="title")
        or soup.find("h1", class_="page-title")
        or soup.find("h1")
    )
    title = title_el.get_text(strip=True) if title_el else source["title_hint"]

    date = ""
    date_el = (
        soup.find("span", class_="date")
        or soup.find("span", class_="post-date")
        or soup.find("time")
    )
    if date_el:
        raw = date_el.get("datetime") or date_el.get_text(strip=True)
        m = re.search(r"\d{4}-\d{2}-\d{2}", raw or "")
        if m:
            date = m.group()

    content_el = (
        soup.find("div", class_="content")
        or soup.find("div", class_="field-items")
        or soup.find("div", class_="entry-content")
        or soup.find("article")
    )
    text = _clean(content_el) if content_el else _clean(soup.body or soup)
    return title, date, text


def _parse_generic(soup: BeautifulSoup, source: Source) -> tuple[str, str, str]:
    """Fallback parser: meta tags → h1 → body."""
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else source["title_hint"]

    date = ""
    for prop in ("article:published_time", "og:article:published_time"):
        meta = soup.find("meta", property=prop)
        if meta and meta.get("content"):
            date = meta["content"][:10]
            break
    if not date:
        time_el = soup.find("time")
        if time_el:
            date = time_el.get("datetime", "")[:10]

    body = soup.find("main") or soup.find("article") or soup.body or soup
    text = _clean(body)
    return title, date, text


# ── envelope assembly ─────────────────────────────────────────────────────────

def parse_envelope(response: requests.Response, source: Source) -> dict:
    """Route response through the correct parser and return a raw envelope."""
    if _is_pdf(response):
        title, date, text = _parse_pdf(response.content, source)
    else:
        soup = BeautifulSoup(response.text, "html.parser")
        domain = urlparse(source["url"]).netloc
        if domain in ("www.moc.gov.kh", "moc.gov.kh"):
            title, date, text = _parse_moc(soup, source)
        else:
            title, date, text = _parse_generic(soup, source)

    return {
        "leader_id": LEADER_ID,
        "url":   source["url"],
        "date":  date.strip()  or source["date_hint"],
        "title": title.strip() or source["title_hint"],
        "text":  text,
    }


# ── file I/O ──────────────────────────────────────────────────────────────────

def _slug(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:max_len]


def envelope_path(envelope: dict) -> Path:
    return OUTPUT_DIR / f"{envelope['date']}_{_slug(envelope['title'])}.json"


def save_envelope(envelope: dict, path: Path) -> None:
    path.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Saved  %s", path.relative_to(PROJECT_ROOT))


# ── orchestration ─────────────────────────────────────────────────────────────

def run(
    sources: list[Source],
    force: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for i, source in enumerate(sources):
        url = source["url"]
        log.info("[%d/%d] %s", i + 1, len(sources), url)

        response = _fetch_raw(url)
        if response is None:
            if i < len(sources) - 1:
                time.sleep(DELAY)
            continue

        envelope = parse_envelope(response, source)

        if not envelope["text"].strip():
            log.warning("Skipping — empty text body: %s", url)
            if i < len(sources) - 1:
                time.sleep(DELAY)
            continue

        path = envelope_path(envelope)

        if path.exists() and not force:
            log.info("Skip   %s (exists; use --force to overwrite)", path.name)
            if i < len(sources) - 1:
                time.sleep(DELAY)
            continue

        if dry_run:
            log.info(
                "DRY-RUN  [%s] would write → %s",
                source["tier"],
                path.relative_to(PROJECT_ROOT),
            )
        else:
            save_envelope(envelope, path)
            written.append(path)

        if i < len(sources) - 1:
            time.sleep(DELAY)

    return written


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Cham Nimul trade policy statements from primary sources."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be written without fetching")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing output files")
    parser.add_argument("--list", dest="list_only", action="store_true",
                        help="Print configured sources and exit")
    args = parser.parse_args()

    if args.list_only:
        for s in SOURCES:
            print(f"[{s['tier']:<9}]  {s['date_hint']}  {s['url']}")
        sys.exit(0)

    written = run(SOURCES, force=args.force, dry_run=args.dry_run)
    if not args.dry_run:
        log.info("Done. %d file(s) written.", len(written))


if __name__ == "__main__":
    main()
