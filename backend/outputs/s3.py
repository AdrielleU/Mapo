"""Amazon S3 output writer using boto3."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from backend.outputs.base import OutputWriter


class S3Writer(OutputWriter):
    """Upload data as CSV or JSON to an Amazon S3 bucket.

    Config keys:

    * ``bucket`` — S3 bucket name (required).
    * ``key_prefix`` — object key prefix / path (default ``""``).
    * ``region`` — AWS region (optional, uses boto3 default if omitted).
    * ``format`` — ``"csv"`` or ``"json"`` (default ``"json"``).
    """

    def write(self, data: list[dict], metadata: dict) -> None:
        if not data:
            return

        boto3 = _import_boto3()

        bucket = self.config.get("bucket")
        key_prefix = self.config.get("key_prefix", "")
        region = self.config.get("region")
        fmt = self.config.get("format", "json").lower().strip()

        if not bucket:
            raise ValueError("S3Writer requires a 'bucket' in config")
        if fmt not in ("csv", "json"):
            raise ValueError(f"S3Writer format must be 'csv' or 'json', got {fmt!r}")

        # Build the payload.
        if fmt == "json":
            body = json.dumps(data, indent=2, ensure_ascii=False, default=str)
            content_type = "application/json"
            extension = "json"
        else:
            body = _to_csv_string(data)
            content_type = "text/csv"
            extension = "csv"

        key = f"{key_prefix}output.{extension}" if key_prefix else f"output.{extension}"

        # Upload to S3.
        client_kwargs: dict[str, Any] = {}
        if region:
            client_kwargs["region_name"] = region

        s3_client = boto3.client("s3", **client_kwargs)
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType=content_type,
        )


def _to_csv_string(data: list[dict]) -> str:
    """Serialize *data* to a CSV string."""
    if not data:
        return ""
    headers = list(data[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in data:
        flat: dict[str, Any] = {}
        for h in headers:
            v = row.get(h)
            flat[h] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
        writer.writerow(flat)
    return buf.getvalue()


def _import_boto3():  # type: ignore[no-untyped-def]
    """Lazy-import boto3 with a helpful error message."""
    try:
        import boto3
        return boto3
    except ImportError:
        raise ImportError(
            "The 'boto3' package is required for S3Writer. "
            "Install it with: pip install boto3"
        ) from None
