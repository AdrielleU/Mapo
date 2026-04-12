# Mapo

**Self-hosted, open-source Google Maps lead generation platform.**

Scrape Google Maps business data, enrich with contacts, score with AI, deduplicate against existing leads, and deliver to CSV / JSON / Excel / PostgreSQL / webhooks. One-click via web UI, scriptable via CLI, automatable via REST API + cron schedules.

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED)
[![GHCR](https://img.shields.io/badge/ghcr.io-adrielleu%2Fmapo-blue?logo=docker)](https://github.com/AdrielleU/Mapo/pkgs/container/mapo)

---

## What you get

### Scraping
- **Dual stealth browsers** — Camoufox (Firefox) + Patchright (Chromium, ARM-native). Switch in one click.
- **80+ data fields per business** — name, contacts, hours, address, coordinates, photos, reviews, owner info, attributes, business status
- **244 countries, 51 US states with cities, 4,011 business categories** — built in, no API needed
- **Country/state expansion** — auto-generates per-city queries with randomization
- **Geo + radius search** — coordinates + meters (auto-converts to map zoom)
- **Multi-strategy parser** — handles Google's lazy-loaded data with 3 fallback paths so you always get *something*
- **Configurable everything** — concurrency, delays, scroll timeout, headless/debug mode

### Filters & quality control
- **Server-side filters** — skip closed places, min/max rating, min reviews, has website, has phone, category match, price range. Applied **before** enrichment so you don't waste API credits.
- **CSV cross-reference dedup** — upload existing leads, Mapo skips places you already have. Match by `place_id`, name, phone, website, or email.
- **Top-up mode** — set "I want 100 NEW places," Mapo scrapes extra to compensate for duplicates and returns exactly 100 new ones.
- **Auto-retry with backoff** — 3 attempts, configurable delay, partial results preserved across retries.

### Enrichment & detection
- **Email + social extraction** via Hunter.io, Apollo.io, or RapidAPI
- **Email quality scoring** — classifies emails as executive (9/10), personal (8/10), generic (2/10), free provider, etc.
- **Website detection** — tech stack (100+ platforms: WordPress, Shopify, React...), ad pixels (Meta, Google, TikTok), contact forms

### AI features
- **Lead scoring** — score every place against your Ideal Customer Profile (1-10) with personalized pitch summaries and suggested approach (cold call, email, LinkedIn, in-person)
- **AI email prioritization** — when a place has multiple emails, the LLM ranks them by domain match, decision-maker indicators, and ICP fit
- **Review sentiment analysis** — extract themes and sentiment from scraped reviews
- **Multi-provider** — works with Claude, GPT-4, Gemini, or self-hosted vLLM

### Three ways to use it
- **Web UI** — light/dark themed SPA, 4 tabs (Input / Output / Schedules / Settings), real-time SSE progress, sortable/filterable results table with pagination
- **CLI** — full pipeline from the command line, all features as flags
- **REST API** — full job management, SSE progress streams, JSON in / JSON out

### Automation
- **Cron schedules** — recurring jobs managed from the Schedules tab. Hot-reload, no restart. Each schedule uses the same full pipeline.
- **Webhooks** — separate completion + error webhooks. Full results delivered as JSON. Works with Slack, Discord, n8n, Make, Zapier, Pushover, ntfy, or any URL.
- **Settings UI** — configure proxy, enrichment, AI, scraping tuning, webhooks, limits from the browser. Saved to `data/settings.json`, hot-reloaded.

### Safeguards
- **Hard limits** — max results per query, max cities, max total places, max concurrent jobs, max runtime. Enforced server-side.
- **Pre-flight warnings** — UI confirms before submitting jobs over your warning threshold
- **Auto-cancel** — runaway jobs killed after configured runtime limit
- **Recommended Presets** — one-click Conservative / Balanced / Aggressive / Lead-gen settings

### Deployment
- **Docker Compose** — one command to start everything
- **Self-hosted** — runs anywhere (laptop, VPS, home server). No external services required.
- **VPN-aware** — works with NordVPN/Mullvad at OS level, including Docker Desktop on Windows 11 (mirrored networking) and macOS
- **Caddy + auto SSL** — point a domain at your VPS, get Let's Encrypt SSL automatically
- **Authentication** — optional username + password + TOTP (Google Authenticator/Authy) via env vars. Same credentials across multiple instances.

### Outputs
- **Files** — CSV, JSON, Excel (XLSX)
- **Databases** — PostgreSQL (upsert by place_id)
- **Cloud** — Google Sheets, AWS S3
- **HTTP** — webhooks with full result data

---

## Mapo + AI / Enrichment Tools (downstream pipelines)

Mapo is designed to work as the **scraping and filtering layer** in a larger lead-gen pipeline. Built-in AI features are optional — you can also export clean lead data to specialized tools that handle enrichment, social discovery, and personalization at scale.

### How it works

```
Mapo scrapes Google Maps  →  Auto-forwards to enrichment/AI tool  →  CRM / Outreach
        (raw leads)              (emails, social, AI scoring)         (HubSpot, Apollo, etc.)
```

You have **two ways to forward** the data:

#### 1. Webhook auto-forwarding (real-time)

Every scrape can fire its full results to a webhook URL. The webhook payload includes up to 500 leads as JSON, plus download links for the full set:

```bash
python run.py scrape --query "Coffee shops in Austin" --max-results 100 \
  --preset minimal \
  --webhook-url "https://your-n8n.com/webhook/abc"
```

n8n / Make / Zapier receives the data → routes it to:
- **Clay.com** for waterfall enrichment (150+ data providers)
- **Apollo.io** to find verified emails + LinkedIn profiles
- **Hunter.io** for email discovery
- **OpenAI / Claude / Gemini** for personalized outreach drafts
- **PhantomBuster** for LinkedIn scraping
- **Snov.io / FindThatLead** for additional contact data

#### 2. Export presets (batch upload)

Use a built-in export preset that matches the format your downstream tool expects:

| Preset | Tool | What it includes |
|---|---|---|
| `--preset clay` | **Clay.com** | name, website, address, phone, category, rating + structured location |
| `--preset apollo` | **Apollo.io** | name, website, address, phone, category (Apollo enriches the rest) |
| `--preset instantly` | **Instantly.ai** | name, email, company, phone for cold email campaigns |
| `--preset hubspot` | **HubSpot CRM** | Companies object fields (camelCase mapping in n8n) |
| `--preset n8n` | **n8n / Make / Zapier** | Comprehensive 15-field payload |
| `--preset minimal` | **Anything** | name, address, phone, website, rating, reviews |
| `--preset leads` | **Sales tools** | Contact + signals (owner, ads, claimable, best_email) |
| `--preset geo` | **Mapping tools** | name, category, coordinates, address only |

```bash
# Export to a Clay-friendly format
python run.py scrape --country US --state California --business-type "dentist" \
  --max-cities 30 --skip-closed --has-website \
  --preset clay -o ca_dentists_for_clay.csv

# Then upload ca_dentists_for_clay.csv to Clay → Clay enriches with:
#   - Verified emails (waterfall through Hunter, Apollo, etc.)
#   - LinkedIn profiles
#   - Decision-maker names
#   - Social media handles
#   - Tech stack
#   - AI-generated personalized intros
```

### What downstream tools find that Mapo doesn't

Mapo handles the **scraping** layer well — Google Maps data, basic enrichment via Hunter/Apollo/RapidAPI, optional AI lead scoring. But specialized tools do enrichment **better** because they aggregate hundreds of data sources:

| Data Mapo provides | Data downstream tools add |
|---|---|
| Business name, address, phone, website | LinkedIn profile of the owner |
| Google rating, reviews | Decision-maker name + title + email |
| Categories, hours, photos | Verified email (waterfall validation) |
| Best email (if found on website) | Twitter/X handle, Instagram, TikTok |
| Tech stack (basic detection) | Funding rounds, employee count, growth signals |
| AI lead score (Mapo's LLM) | Intent data, buyer signals |

**Practical recommendation:** Use Mapo for fast, cheap, high-volume scraping of business listings. Use a downstream tool (Clay, Apollo, etc.) for the expensive, specialized enrichment + personalization layer. Mapo's webhook + export presets make this handoff seamless.

### Example: full pipeline

```
Scheduled in Mapo (Schedules tab)
    ↓ Daily 8am
Mapo scrapes "Dentists in California" with cross-ref dedup (only NEW places)
    ↓ Webhook
n8n receives 50 new leads as JSON
    ↓ Clay node
Clay enriches: emails, LinkedIn, owner name, employee count
    ↓ OpenAI node
GPT-4 writes personalized first-line for each lead
    ↓ HubSpot node
Creates contact + company in HubSpot
    ↓ Instantly node
Adds to today's cold email campaign
    ↓ Slack notification
"50 new dentists added to today's outreach campaign"
```

Mapo handles the first step. Everything else is your existing tool stack.

---

## Quick Start

### Option A: Run the pre-built image (fastest, no clone needed)

```bash
docker run -d --name mapo -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  ghcr.io/adrielleu/mapo:latest
```

Open **http://localhost:8000**. That's it.

**Pin to a specific version** for production:

```bash
docker run -d --name mapo -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  ghcr.io/adrielleu/mapo:v1.1.0
```

Available tags: `latest`, `v1.1.0`, `1.1`, `1`, plus per-commit SHA tags. Browse them at the [GHCR package page](https://github.com/AdrielleU/Mapo/pkgs/container/mapo).

**With env vars** (auth, AI, enrichment, etc.):

```bash
docker run -d --name mapo -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  ghcr.io/adrielleu/mapo:v1.1.0
```

**Upgrade later:**

```bash
docker pull ghcr.io/adrielleu/mapo:latest
docker stop mapo && docker rm mapo
# re-run the docker run command above
```

**Rollback to a known-good version** — just change the tag and re-run. Your `./data` volume is preserved.

---

### Option B: Build from source

For development, customization, or building your own image. Same end result as Option A.

### 1. Clone and configure

```bash
git clone https://github.com/AdrielleU/mapo.git
cd mapo
cp .env.example .env
```

Edit `.env` with your settings (all optional — Mapo works without them):

```bash
# Authentication (optional — leave empty to disable login)
# MAPO_USERNAME=admin
# MAPO_PASSWORD=changeme
# MAPO_TOTP_SECRET=JBSWY3DPEHPK3PXP

# Enrichment (emails + social links)
# MAPO_ENRICHMENT_PROVIDER=rapidapi
# MAPO_ENRICHMENT_API_KEY=your-key

# AI lead scoring
# MAPO_AI_PROVIDER=anthropic
# MAPO_AI_API_KEY=sk-ant-...

# Proxies (recommended for large scrapes)
# MAPO_PROXY_URLS=http://user:pass@proxy1:8080,socks5://user:pass@proxy2:1080

# Webhooks
# MAPO_WEBHOOK_URLS=https://hooks.slack.com/services/XXX/YYY/ZZZ
```

### 2. Run

Pick your platform:

#### Linux / Linux VPS

```bash
docker compose up -d
```

Open **http://localhost:8000** (or `http://your-vps-ip:8000`).

#### Windows 11 (Docker Desktop)

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Enable WSL2 mirrored networking (one-time setup):

   Create `%USERPROFILE%\.wslconfig` (e.g. `C:\Users\YourName\.wslconfig`):
   ```ini
   [wsl2]
   networkingMode=mirrored
   ```
   Then restart WSL:
   ```powershell
   wsl --shutdown
   ```

3. Run in the project folder:
   ```bash
   docker compose up -d
   ```

Open **http://localhost:8000** in your browser.

> **VPN on Windows:** With mirrored networking enabled, NordVPN (or any VPN) running on Windows will route Docker container traffic through the VPN tunnel. No extra config needed.

#### macOS (Intel & Apple Silicon)

```bash
docker compose up -d
```

Open **http://localhost:8000**.

> **VPN on macOS:** NordVPN (or any full-tunnel VPN) running on macOS will route Docker traffic through the VPN automatically. If you connect/disconnect the VPN while Docker is running, restart Docker Desktop.
>
> **Apple Silicon note:** Camoufox/Firefox runs under Rosetta 2 emulation. It works but is slower than on x86 machines. For heavy scraping, deploy to a Linux VPS instead.

#### Local setup (without Docker)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install firefox chromium
python -m camoufox fetch    # downloads stealth Firefox binary (~713 MB, one-time)
python run.py
```

### 3. Verify

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","version":"1.0.0"}
```

---

## Using the Web UI

Navigate to **http://localhost:8000**. The UI has three tabs: **Input**, **Output**, and **Settings**.

### Input Tab

The form uses collapsible accordion sections:

**Search Queries** — Enter one or more queries (e.g., "Plumbers in Miami") or paste Google Maps URLs. Add rows with "+ Add Query".

**Extract Cities By Country** — Select from 244 countries with city counts. Optionally pick a US state to narrow to those cities. Enter a business type (with autocomplete from 4,011 Google Maps categories). Set max cities and toggle randomization.

> When a country is selected, the search queries field is disabled — the system auto-generates queries as `"{business_type} in {city}"` for each city.

**Email and Social Links Extraction** — Provide your RapidAPI / Hunter / Apollo key to extract emails, phones, LinkedIn, Twitter, Facebook, etc.

**Reviews Extraction** — Toggle on, set max reviews per place, choose sort order (Newest, Most Relevant, Highest Rating, Lowest Rating).

**Language and Max Results** — Set the Google Maps language and cap results per query.

**Geo Location** — Provide coordinates, search radius in meters (e.g., 5000 = 5km), or zoom level.

**Result Filters** — Skip closed places, set minimum rating/reviews, require website or phone. Filters are applied server-side before enrichment to save API credits.

**Webhook / Integration** — Paste a webhook URL for completion notifications and/or a separate error webhook URL. Works with Slack, n8n, Make, Zapier, Discord, ntfy, Pushover, or any URL that accepts JSON POST.

Click **Run** to start. You'll be switched to the Output tab automatically.

### Output Tab

**Tasks** — Lists all scrape jobs with status badges (running, completed, failed, retrying), result counts, and elapsed time. Click any task to view results.

**Progress** — Real-time progress bar with places scraped, queries completed, elapsed time, and ETA. Shows retry status if a job fails and is retrying.

**Results** — Interactive table with:
- **Filters** — min/max reviews, min rating, has website, has phone, spending on ads, can claim, text search
- **Sort** — by reviews, rating, or name
- **Pagination** — 50 results per page
- **Export** — download as CSV or JSON

### Settings Tab

Configure everything from the browser — settings are saved to `data/settings.json` and hot-reloaded (no restart needed):

- **Scraping** — concurrency, delays, scroll timeout, headless/debug mode
- **Proxy** — proxy URLs (one per line), rotation strategy
- **Enrichment** — provider and API key
- **AI Lead Scoring** — provider, API key, model, ICP, product description
- **Webhooks** — global webhook URLs + error webhook URL

Settings override `mapo.yaml` defaults. Auth credentials stay in `.env` only (not editable from the UI).

Toggle between **light and dark themes** using the button in the top-right corner. Your preference is saved.

---

## VPN Setup (Optional)

For scraping through a VPN, install it at the OS level. Mapo doesn't need any proxy config — the VPN is transparent.

### Linux VPS

```bash
# Install NordVPN
sh <(curl -sSf https://downloads.nordcdn.com/apps/linux/install.sh)
nordvpn login --token YOUR_TOKEN
nordvpn connect us
nordvpn set autoconnect on us

# Start Mapo
docker compose up -d
```

All Mapo traffic routes through NordVPN. To switch countries: `nordvpn connect de`.

### Windows 11

Just connect NordVPN on Windows. With mirrored networking enabled (see Quick Start), Docker container traffic routes through the VPN automatically.

### macOS

Just connect NordVPN on macOS. Docker Desktop routes container traffic through the host's VPN by default.

---

## Self-Hosting with a Domain (Caddy + SSL)

To access Mapo via `https://mapo.yourdomain.com` with automatic SSL:

### 1. Point DNS

Add an A record: `mapo.yourdomain.com → your-vps-ip`

### 2. docker-compose.yaml

```yaml
services:
  mapo:
    build: .
    init: true
    restart: unless-stopped
    shm_size: 800m
    volumes:
      - ./data:/app/data
      - ./mapo.yaml:/app/mapo.yaml:ro
    env_file:
      - .env

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config

volumes:
  caddy_data:
  caddy_config:
```

### 3. Caddyfile

```
mapo.yourdomain.com {
    reverse_proxy mapo:8000
}
```

### 4. Start

```bash
docker compose up -d
```

Caddy auto-provisions Let's Encrypt SSL. Visit **https://mapo.yourdomain.com**.

---

## CLI Usage

The CLI runs the **same full pipeline** as the web UI — filters, enrichment, AI scoring, retries, webhooks. Use it for one-off scrapes, scripted workflows, or cron jobs.

### Basic scraping

```bash
# Quick search by query
python run.py scrape --query "restaurants in NYC" --max-results 100 -o results.csv

# Output formats: CSV, JSON, XLSX (inferred from extension)
python run.py scrape --query "dentists in Miami" -o dentists.json
python run.py scrape --query "lawyers in Chicago" -o lawyers.xlsx
```

### Country / state / city scraping

```bash
# All cities in a country (auto-generates "{biz_type} in {city}" queries)
python run.py scrape --country US --business-type "dentist" -o all_us_dentists.csv

# Limit to specific US state
python run.py scrape --country US --state "California" --business-type "dentist" \
  --max-cities 20 -o ca_dentists.csv

# Randomize city order (default: true) — different cities each run
python run.py scrape --country US --state "Texas" --business-type "plumber" \
  --max-cities 50 --randomize-cities -o tx_plumbers.csv
```

### Filters (server-side, before enrichment)

```bash
# Skip closed places, only 4+ stars, must have phone
python run.py scrape --query "cafes in Portland" --max-results 100 \
  --skip-closed --min-rating 4.0 --has-phone -o quality_cafes.csv

# Must have website + phone + min 50 reviews
python run.py scrape --query "real estate agents in Austin" --max-results 200 \
  --has-website --has-phone --min-reviews 50 -o austin_agents.csv
```

### Reviews extraction

```bash
python run.py scrape --query "hotels in Las Vegas" --max-results 50 \
  --reviews --max-reviews 100 --reviews-sort newest -o vegas_hotels.json
```

### Geo / radius targeting

```bash
# Within 5km radius of coordinates
python run.py scrape --query "coffee shops" --coordinates "40.7128,-74.0060" \
  --radius 5000 --max-results 100 -o nyc_coffee.csv
```

### Cross-reference (skip places you already have)

```bash
# Skip places already in existing.csv (matches by place_id by default)
python run.py scrape --query "Coffee shops in Austin" --max-results 100 \
  --skip-existing existing.csv -o new_only.csv

# Match on a different field
python run.py scrape --query "Dentists in NYC" --max-results 100 \
  --skip-existing my_leads.csv --skip-existing-field phone -o new_dentists.csv

# Top-up mode: keep scraping until you have 100 NEW places (after dedup)
python run.py scrape --query "Plumbers in Miami" \
  --skip-existing existing.csv --target-new 100 -o 100_new_plumbers.csv
```

### Enrichment (emails + social profiles)

```bash
# Add emails/social to scraped places (uses MAPO_ENRICHMENT_API_KEY from .env)
python run.py scrape --query "agencies in Seattle" --max-results 50 \
  --enrichment-key your-rapidapi-key -o seattle_agencies.csv

# Standalone enrichment of an existing CSV
python run.py enrich --input places.csv --provider hunter -o enriched.csv
```

### AI lead scoring

Set `MAPO_AI_PROVIDER` and `MAPO_AI_API_KEY` in `.env` first, then:

```bash
python run.py scrape --query "restaurants in Portland" --max-results 50 \
  --ai -o scored_leads.csv
```

Each result gets `lead_score` (1-10), `icp_match`, `pitch_summary`, `suggested_approach`. With multiple emails, you also get `best_email_ai` (LLM-ranked best contact).

### Webhooks (notifications)

```bash
# POST results to a webhook on completion
python run.py scrape --query "Coffee shops in Austin" --max-results 50 \
  --webhook-url "https://your-n8n.com/webhook/abc" -o results.csv

# Separate error webhook (Slack, Discord, ntfy, etc.)
python run.py scrape --query "..." \
  --webhook-url "https://hooks.slack.com/services/XXX/done" \
  --error-webhook-url "https://hooks.slack.com/services/XXX/errors" \
  -o results.csv
```

### Retry on failure

```bash
# 3 retries with exponential backoff (default: 2 retries)
python run.py scrape --query "..." --retries 3 -o results.csv
```

### All flags

```bash
python run.py scrape --help
```

---

## Web UI

Open **http://localhost:8000** in your browser. Three tabs:

### Input Tab
Build a scrape job using collapsible accordion sections:

| Section | Purpose |
|---|---|
| **Search Queries** | Free-text queries (multi-line) or Google Maps URLs |
| **Extract Cities By Country** | Pick country (244 supported), state, business type, max cities |
| **Email and Social Links Extraction** | API key for enrichment provider |
| **Reviews Extraction** | Toggle reviews, max per place, sort order |
| **Language and Max Results** | Language code + max results per query |
| **Geo Location** | Coordinates, search radius (meters), zoom level |
| **Result Filters** | Skip closed, min rating, min reviews, must have website/phone |
| **Cross-Reference (Skip Existing)** | Upload CSV → skip places you already have, optional "Target New" top-up |
| **Webhook / Integration** | Per-job webhook URL + error webhook URL |

Click **Run** → switches to Output tab and shows live progress.

### Output Tab
- **Tasks** — list of all jobs with status badges, click any to view results
- **Progress** — real-time SSE updates with ETA
- **Results** — sortable, filterable table with CSV/JSON download buttons

### Schedules Tab
Recurring cron jobs that run automatically:

- Click **+ New Schedule**
- Enter name, set cron expression (or use Hourly/Daily/Weekly/Monthly presets)
- Fill in scrape parameters (same as Input tab)
- Click **Save Schedule**
- Use **Run Now** to test, **Edit** to modify, **Delete** to remove

Scheduled jobs use the same full pipeline — they get filters, AI, cross-ref, webhooks.

### Settings Tab
Configure everything from the browser (saved to `data/settings.json`, hot-reloaded):

- **Scraping** — Recommended Presets (Conservative / Balanced / Aggressive / Lead-gen) + browser, concurrency, delays, headless mode
- **Limits & Safeguards** — max_results, max_cities, max_total, max_concurrent_jobs, max_runtime_minutes
- **Proxy** — URLs (one per line), rotation strategy
- **Enrichment** — provider + API key
- **AI Lead Scoring** — provider, key, model, ICP, product description
- **Webhooks** — global completion + error webhook URLs

Toggle **light/dark theme** with the button in the top-right corner.

---

## Docker Usage

### Quick start

```bash
git clone https://github.com/AdrielleU/mapo.git
cd mapo
cp .env.example .env
# Edit .env if you want auth, AI, enrichment, or proxies

docker compose up -d
```

Open **http://localhost:8000**. That's it.

### Run a CLI command inside the container

```bash
# One-off scrape via CLI inside the running container
docker compose exec mapo python run.py scrape \
  --query "Coffee shops in Austin" --max-results 50 -o /app/data/austin.csv

# Files written to /app/data/ are visible on the host in ./data/
```

### View logs

```bash
docker compose logs -f mapo
```

### Stop / restart

```bash
docker compose down       # stop everything
docker compose restart    # restart after changing .env or mapo.yaml
docker compose up --build # rebuild after `git pull`
```

### Persistent data

The `./data` volume holds:
- `mapo_jobs.db` — job history (SQLite)
- `settings.json` — UI-saved settings
- `schedules.json` — cron schedules
- `exports/` — auto-saved JSON of every scrape (CSV available on demand via API)

Back this up to keep your jobs and schedules across rebuilds.

### Multiple instances on one VPS

```yaml
services:
  mapo-us:
    build: .
    ports: ["8001:8000"]
    volumes: [./data/us:/app/data:z, ./mapo.yaml:/app/mapo.yaml:ro,z]
    env_file: [.env]

  mapo-eu:
    build: .
    ports: ["8002:8000"]
    volumes: [./data/eu:/app/data:z, ./mapo.yaml:/app/mapo.yaml:ro,z]
    env_file: [.env]
```

Same auth credentials work across all instances (env vars).

---

## Common Workflows

### Daily new-leads scrape

```bash
# Initial scrape
python run.py scrape --query "Plumbers in Miami" --max-results 200 -o leads_v1.csv

# Tomorrow: only get NEW ones
python run.py scrape --query "Plumbers in Miami" --max-results 200 \
  --skip-existing leads_v1.csv --target-new 50 -o new_leads_today.csv
```

Or set this up as a recurring schedule in the Schedules tab — it runs daily, skips what you already have, posts new leads to a webhook.

### Country-wide lead generation with AI scoring

```bash
python run.py scrape \
  --country US --state Texas --business-type "dentist" \
  --max-cities 30 --max-results 50 \
  --skip-closed --min-rating 4.0 --has-website --has-phone \
  --ai \
  --enrichment-key your-key \
  -o tx_dentists_scored.csv
```

Output: places filtered for quality, with AI lead scores, ICP match reasoning, and AI-ranked best emails.

### Webhook-driven pipeline (n8n, Make, Zapier)

1. In the Schedules tab, create a daily schedule
2. Set webhook URL to your n8n/Make endpoint
3. n8n receives the full results JSON each day
4. n8n maps fields → pushes to HubSpot/Pipedrive/your CRM

### Self-hosted with VPN routing

On a Linux VPS:
```bash
# Install NordVPN at OS level
sh <(curl -sSf https://downloads.nordcdn.com/apps/linux/install.sh)
nordvpn login --token YOUR_TOKEN
nordvpn connect us
nordvpn set autoconnect on us

# Start Mapo — all traffic routes through VPN automatically
docker compose up -d
```

---

## REST API

### Start a scrape

```bash
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cafes in Portland",
    "max_results": 50,
    "enable_reviews": true,
    "skip_closed": true,
    "min_rating": 4.0,
    "max_retries": 2,
    "webhook_url": "https://your-n8n.com/webhook/abc",
    "error_webhook_url": "https://hooks.slack.com/services/XXX"
  }'
```

### Country-wide scrape

```bash
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "country": "US",
    "state": "California",
    "business_type": "dentist",
    "max_cities": 50,
    "randomize_cities": true,
    "max_results": 100,
    "radius_meters": 5000
  }'
```

### Monitor progress (SSE)

```bash
curl -N http://localhost:8000/api/v1/progress/{job_id}
# Streams: data: {"type":"progress","percent":45.2,"places_scraped":23,...}
# Retry:   data: {"type":"retrying","attempt":1,"max_retries":2,"retry_in":30}
# Final:   data: {"type":"completed","total_results":51}
```

### Get results

```bash
curl http://localhost:8000/api/v1/jobs/{job_id}
curl http://localhost:8000/api/v1/jobs/{job_id}/download?format=csv -o results.csv
curl http://localhost:8000/api/v1/jobs/{job_id}/download?format=json -o results.json
```

### Settings (read/write from UI or API)

```bash
# Get current settings
curl http://localhost:8000/api/v1/settings

# Update settings (hot-reloads, no restart)
curl -X PUT http://localhost:8000/api/v1/settings \
  -H "Content-Type: application/json" \
  -d '{"scraping": {"concurrency": 10}, "proxy": {"urls": ["socks5://127.0.0.1:1080"]}}'
```

### Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/scrape` | Start a scrape job |
| `GET` | `/api/v1/jobs` | List all jobs |
| `GET` | `/api/v1/jobs/{id}` | Job status + results |
| `GET` | `/api/v1/jobs/{id}/download` | Download results (`?format=csv\|json`) |
| `DELETE` | `/api/v1/jobs/{id}` | Cancel or delete a job |
| `GET` | `/api/v1/progress/{id}` | SSE progress stream |
| `POST` | `/api/v1/enrich` | Standalone enrichment |
| `GET` | `/api/v1/countries` | List all countries with city counts |
| `GET` | `/api/v1/states` | List states (`?country=US`) |
| `GET` | `/api/v1/states/{state}/cities` | List cities for a state |
| `GET` | `/api/v1/categories` | Business category options (4,011) |
| `GET` | `/api/v1/settings` | Get saved settings |
| `PUT` | `/api/v1/settings` | Update settings (hot-reload) |
| `GET` | `/api/v1/health` | Health check |

---

## Configuration

Settings are loaded in this priority order (highest wins):

1. **Settings UI** (`data/settings.json`) — changed from the browser, hot-reloaded
2. **Environment variables** (`.env` file)
3. **mapo.yaml** — base defaults

See `mapo.yaml` for all available settings and `.env.example` for environment variables.

### Authentication

Set in `.env` (not configurable from the UI):

```bash
MAPO_USERNAME=admin
MAPO_PASSWORD=your-strong-password
MAPO_TOTP_SECRET=JBSWY3DPEHPK3PXP   # optional MFA
```

Generate a TOTP secret: `python -c "import secrets,base64;print(base64.b32encode(secrets.token_bytes(20)).decode())"`

Add the secret to Google Authenticator / Authy. Same secret on all your servers = one authenticator entry for everything.

Leave all three empty to disable authentication (default).

### Webhooks

**Completion webhook** — sends full results (up to 500 leads) + download URLs:

```json
{
  "event": "task.completed",
  "data": {
    "job_id": "abc-123",
    "query": "Dentists in Miami",
    "result_count": 47,
    "results": [{ "name": "...", "phone": "...", ... }],
    "download_csv": "/api/v1/jobs/abc-123/download?format=csv",
    "download_json": "/api/v1/jobs/abc-123/download?format=json"
  }
}
```

**Error webhook** — fires on final failure (after all retries exhausted):

```json
{
  "event": "task.failed",
  "data": {
    "job_id": "abc-123",
    "error": "Connection timeout",
    "attempt": 3,
    "max_retries": 2,
    "results_before_failure": 23
  }
}
```

Works with Slack, Discord, n8n, Make, Zapier, ntfy, Pushover — any URL that accepts JSON POST. Set per-job in the Input tab or globally in the Settings tab.

---

## Architecture

```
run.py                          # Entry point: CLI or web server
├── frontend/                   # Web UI (vanilla HTML/CSS/JS, no build step)
│   ├── index.html              # SPA with light/dark theme + settings
│   ├── style.css               # WCAG AA compliant styles
│   └── data.js                 # Static categories + states (auto-generated)
├── backend/
│   ├── config.py               # Config (yaml + env + UI settings)
│   ├── server.py               # FastAPI app + SSE + retry logic
│   ├── auth.py                 # Login + TOTP authentication
│   ├── cli.py                  # CLI interface
│   ├── progress.py             # Job progress tracking
│   ├── webhooks.py             # Webhook delivery (Slack + generic)
│   ├── scheduler.py            # APScheduler cron jobs
│   ├── scrapers/
│   │   ├── places.py           # Camoufox + HTTP scraper (configurable concurrency/delays)
│   │   ├── extract.py          # APP_INITIALIZATION_STATE parser
│   │   ├── reviews.py          # Review API (40x parallel)
│   │   ├── filters.py          # 8 filter criteria (rating, phone, closed, category, etc.)
│   │   └── social.py           # Enrichment integration
│   ├── enrichment/             # Email/social providers
│   ├── detection/              # Tech stack, ads, contact forms
│   ├── ai/                     # Lead scoring + review analysis
│   ├── outputs/                # CSV, JSON, Postgres, Sheets, S3
│   ├── api/                    # REST API routes + models
│   └── data/                   # Static data (countries, categories, states)
├── scripts/
│   └── generate_frontend_data.py  # Generates frontend/data.js
├── mapo.yaml                   # Configuration defaults
├── docker-compose.yaml         # Docker deployment
└── Dockerfile                  # python:3.12-slim + Playwright Firefox + Chromium + Camoufox
```

### Scraping Pipeline

1. Query submitted via UI, API, CLI, or scheduler
2. Server splits into sub-tasks (per query or per city/state)
3. Stealth browser (Camoufox Firefox or Patchright Chromium) scrolls Google Maps results
4. Parallel HTTP fetches individual place pages (configurable concurrency)
5. Parses Google's `APP_INITIALIZATION_STATE` for structured data
6. Server-side filters applied (skip closed, min rating, etc.)
7. Optional: enrichment, detection, reviews, AI scoring
8. Results deduped, filtered, written to configured outputs
9. Webhook notification fired (completion or error)
10. On failure: auto-retry with backoff (up to 3 attempts)

---

## Anti-Detection

- **Dual browser backends** — Camoufox (stealth Firefox with fingerprint spoofing) or Patchright (anti-detection Chromium). Switchable in Settings.
- **Proxy rotation** — HTTP/HTTPS/SOCKS5 with round-robin, random, or geo-match
- **Hardened selectors** — aria-label/role-based with text-content fallbacks
- **Behavioral mimicry** — configurable randomized delays and jittered timeouts
- **User-agent rotation** — 12+ current browser user agents
- **HTTP/2** — httpx with HTTP/2 support defeats TLS fingerprinting
- **Debug mode** — set headless=false in Settings to watch the browser live

---

## License

[MIT](LICENSE)

## Acknowledgments

Derived from [omkarcloud/google-maps-scraper](https://github.com/omkarcloud/google-maps-scraper), rebuilt with a modular architecture using FastAPI, [Camoufox](https://github.com/daijro/camoufox), [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright), and asyncio.
