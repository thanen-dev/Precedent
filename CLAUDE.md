# Precedent 

## Purpose
Political intelligence system mapping the mental models of Cambodia’s top 10 decision‑makers.  
Extracts doctrine from speeches/policy docs, links to historical “twin” cases, and flags internal government conflicts.

## Core outputs
- 7‑field mental model JSON profile per leader (with quotes, URL, date, confidence).
- Historical twin matches for major policy moves.
- Simple static site showing leader profiles, twins, and conflicts.

## Stack
- Python 3.13
- Claude API (Sonnet) for extraction / twin matching
- `requests`, `BeautifulSoup` for scraping
- `pdfplumber` for PDFs
- JSON files (v1 storage)
- GitHub Pages for static HTML

## Project structure
/data/leaders/       # JSON profiles per leader  
/data/historical/    # Historical twin cases  
/data/raw/           # Raw scraped documents (text + metadata)  
/scraper/            # Scraping + PDF ingestion  
/extractor/          # Claude API prompts + merge/update logic  
/site/               # Static HTML/CSS + build scripts  

## Ground rules
- Start with data, not interface.
- Every JSON field must have source URL + date + exact quote.
- No invention: if unsourced, keep the field empty.
- v1 target: 4 leaders, 10 historical cases, static site live on GitHub Pages.
- Weekly cadence; accuracy beats freshness.
