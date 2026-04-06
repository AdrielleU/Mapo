"""
Mapo entry point.

Dispatches to CLI mode (scrape/enrich subcommands) or starts the
Botasaurus web server with UI.
"""
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("scrape", "enrich"):
        from backend.cli import main as cli_main
        cli_main()
    else:
        import backend.server  # noqa: F401 — registers scrapers
        from backend.config import config

        # Start scheduler if enabled
        if config.scheduler.enabled:
            from backend.scheduler import scheduler
            scheduler.start()

        from botasaurus_server.run import run
        run()


if __name__ == "__main__":
    main()
