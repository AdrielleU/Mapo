# CLAUDE.md — Mapo

## Project Overview

Mapo is a Google Maps business data scraper with enrichment, detection, AI analysis, and multi-target output. Built on the Botasaurus framework. Supports web UI, REST API, CLI, webhooks, and cron scheduling.

Derived from [omkarcloud/google-maps-scraper](https://github.com/omkarcloud/google-maps-scraper), rebuilt with a modular architecture.

## Quick Start

```bash
# Set up venv
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run web UI + API server
python run.py

# Or use Docker
docker-compose up
```

- Frontend UI: http://localhost:3000
- Backend API: http://localhost:8000
- REST API: http://localhost:8000/api/v1/health
- Requires Google Chrome on host (for browser-based scraping)

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
run.py                              # Entry point: CLI dispatch or server start
├── backend/
│   ├── config.py                   # Central config (mapo.yaml + env vars)
│   ├── proxy.py                    # Proxy rotation manager (HTTP/HTTPS/SOCKS5)
│   ├── webhooks.py                 # Webhook delivery with Slack support
│   ├── scheduler.py                # APScheduler cron jobs
│   ├── cli.py                      # CLI interface (scrape/enrich subcommands)
│   ├── server.py                   # Botasaurus server registration + orchestration
│   ├── scrapers/
│   │   ├── places.py               # Browser+HTTP hybrid scraper with anti-detection
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
│   │   ├── routes.py               # /scrape, /jobs, /enrich, /health
│   │   └── models.py               # Request validation
│   ├── inputs/                     # UI form definitions (JS)
│   └── data/                       # Country/category static data
├── mapo.yaml                       # Configuration file
├── .env.example                    # Environment variable template
├── Dockerfile                      # Docker image with healthcheck
└── docker-compose.yaml             # Ports 3000+8000, optional PostgreSQL
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
POST /api/v1/scrape      — start scrape job
GET  /api/v1/jobs         — list all jobs
GET  /api/v1/jobs/{id}    — job status + results
DELETE /api/v1/jobs/{id}  — cancel/delete job
POST /api/v1/enrich       — standalone enrichment
GET  /api/v1/health       — health check
```

## Scraping Pipeline

1. Query submitted (UI / API / CLI / scheduler)
2. `server.py` splits into sub-tasks (per query or per city)
3. `places.scrape_places()` — headless Chrome scrolls results with anti-detection
4. `places.scrape_place()` — parallel HTTP (×5) fetches individual pages
5. `extract.extract_data()` — parses Google's APP_INITIALIZATION_STATE
6. (Optional) `enrichment` — pluggable provider for emails/social
7. (Optional) `detection` — tech stack, ad pixels, contact forms
8. (Optional) `reviews` — Google's internal review API (×40 parallel)
9. (Optional) `ai` — LLM lead scoring + review analysis
10. Results deduped, filtered, written to configured outputs, webhook fired

## Anti-Detection

- Proxy rotation (HTTP/HTTPS/SOCKS5) with geo-matching
- Hardened selectors (aria-label/role-based, text-content fallbacks)
- Behavioral mimicry (randomized delays, jittered timeouts)
- User-agent rotation (12+ current Chrome UAs)
- httpx with HTTP/2 (defeats TLS fingerprinting)

## Tech Stack

- Python 3.12+, Botasaurus >=4.0.97, botasaurus-server >=4.0.61
- httpx (HTTP/2), lxml, regex, APScheduler, rich
- Optional: psycopg2, gspread, boto3, anthropic, openai
