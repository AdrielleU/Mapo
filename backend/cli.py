"""
Mapo CLI interface.

Provides ``scrape`` and ``enrich`` subcommands for headless, non-UI usage.
Runs the same pipeline as the web UI (filters, enrichment, reviews, AI).

Usage::

    python run.py scrape --query "restaurants in NYC" --output results.csv
    python run.py scrape --country US --state California --business-type dentist --output dentists.json
    python run.py enrich --input places.csv --output enriched.csv
"""
import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _infer_format(filepath: str, explicit: str | None) -> str:
    if explicit:
        return explicit.lower()
    ext = Path(filepath).suffix.lower()
    mapping = {".csv": "csv", ".json": "json", ".xlsx": "xlsx"}
    fmt = mapping.get(ext)
    if fmt is None:
        raise ValueError(
            f"Cannot infer format from extension {ext!r}. "
            f"Use --format to specify one of: csv, json, xlsx"
        )
    return fmt


def _write_csv(data: list[dict], filepath: str) -> None:
    if not data:
        return
    keys = list(data[0].keys())
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            flat = {}
            for k, v in row.items():
                flat[k] = json.dumps(v) if isinstance(v, (list, dict)) else v
            writer.writerow(flat)


def _write_json(data: list[dict], filepath: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _write_xlsx(data: list[dict], filepath: str) -> None:
    try:
        from openpyxl import Workbook
    except ImportError:
        raise ImportError("openpyxl required for XLSX: pip install openpyxl")
    if not data:
        return
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    wb = Workbook()
    ws = wb.active
    keys = list(data[0].keys())
    ws.append(keys)
    for row in data:
        ws.append([row.get(k, "") for k in keys])
    wb.save(filepath)


def _write_output(data: list[dict], filepath: str, fmt: str) -> None:
    writers = {"csv": _write_csv, "json": _write_json, "xlsx": _write_xlsx}
    writer = writers.get(fmt)
    if writer is None:
        raise ValueError(f"Unsupported format: {fmt!r}")
    writer(data, filepath)


def _read_input(filepath: str) -> list[dict]:
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        with open(filepath, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    elif ext == ".json":
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            raise ValueError("JSON input must be a list of objects")
    else:
        raise ValueError(f"Unsupported input format: {ext!r}. Use .csv or .json")


def _print_summary(data: list[dict], label: str) -> None:
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"{label} Summary")
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Total records", str(len(data)))
        if data:
            table.add_row("Fields", str(len(data[0].keys())))
            table.add_row("Sample fields", ", ".join(list(data[0].keys())[:8]))
        console.print(table)
    except ImportError:
        print(f"\n--- {label} Summary ---")
        print(f"  Total records: {len(data)}")
        if data:
            print(f"  Fields: {len(data[0].keys())}")
        print()


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def _cmd_scrape(args: argparse.Namespace) -> None:
    """Execute the scrape subcommand using the full pipeline."""
    import time
    import uuid

    fmt = _infer_format(args.output, args.format)

    # Build params matching ScrapeRequest model
    params = {
        "query": args.query or "",
        "country": args.country or "",
        "state": args.state or "",
        "business_type": args.business_type or "",
        "max_results": args.max_results,
        "max_cities": args.max_cities,
        "randomize_cities": args.randomize_cities,
        "lang": args.lang or "",
        "coordinates": args.coordinates or "",
        "zoom_level": args.zoom or 14,
        "radius_meters": args.radius,
        "enable_reviews": args.reviews,
        "max_reviews": args.max_reviews,
        "reviews_sort": args.reviews_sort,
        "enrichment_api_key": args.enrichment_key or "",
        "enable_ai": args.ai,
        "max_retries": args.retries,
        "retry_delay": 30,
        # Filters
        "skip_closed": args.skip_closed,
        "min_rating": args.min_rating,
        "min_reviews": args.min_reviews,
        "has_website": True if args.has_website else None,
        "has_phone": True if args.has_phone else None,
        # Webhooks
        "webhook_url": args.webhook_url or "",
        "error_webhook_url": args.error_webhook_url or "",
        "webhook_headers": {},
        "skip_existing_csv": args.skip_existing or "",
        "skip_existing_csv_data": "",
        "skip_existing_field": args.skip_existing_field or "place_id",
        "target_new": args.target_new,
        "target_buffer": 2.0,
        "export_preset": args.preset or "",
        "export_fields": [f.strip() for f in args.fields.split(",")] if args.fields else [],
    }

    if not params["query"] and not params["country"]:
        print("Error: provide --query or --country + --business-type", file=sys.stderr)
        sys.exit(1)
    if params["country"] and not params["business_type"]:
        print("Error: --business-type required with --country", file=sys.stderr)
        sys.exit(1)

    # Describe what we're doing
    if params["query"]:
        desc = params["query"]
    else:
        desc = f"{params['business_type']} in {params['country']}"
        if params["state"]:
            desc += f" ({params['state']})"
    print(f"Scraping: {desc} (max {args.max_results} results)")

    if args.skip_closed:
        print("  Filtering: skip closed places")
    if args.min_rating:
        print(f"  Filtering: min rating {args.min_rating}")
    if args.reviews:
        print(f"  Reviews: enabled (max {args.max_reviews}, sort={args.reviews_sort})")

    # Run the full pipeline
    from backend.server import run_pipeline, _jobs, _init_db

    _init_db()

    job_id = str(uuid.uuid4())
    now = time.time()
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "created",
        "params": params,
        "results": [],
        "error": None,
        "created_at": now,
        "updated_at": now,
        "progress": None,
        "_task": None,
    }

    try:
        from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
        use_rich = True
    except ImportError:
        use_rich = False

    async def _run():
        await run_pipeline(job_id, params)

    if use_rich:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            progress.add_task("Scraping...", total=None)
            asyncio.run(_run())
    else:
        print("Running pipeline...")
        asyncio.run(_run())

    job = _jobs[job_id]
    results = job.get("results", [])

    if job["status"] == "failed":
        print(f"Error: {job.get('error', 'Unknown')}", file=sys.stderr)
        if results:
            print(f"  (partial results: {len(results)} records)")

    if not results:
        print("No results found.")
        return

    _write_output(results, args.output, fmt)
    print(f"Wrote {len(results)} records to {args.output} ({fmt})")
    _print_summary(results, "Scrape")


