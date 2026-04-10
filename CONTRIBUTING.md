# Contributing to Mapo

Thanks for your interest! Mapo is a self-hosted Google Maps lead generation platform — contributions of all sizes are welcome.

## Development Setup

```bash
git clone https://github.com/AdrielleU/mapo.git
cd mapo

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install both browser binaries (Patchright and Camoufox)
python -m playwright install firefox chromium

# Generate the static frontend data file (categories + states)
python scripts/generate_frontend_data.py
```

Run the server in development:

```bash
python run.py
```

- Web UI: http://localhost:8000
- API: http://localhost:8000/api/v1/
- Health check: http://localhost:8000/api/v1/health

Run a CLI command in dev:

```bash
python run.py scrape --query "Coffee shops in Austin" --max-results 5 -o test.csv
```

## Project Structure

```
run.py                          # Entry point: CLI dispatch or FastAPI server
├── frontend/                   # Vanilla HTML/CSS/JS (no build step)
│   ├── index.html              # SPA — Input/Output/Schedules/Settings tabs
│   ├── style.css               # Light + dark theme, WCAG AA compliant
│   └── data.js                 # Auto-generated: 4011 categories + 51 US states
├── backend/
│   ├── server.py               # FastAPI app, run_pipeline(), routes
│   ├── config.py               # Config dataclasses (yaml + env + UI settings)
│   ├── auth.py                 # Optional username/password + TOTP
│   ├── cli.py                  # CLI subcommands (scrape, enrich)
│   ├── scheduler.py            # APScheduler cron jobs
│   ├── webhooks.py             # Webhook delivery
│   ├── progress.py             # Job progress tracking
│   ├── proxy.py                # Proxy rotation manager
│   ├── cache.py                # Per-place response cache
│   ├── scrapers/
│   │   ├── places.py           # Browser launchers + HTTP fetching pipeline
│   │   ├── extract.py          # Parses Google's APP_INITIALIZATION_STATE / preview endpoint
│   │   ├── filters.py          # 8 filter criteria + cross-reference dedup helpers
│   │   ├── reviews.py          # Review API (parallel)
│   │   └── social.py           # Enrichment integration
│   ├── enrichment/             # Pluggable email/social providers
│   ├── detection/              # Tech stack, ad pixels, contact forms
│   ├── ai/
│   │   ├── lead_scoring.py     # AI lead scoring + email ranking
│   │   └── review_analysis.py  # Sentiment + themes
│   ├── outputs/                # CSV, JSON, Postgres, Sheets, S3 writers
│   ├── api/                    # REST API models + routes
│   └── data/                   # Static data (countries, states, categories)
├── scripts/
│   └── generate_frontend_data.py   # Generates frontend/data.js
├── mapo.yaml                   # Configuration defaults
├── docker-compose.yaml         # Docker deployment
└── Dockerfile                  # python:3.12-slim + Playwright Firefox + Chromium
```

## Key Architectural Patterns

### Configuration

3-layer config priority (highest wins):
1. **`data/settings.json`** — managed via Settings UI, hot-reloaded
2. **Environment variables** — `MAPO_*` prefix (see `.env.example`)
3. **`mapo.yaml`** — base defaults

To add a new config section:
1. Add a `@dataclass` in `backend/config.py` with a `from_dict()` classmethod
2. Add to `MapoConfig`, `load_config()`, `_apply_env_overrides()`, `_apply_ui_settings()`, and `reload_config()`
3. Existing examples: `ProxyConfig`, `ScrapingConfig`, `LimitsConfig`

### Pipeline (single source of truth)

All scrape jobs go through `run_pipeline()` in `backend/server.py` — including web UI requests, CLI commands, REST API calls, and scheduled cron jobs. This ensures features like filters, retries, AI scoring, cross-ref dedup, and webhooks work consistently everywhere.

The pipeline order:
1. Build query list (or expand country → cities)
2. Scroll Google Maps via stealth browser, collect place URLs
3. Parallel HTTP fetch each place, parse data
4. Apply server-side filters
5. CSV cross-reference dedup
6. Trim to `target_new` if set
7. Optional: enrichment, email scoring, reviews, AI lead scoring, AI email ranking
8. Order fields, save to job store
9. Auto-export to CSV/JSON, fire webhooks

### Browser backends

Two pluggable browsers in `backend/scrapers/places.py`:
- **`_launch_camoufox()`** — Camoufox (patched Firefox) via `AsyncCamoufox` context manager
- **`_launch_patchright()`** — Patchright (anti-detection Chromium) via `async_playwright`

Both implement the same interface: return `(page, context, _pw, _browser)`. Selected via `config.scraping.browser` ("camoufox" or "patchright").

### Frontend (no build step)

Pure HTML/CSS/JS — no React, no Vue, no bundler. Edit `frontend/index.html` directly. The static `frontend/data.js` is auto-generated from `backend/data/categories.py` and `backend/data/states.py` via `scripts/generate_frontend_data.py`.

