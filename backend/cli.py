"""
Mapo CLI interface.

Provides ``scrape`` and ``enrich`` subcommands for headless, non-UI usage.

Usage::

    python -m backend.cli scrape --query "restaurants in NYC" --output results.csv
    python -m backend.cli enrich --input places.csv --output enriched.csv
"""
import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_format(filepath: str, explicit: str | None) -> str:
    """Return the output format, inferred from extension if not given."""
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
    """Write a list of dicts to a CSV file."""
    if not data:
        logger.warning("No data to write")
        return
    keys = list(data[0].keys())
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)


def _write_json(data: list[dict], filepath: str) -> None:
    """Write a list of dicts to a JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _write_xlsx(data: list[dict], filepath: str) -> None:
    """Write a list of dicts to an XLSX file (requires openpyxl)."""
    try:
        from openpyxl import Workbook
    except ImportError:
        raise ImportError(
            "The 'openpyxl' package is required for XLSX output. "
            "Install it with: pip install openpyxl"
        )
    if not data:
        logger.warning("No data to write")
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
    """Dispatch to the correct writer."""
    writers = {"csv": _write_csv, "json": _write_json, "xlsx": _write_xlsx}
    writer = writers.get(fmt)
    if writer is None:
        raise ValueError(f"Unsupported format: {fmt!r}")
    writer(data, filepath)


def _read_input(filepath: str) -> list[dict]:
    """Read CSV or JSON input file into a list of dicts."""
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
    """Print a summary table using rich if available, else plain text."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"{label} Summary")
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Total records", str(len(data)))
        if data:
            sample = data[0]
            table.add_row("Fields", str(len(sample.keys())))
            table.add_row("Sample fields", ", ".join(list(sample.keys())[:6]))
        console.print(table)
    except ImportError:
        print(f"\n--- {label} Summary ---")
        print(f"  Total records: {len(data)}")
        if data:
            print(f"  Fields: {len(data[0].keys())}")
            print(f"  Sample fields: {', '.join(list(data[0].keys())[:6])}")
        print()


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def _cmd_scrape(args: argparse.Namespace) -> None:
    """Execute the scrape subcommand."""
    try:
        from rich.progress import Progress, SpinnerColumn, TextColumn
    except ImportError:
        Progress = None  # type: ignore[misc, assignment]

    # Build the query
    query = args.query
    if not query and args.country and args.business_type:
        query = f"{args.business_type} in {args.country}"

    if not query:
        print("Error: provide --query or both --country and --business-type", file=sys.stderr)
        sys.exit(1)

    fmt = _infer_format(args.output, args.format)

    # Import scraper late so CLI help loads fast
    from backend.scrapers.places import scrape_places

    data_input = {
        "query": query,
        "max_results": args.max_results,
    }
    if args.lang:
        data_input["lang"] = args.lang
    if args.coordinates:
        data_input["coordinates"] = args.coordinates
    if args.zoom:
        data_input["zoom"] = args.zoom

    print(f"Scraping: {query} (max {args.max_results} results)")

    if Progress is not None:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            progress.add_task("Scraping Google Maps...", total=None)
            results = scrape_places(data_input)
    else:
        results = scrape_places(data_input)

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
        track = None  # type: ignore[assignment]

    enriched = []
    items = track(records, description="Enriching...") if track else records  # type: ignore[arg-type]

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
    sp_scrape = subparsers.add_parser("scrape", help="Scrape Google Maps places")
    sp_scrape.add_argument("--query", type=str, default="", help="Search query, e.g. 'restaurants in NYC'")
    sp_scrape.add_argument("--country", type=str, default="", help="Country code (used with --business-type)")
    sp_scrape.add_argument("--business-type", type=str, default="", help="Business type (used with --country)")
    sp_scrape.add_argument("--max-results", type=int, default=100, help="Maximum results to scrape (default: 100)")
    sp_scrape.add_argument("--output", type=str, required=True, help="Output file path")
    sp_scrape.add_argument("--format", type=str, choices=["csv", "json", "xlsx"], default=None, help="Output format (inferred from extension if omitted)")
    sp_scrape.add_argument("--lang", type=str, default=None, help="Language code, e.g. 'en'")
    sp_scrape.add_argument("--coordinates", type=str, default=None, help="Center coordinates 'lat,lon'")
    sp_scrape.add_argument("--zoom", type=int, default=None, help="Map zoom level")

    # --- enrich ---
    sp_enrich = subparsers.add_parser("enrich", help="Enrich places with contact data")
    sp_enrich.add_argument("--input", type=str, required=True, help="Input CSV or JSON file")
    sp_enrich.add_argument("--provider", type=str, default=None, help="Enrichment provider (default from config)")
    sp_enrich.add_argument("--output", type=str, required=True, help="Output file path")
    sp_enrich.add_argument("--format", type=str, choices=["csv", "json", "xlsx"], default=None, help="Output format (inferred from extension if omitted)")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point — parse args and dispatch to the appropriate subcommand."""
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
            # Default provider from config if not specified
            if args.provider is None:
                from backend.config import config
                args.provider = config.enrichment.provider
            _cmd_enrich(args)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)
    except Exception as exc:
        logger.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