def _cmd_enrich(args: argparse.Namespace) -> None:
    """Execute the enrich subcommand."""
    from backend.enrichment import get_provider

    records = _read_input(args.input)
    if not records:
        print("Input file is empty.")
        return

    fmt = _infer_format(args.output, getattr(args, "format", None))
    provider = get_provider(args.provider)

    print(f"Enriching {len(records)} records using {args.provider}...")

    try:
        from rich.progress import track
    except ImportError:
        track = None

    enriched = []
    items = track(records, description="Enriching...") if track else records

    for record in items:
        website = record.get("website", "")
        if website:
            try:
                extra = provider.enrich(website)
                record.update(extra)
            except Exception as exc:
                logger.warning("Enrichment failed for %s: %s", website, exc)
        enriched.append(record)

    _write_output(enriched, args.output, fmt)
    print(f"Wrote {len(enriched)} enriched records to {args.output}")
    _print_summary(enriched, "Enrich")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mapo",
        description="Mapo — Google Maps business data scraper CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- scrape ---
    sp = subparsers.add_parser("scrape", help="Scrape Google Maps places")

    # Search
    sp.add_argument("--query", type=str, default="", help="Search query, e.g. 'restaurants in NYC'")
    sp.add_argument("--country", type=str, default="", help="Country code (e.g. US, DE, JP)")
    sp.add_argument("--state", type=str, default="", help="US state name (e.g. California)")
    sp.add_argument("--business-type", type=str, default="", help="Business type (used with --country)")
    sp.add_argument("--max-results", type=int, default=100, help="Max results per query (default: 100)")
    sp.add_argument("--max-cities", type=int, default=None, help="Max cities to scrape (country mode)")
    sp.add_argument("--randomize-cities", action="store_true", default=True, help="Randomize city order (default: true)")
    sp.add_argument("--no-randomize-cities", dest="randomize_cities", action="store_false")

    # Output
    sp.add_argument("--output", "-o", type=str, required=True, help="Output file path (.csv, .json, .xlsx)")
    sp.add_argument("--format", type=str, choices=["csv", "json", "xlsx"], default=None)

    # Geo
    sp.add_argument("--lang", type=str, default=None, help="Language code (e.g. en, es, de)")
    sp.add_argument("--coordinates", type=str, default=None, help="Center coordinates 'lat,lon'")
    sp.add_argument("--zoom", type=int, default=None, help="Map zoom level (1-21)")
    sp.add_argument("--radius", type=int, default=None, help="Search radius in meters (overrides zoom)")

    # Reviews
    sp.add_argument("--reviews", action="store_true", default=False, help="Enable review extraction")
    sp.add_argument("--max-reviews", type=int, default=20, help="Max reviews per place (default: 20)")
    sp.add_argument("--reviews-sort", type=str, default="newest", choices=["newest", "most_relevant", "highest_rating", "lowest_rating"])

    # Enrichment
    sp.add_argument("--enrichment-key", type=str, default=None, help="API key for email/social enrichment")

    # AI
    sp.add_argument("--ai", action="store_true", default=False, help="Enable AI lead scoring")

    # Filters
    sp.add_argument("--skip-closed", action="store_true", default=False, help="Exclude closed businesses")
    sp.add_argument("--min-rating", type=float, default=None, help="Minimum star rating (0-5)")
    sp.add_argument("--min-reviews", type=int, default=None, help="Minimum review count")
    sp.add_argument("--has-website", action="store_true", default=False, help="Only include places with a website")
    sp.add_argument("--has-phone", action="store_true", default=False, help="Only include places with a phone")

    # Retry
    sp.add_argument("--retries", type=int, default=2, help="Max retries on failure (default: 2)")

    # Webhooks
    sp.add_argument("--webhook-url", type=str, default=None, help="Webhook URL for completion notification")
    sp.add_argument("--error-webhook-url", type=str, default=None, help="Webhook URL for error notification")

    # Cross-reference (skip places already in an existing CSV/JSON)
    sp.add_argument("--skip-existing", type=str, default=None, help="Path to CSV/JSON of places to skip (e.g. existing leads)")
    sp.add_argument("--skip-existing-field", type=str, default="place_id", help="Field to dedup on (default: place_id)")
    sp.add_argument("--target-new", type=int, default=None, help="Target number of NEW places after cross-ref dedup (top-up mode)")

    # Field selection
    sp.add_argument("--fields", type=str, default=None, help="Comma-separated list of fields to export (e.g. 'name,phone,website')")
    sp.add_argument("--preset", type=str, default=None,
                    choices=["minimal", "clay", "apollo", "hubspot", "instantly", "n8n", "leads", "geo", "full"],
                    help="Export preset (overrides --fields if both given)")

    # --- enrich ---
    sp_e = subparsers.add_parser("enrich", help="Enrich places with contact data")
    sp_e.add_argument("--input", "-i", type=str, required=True, help="Input CSV or JSON file")
    sp_e.add_argument("--provider", type=str, default=None, help="Enrichment provider (default from config)")
    sp_e.add_argument("--output", "-o", type=str, required=True, help="Output file path")
    sp_e.add_argument("--format", type=str, choices=["csv", "json", "xlsx"], default=None)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "scrape":
            _cmd_scrape(args)
        elif args.command == "enrich":
            if args.provider is None:
                from backend.config import config
                args.provider = config.enrichment.provider
            _cmd_enrich(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as exc:
        logger.error("Fatal: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