To regenerate after changing data files:
```bash
python scripts/generate_frontend_data.py
```

## Making Changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Test locally:
   - `python -c "from backend.server import app; print('OK')"` (imports work)
   - Run a small scrape via CLI to verify the pipeline
   - Open the web UI and test interactively
4. Submit a pull request with a clear description

### Verification checklist

- [ ] Imports work: `python -c "from backend.server import app; print('OK')"`
- [ ] CLI runs: `python run.py scrape --query "test" --max-results 5 -o /tmp/test.csv`
- [ ] Web UI loads: `python run.py` then visit http://localhost:8000
- [ ] No new lazy imports inside hot-path functions (move to module level)
- [ ] If you added a new ScrapeRequest field, also add it to the CLI in `backend/cli.py`
- [ ] If you added a new config option, document it in `mapo.yaml`

## Code Style

- Python 3.12+ with type hints where practical
- Use `async`/`await` for I/O-bound operations
- **Avoid lazy imports inside hot-path functions** — they re-import on every call
- **Don't block the async event loop** with sync I/O — use `asyncio.to_thread()` if you must
- Follow existing patterns — look at how similar features are implemented before adding new ones
- No build tooling for the frontend — keep it vanilla HTML/CSS/JS
- No external runtime services required — Mapo is self-hosted, everything runs in one process

## Adding Features

### Adding a new ScrapeRequest field

1. Add the field to `ScrapeRequest` in `backend/server.py` with a default value
2. Wire it through to the scrape pipeline (`run_pipeline` → `scrape_places` if needed)
3. Add a CLI flag in `backend/cli.py` (`_build_parser` and `_cmd_scrape` params dict)
4. Add a UI form field in `frontend/index.html` and the JS submit body
5. Update the README example commands

### Adding a new server-side filter

1. Add the criterion to `filter_places()` in `backend/scrapers/filters.py`
2. Add the field to `ScrapeRequest` in `backend/server.py`
3. The pipeline already passes filter params through — no pipeline changes needed
4. Add a CLI flag and UI checkbox

### Adding an Enrichment Provider

1. Create a new file in `backend/enrichment/` (e.g., `clearbit.py`)
2. Implement the `EnrichmentProvider` ABC from `backend/enrichment/base.py`
3. Register it in `backend/enrichment/__init__.py`
4. Add to the provider dropdown in `frontend/index.html` Settings tab
5. Document in `mapo.yaml` and `.env.example`

### Adding an Output Target

1. Create a new writer in `backend/outputs/` following the existing pattern (csv_writer.py, postgres.py, etc.)
2. Add the target type to the configuration schema in `mapo.yaml`
3. Hook into `_auto_export()` in `backend/server.py` if it should fire automatically

### Adding a Detection Module

1. Create a new file in `backend/detection/`
2. Follow the pattern in `techstack.py` or `adpixels.py`
3. Hook into the scraping pipeline (called per-place after enrichment)
4. Add the new field name to `DETECTION_KEYS` in `backend/server.py`

### Adding an AI feature

1. Add the function to `backend/ai/lead_scoring.py` or `review_analysis.py`
2. Use the existing rate-limiting pattern (`_MIN_CALL_INTERVAL`, `_last_call_time`)
3. Use the shared LLM client via `from backend.ai import get_llm_client`
4. Hook into `run_pipeline()` in `backend/server.py`, conditional on `config.ai.enabled`
5. Skip the call when there's no useful input (e.g., no emails to rank)

## Reporting Issues

Open an issue on GitHub with:

- **What you expected to happen**
- **What actually happened** (full error message + stack trace if available)
- **Steps to reproduce** — exact CLI command or API request
- **Environment** — Python version, OS, Docker vs. native, browser backend (camoufox/patchright)
- **Are you on a residential IP, datacenter VPS, or proxy?** — Google returns different responses to different IP types

For scraping issues specifically, also include:
- The query you're running
- Whether the issue happens for all queries or specific ones
- Output of `python -m pip show camoufox patchright playwright`

## Common Gotchas

- **Camoufox needs `libgtk-3.so.0`** on Linux — install with `apt install libgtk-3-0` (Debian/Ubuntu) or `dnf install gtk3` (RHEL/Fedora). Alternatively, use Patchright (Chromium) which doesn't need GTK.
- **Datacenter IPs get different responses** from Google — fields may be incomplete on cloud servers. Use a residential proxy or VPN for full data.
- **Don't have both `camoufox` and `cloverlabs-camoufox` installed** — they overwrite the same module directory. Pick one.
- **APScheduler runs in a background thread** — when adding scheduled jobs, the pipeline runs in a fresh asyncio loop via `asyncio.run()`. Don't try to share the FastAPI event loop.
- **Frontend `data.js` is auto-generated** — don't edit it directly. Edit the source data files in `backend/data/` and regenerate.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
