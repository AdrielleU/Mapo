# CLAUDE.md - Mapo MVP

## Project Overview

Mapo MVP is a Google Maps business data scraper built on the Botasaurus framework. It extracts business listings, contact info, social media profiles, and reviews from Google Maps. Derived from [omkarcloud/google-maps-scraper](https://github.com/omkarcloud/google-maps-scraper) (commit `80569e9`), rewritten with a cleaner module structure.

## Quick Start

```bash
# Docker (recommended)
docker-compose up

# Local
pip install -r requirements.txt
python run.py
```

- Frontend UI: http://localhost:3000
- Backend API: http://localhost:8000
- Requires Google Chrome installed on host

## Architecture

```
run.py                              # Entry point — starts botasaurus_server
├── backend/
│   ├── server.py                   # Orchestration: registers scrapers, defines UI, task splitting
│   ├── scrapers/
│   │   ├── places.py               # Core engine: @browser scrolls Maps, @request fetches pages
│   │   ├── extract.py              # Parses APP_INITIALIZATION_STATE JSON from Google Maps HTML
│   │   ├── reviews.py              # GoogleMapsAPIScraper: hits internal review API (parallel=40)
│   │   ├── social.py               # RapidAPI social scraper for emails/phones/social links
│   │   ├── filters.py              # Result filtering and field ordering
│   │   └── time_utils.py           # Relative date parsing ("2 months ago" → datetime)
│   ├── inputs/
│   │   ├── google_maps_scraper.js  # UI form definition for the main scraper
│   │   └── website_contacts_scraper.js  # UI form for standalone website contacts
│   └── data/
│       ├── countries.py            # Country code → cities mapping (~240 countries)
│       └── categories.py           # ~1500 business category options for UI filters
├── Dockerfile                      # Based on chetan1111/botasaurus:latest
└── docker-compose.yaml             # Ports 3000 + 8000, shm_size 800m for Chrome
```

## Scraping Pipeline

1. User submits query via UI or API
2. `server.py:split_task_by_query()` splits into sub-tasks (per query, or per city if country mode)
3. `places.scrape_places()` — headless Chrome scrolls results feed, collects place links
4. `places.scrape_place()` — parallel HTTP requests (×5) fetch individual pages
5. `extract.extract_data()` — parses Google's `APP_INITIALIZATION_STATE` JSON blob
6. (Optional) `social.scrape_social()` — RapidAPI enrichment for emails/social
7. (Optional) `reviews.scrape_reviews()` — Google's internal review API (×40 parallel)
8. Results merged, deduped by `place_id`, displayed in UI with filters/sorts/export

## Key Design Patterns

- **Browser + HTTP hybrid**: Chrome discovers links by scrolling; HTTP workers (parallel=5) fetch pages
- **AsyncQueueResult**: Browser pushes links as discovered; HTTP workers consume concurrently
- **Botasaurus decorators**: `@browser`, `@request`, `@task` handle parallelism, caching, retry
- **Dynamic UI forms**: JS definitions in `inputs/` → auto-generated form fields via botasaurus-controls

## Commands

```bash
python run.py              # Start the server
python run.py install      # Build/install step (used in Docker)
```

## Tech Stack

- Python 3, Botasaurus (>=4.0.58), botasaurus-server (>=4.0.56)
- lxml, regex, dateutils, unidecode, requests
- Docker with Chrome (shm_size 800m required)
- External: RapidAPI Website Social Scraper (optional, for enrichment)
