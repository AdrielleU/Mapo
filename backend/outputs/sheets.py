"""Google Sheets output writer using gspread."""

from __future__ import annotations

import json
from typing import Any

from backend.outputs.base import OutputWriter


class SheetsWriter(OutputWriter):
    """Write rows to a Google Sheets worksheet.

    Config keys:

    * ``credentials_file`` — path to a service-account JSON key file (required).
    * ``spreadsheet_id`` — the Google Sheets spreadsheet ID (required).
    * ``worksheet`` — worksheet name or index (default ``"Sheet1"``).
    """

    def write(self, data: list[dict], metadata: dict) -> None:
        if not data:
            return

        gspread = _import_gspread()

        creds_file = self.config.get("credentials_file")
        spreadsheet_id = self.config.get("spreadsheet_id")
        worksheet_name = self.config.get("worksheet", "Sheet1")

        if not creds_file:
            raise ValueError("SheetsWriter requires a 'credentials_file' in config")
        if not spreadsheet_id:
            raise ValueError("SheetsWriter requires a 'spreadsheet_id' in config")

        # Authenticate and open the spreadsheet.
        gc = gspread.service_account(filename=creds_file)
        spreadsheet = gc.open_by_key(spreadsheet_id)

        # Open or create the worksheet.
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title=worksheet_name, rows=len(data) + 1, cols=len(data[0])
            )

        # Build the grid: header row + data rows.
        headers = list(data[0].keys())
        rows = [headers]
        for row in data:
            rows.append([_cell_value(row.get(h)) for h in headers])

        worksheet.clear()
        worksheet.update(rows, value_input_option="RAW")


def _cell_value(value: Any) -> str:
    """Convert a value to a Sheets-friendly string."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _import_gspread():  # type: ignore[no-untyped-def]
    """Lazy-import gspread with a helpful error message."""
    try:
        import gspread
        return gspread
    except ImportError:
        raise ImportError(
            "The 'gspread' package is required for SheetsWriter. "
            "Install it with: pip install gspread"
        ) from None
