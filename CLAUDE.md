# CLAUDE.md — Mapo

## Project Overview

Mapo is a Google Maps business data scraper with enrichment, detection, AI analysis, and multi-target output. Built on FastAPI with dual browser backends (Camoufox Firefox + Patchright Chromium) for stealth automation and asyncio for concurrency. Supports web UI, REST API, CLI, webhooks, and cron scheduling.

Derived from [omkarcloud/google-maps-scraper](https://github.com/omkarcloud/google-maps-scraper), rebuilt with a modular architecture.

## Quick Start

```bash
# Set up venv
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m playwright install firefox chromium

# Run web UI + API server (single port)
python run.py

# Or use Docker
docker-compose up
```

- Web UI + API: http://localhost:8000
- Health check: http://localhost:8000/api/v1/health
- Frontend served as static files from `frontend/`

## CLI Usage

```bash
# Scrape from command line
python run.py scrape --query "restaurants in NYC" --max-results 100 --output results.csv

# Country-wide scrape
python run.py scrape --country US --business-type "dentist" --output dentists.json

# Enrich existing data
python run.py enrich --input places.csv --provider hunter --output enriched.csv
```

## Architecture

```
run.py                              # Entry point: CLI dispatch or FastAPI server
├── frontend/
│   ├── index.html                  # Single-page web UI (no build step)
│   └── style.css                   # Dark theme styles
├── backend/
│   ├── config.py                   # Central config (mapo.yaml + env vars)
│   ├── proxy.py                    # Proxy rotation manager (HTTP/HTTPS/SOCKS5)
│   ├── webhooks.py                 # Webhook delivery with Slack support
│   ├── scheduler.py                # APScheduler cron jobs
│   ├── cli.py                      # CLI interface (scrape/enrich subcommands)
│   ├── server.py                   # FastAPI app, WebSocket progress, job mgmt
│   ├── scrapers/
│   │   ├── places.py               # Stealth browser + HTTP hybrid scraper (Camoufox/Patchright)
│   │   ├── extract.py              # Parses APP_INITIALIZATION_STATE JSON
│   │   ├── reviews.py              # Google Maps internal review API (parallel=40)
│   │   ├── social.py               # Pluggable enrichment integration
│   │   ├── filters.py              # Result filtering and field ordering
│   │   └── time_utils.py           # Relative date parsing
│   ├── enrichment/                 # Pluggable enrichment providers
│   │   ├── base.py                 # EnrichmentProvider ABC
│   │   ├── rapidapi.py             # RapidAPI Website Social Scraper
│   │   ├── hunter.py               # Hunter.io email enrichment
│   │   └── apollo.py               # Apollo.io company enrichment
│   ├── detection/                  # Website analysis
│   │   ├── techstack.py            # WordPress, Shopify, React, etc.
│   │   ├── adpixels.py             # Facebook Pixel, Google Ads, etc.
│   │   └── contactform.py          # Contact form + provider detection
│   ├── outputs/                    # Multi-target output writers
│   │   ├── csv_writer.py, json_writer.py
│   │   ├── postgres.py             # PostgreSQL (upsert by place_id)
│   │   ├── sheets.py               # Google Sheets
│   │   └── s3.py                   # AWS S3
│   ├── ai/                         # LLM-powered features
│   │   ├── lead_scoring.py         # Lead score + pitch summary
│   │   └── review_analysis.py      # Sentiment + themes
│   ├── api/                        # REST API (v1)
│   │   ├── routes.py               # /scrape, /jobs, /enrich, /health, /states
│   │   └── models.py               # Request validation
│   ├── inputs/                     # UI form definitions
│   └── data/                       # Country/category/state static data
│       ├── countries.py            # Country → city mappings
│       ├── categories.py           # Google Maps category options
│       └── states.py               # US state → city mappings
├── mapo.yaml                       # Configuration file
├── .env.example                    # Environment variable template
├── Dockerfile                      # python:3.12-slim + Playwright Firefox
└── docker-compose.yaml             # Single port 8000, volumes for data/ + config
```

## Configuration

Settings in `mapo.yaml` with env var overrides (see `.env.example`):

- **Proxy**: rotation strategy (round-robin/random/geo-match), HTTP/HTTPS/SOCKS5
- **Enrichment**: provider selection (rapidapi/hunter/apollo) + API key
- **Webhooks**: URLs for task.completed/task.failed notifications (Slack support)
- **Scheduler**: cron jobs with output targets
- **Outputs**: CSV, JSON, PostgreSQL, Google Sheets, S3
- **AI**: Claude or OpenAI for lead scoring + review analysis

## REST API

```
POST /api/v1/scrape          — start scrape job
GET  /api/v1/jobs             — list all jobs
GET  /api/v1/jobs/{id}        — job status + results
GET  /api/v1/jobs/{id}/download?format=csv — download results
DELETE /api/v1/jobs/{id}      — cancel/delete job
POST /api/v1/enrich           — standalone enrichment
GET  /api/v1/states?country=US — list states for country
GET  /api/v1/health           — health check
WS   /api/v1/ws/{job_id}     — real-time progress updates
```

## Scraping Pipeline

1. Query submitted (UI / API / CLI / scheduler)
2. Server splits into sub-tasks (per query or per city via state data)
3. `places.scrape_places()` — stealth browser (Camoufox or Patchright) scrolls results
4. `places.scrape_place()` — parallel HTTP (x5) fetches individual pages
5. `extract.extract_data()` — parses Google's APP_INITIALIZATION_STATE
6. (Optional) `enrichment` — pluggable provider for emails/social
7. (Optional) `detection` — tech stack, ad pixels, contact forms
8. (Optional) `reviews` — Google's internal review API (x40 parallel)
9. (Optional) `ai` — LLM lead scoring + review analysis
10. Results deduped, filtered, written to configured outputs, webhook fired

## Anti-Detection

- Camoufox (patched Firefox) for undetectable browser fingerprints
- Proxy rotation (HTTP/HTTPS/SOCKS5) with geo-matching
- Hardened selectors (aria-label/role-based, text-content fallbacks)
- Behavioral mimicry (randomized delays, jittered timeouts)
- User-agent rotation (12+ current browser UAs)
- httpx with HTTP/2 (defeats TLS fingerprinting)

## Tech Stack

- Python 3.12+, FastAPI, uvicorn, Pydantic
- Camoufox (stealth Firefox) + Patchright (stealth Chromium) via Playwright
- httpx (HTTP/2), lxml, regex, APScheduler, rich
- asyncio throughout, WebSocket for real-time progress
- Frontend: vanilla HTML/CSS/JS (no build step, no Node.js)
- Optional: psycopg2, gspread, boto3, anthropic, openai
