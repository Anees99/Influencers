"""CSV ingestion with robust column mapping and per-row error isolation."""
from __future__ import annotations

import csv
import io


COLUMN_ALIASES = {
    "creator_name": "creator", "creator": "creator", "name": "creator",
    "influencer": "creator", "creator handle": "handle", "handle": "handle",
    "instagram_handle": "handle",
    "content_id": "content_id", "post_id": "content_id", "content id": "content_id",
    "platform": "platform",
    "content_type": "content_type", "type": "content_type", "format": "content_type",
    "publish_date": "publish_date", "published_date": "publish_date",
    "date": "publish_date", "live date": "publish_date",
    "views": "views", "reach": "reach", "impressions": "impressions",
    "likes": "likes", "comments": "comments", "saves": "saves",
    "shares": "shares", "watch_time": "watch_time", "watch time": "watch_time",
    "captured_at": "captured_at", "report_date": "captured_at", "snapshot_date": "captured_at",
    "invoice_number": "invoice_number", "invoice": "invoice_number",
    "amount": "amount", "payout_id": "payout_id", "payment_ref": "payout_id",
    "payment_date": "payment_date", "status": "status",
    "currency": "currency", "deliverable_id": "deliverable_id",
    "required": "required", "approval_status": "approval_status",
    "approval": "approval_status",
}


class CsvError(Exception):
    pass


def read_rows(blob: bytes | str, filename: str = "") -> tuple[list[dict], list[str]]:
    """Return (rows with canonical keys, warnings). Bad rows are skipped, not fatal."""
    warnings: list[str] = []
    if isinstance(blob, bytes):
        try:
            text = blob.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = blob.decode("latin-1", errors="replace")
            warnings.append("file is not valid UTF-8; decoded as latin-1")
    else:
        text = blob
    try:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise CsvError(f"{filename}: empty file")
        raw_fields = list(reader.fieldnames)
        canon = {}
        for f in raw_fields:
            key = str(f or "").strip().lower()
            canon[f] = COLUMN_ALIASES.get(key, key.replace(" ", "_"))
        rows = []
        for i, raw in enumerate(reader, start=2):
            if all((v is None or str(v).strip() == "") for v in raw.values()):
                warnings.append(f"row {i}: blank row skipped")
                continue
            row = {canon.get(k, k): (v.strip() if isinstance(v, str) else v)
                   for k, v in raw.items() if k is not None}
            rows.append(row)
        if not rows:
            warnings.append("no data rows found")
        return rows, warnings
    except CsvError:
        raise
    except Exception as exc:
        raise CsvError(f"{filename}: malformed CSV ({exc})") from exc
