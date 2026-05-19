#!/usr/bin/env python3
"""
Scraper — Khmer Times RSS + article fetcher.
Fetches recent articles mentioning tracked leaders, saves raw JSON to data/raw/<leader_id>/.

Usage:
    python scraper/fetch_khmer_times.py
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S", level=logging.INFO)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR      = PROJECT_ROOT / "data" / "raw"

RSS_URL = "https://www.khmertimeskh.com/feed/"
TIMEOUT = 20
DELAY   = 1.5

# Maps search terms → leader_id
LEADER_TERMS: dict[str, str] = {
    "hun manet":         "hun_manet",
    "hun sen":           "hun_sen",
    "aun pornmoniroth":  "aun_pornmoniroth",
    "cham nimul":        "cham_nimul",
    "chea serey":        "chea_serey",
    "chea vandeth":      "chea_vandeth",
    "hang chuon naron":  "hang_chuon_naron",
    "hem vanndy":        "hem_vanndy",
    "say sam al":        "say_sam_al",
    "sok siphana":       "sok_siphana",
    "sun chanthol":      "sun_chanthol",
}


def _slug(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:10]


def _parse_date(date_str: str) -> str:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return datetime.utcnow().strftime("%Y-%m-%d")


def _fetch_article_text(url: str) -> str:
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "PrecedentBot/1.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Khmer Times article body
        article = soup.find("div", class_=re.compile(r"entry-content|article-content|post-content"))
        if article:
            return article.get_text(" ", strip=True)
        # fallback: all <p> tags
        return " ".join(p.get_text(strip=True) for p in soup.find_all("p"))
    except Exception as exc:
        log.warning("Failed to fetch article %s: %s", url, exc)
        return ""


def _save(leader_id: str, url: str, date: str, title: str, text: str) -> Path | None:
    out_dir = RAW_DIR / leader_id
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{date}_khtimes_{_slug(url)}"
    out  = out_dir / f"{stem}.json"
    if out.exists():
        log.debug("Skip — already scraped: %s", out.name)
        return None
    payload = {"url": url, "date": date, "title": title, "text": text, "source": "khmer_times"}
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    log.info("Saved: %s", out)
    return out


def run() -> list[Path]:
    log.info("Fetching Khmer Times RSS: %s", RSS_URL)
    try:
        r = requests.get(RSS_URL, timeout=TIMEOUT, headers={"User-Agent": "PrecedentBot/1.0"})
        r.raise_for_status()
    except Exception as exc:
        log.error("RSS fetch failed: %s", exc)
        return []

    soup = BeautifulSoup(r.text, "xml")
    items = soup.find_all("item")
    log.info("Found %d RSS items", len(items))

    saved: list[Path] = []

    for item in items:
        title_tag = item.find("title")
        link_tag  = item.find("link")
        date_tag  = item.find("pubDate")
        desc_tag  = item.find("description")

        if not (title_tag and link_tag):
            continue

        title   = title_tag.get_text(strip=True)
        url     = link_tag.get_text(strip=True)
        date    = _parse_date(date_tag.get_text()) if date_tag else datetime.utcnow().strftime("%Y-%m-%d")
        summary = BeautifulSoup(desc_tag.get_text(), "html.parser").get_text(" ", strip=True) if desc_tag else ""
        combined = (title + " " + summary).lower()

        for term, leader_id in LEADER_TERMS.items():
            if term in combined:
                time.sleep(DELAY)
                text = _fetch_article_text(url)
                if len(text) < 100:
                    text = summary
                if text:
                    p = _save(leader_id, url, date, title, text)
                    if p:
                        saved.append(p)
                break

    log.info("Khmer Times: saved %d new documents", len(saved))
    return saved


if __name__ == "__main__":
    run()
