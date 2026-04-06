"""
Mapo entry point.

Dispatches to CLI mode (scrape/enrich subcommands) or starts the
FastAPI web server.
"""
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("scrape", "enrich"):
        from backend.cli import main as cli_main
        cli_main()
    else:
        import uvicorn
        from backend.config import config

        if config.scheduler.enabled:
            from backend.scheduler import scheduler
            scheduler.start()

        uvicorn.run("backend.server:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
