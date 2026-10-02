"""SQLite persistence layer.

The in-memory PipelineResult is the source of truth during a session; this
module persists everything (including snapshot-level analytics and exception
status changes) so state survives page reloads and can be audited with SQL.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from config.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    client_name TEXT, campaign_name TEXT, start_date TEXT, end_date TEXT,
    currency TEXT, platforms TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS creators (
    creator_id TEXT PRIMARY KEY,
    canonical_name TEXT, instagram_handle TEXT, tiktok_handle TEXT, email TEXT
);
CREATE TABLE IF NOT EXISTS contracts (
    contract_id TEXT PRIMARY KEY, campaign_id TEXT, creator_id TEXT,
    source_file TEXT, source_page INTEGER, agreed_fee REAL, currency TEXT,
    deadline TEXT, deliverables_json TEXT, extraction_confidence REAL,
    match_confidence REAL, match_method TEXT, match_reason TEXT
);
CREATE TABLE IF NOT EXISTS deliverables (
    deliverable_id TEXT PRIMARY KEY, campaign_id TEXT, creator_id TEXT,
    content_id TEXT, platform TEXT, content_type TEXT, required INTEGER,
    published_at TEXT, approval_status TEXT, source_file TEXT
);
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id TEXT PRIMARY KEY, invoice_number TEXT, campaign_id TEXT,
    creator_id TEXT, source_file TEXT, source_page INTEGER, amount REAL,
    currency TEXT, invoice_date TEXT, due_date TEXT, tax REAL, commission REAL,
    extraction_confidence REAL, match_confidence REAL, match_method TEXT,
    match_reason TEXT
);
CREATE TABLE IF NOT EXISTS payouts (
    payout_id TEXT PRIMARY KEY, invoice_id TEXT, invoice_number TEXT,
    creator_id TEXT, amount REAL, currency TEXT, payment_date TEXT,
    status TEXT, source_file TEXT
);
CREATE TABLE IF NOT EXISTS analytics_records (
    analytics_id TEXT PRIMARY KEY, campaign_id TEXT, creator_id TEXT,
    content_id TEXT, platform TEXT, content_type TEXT, publish_date TEXT,
    views INTEGER, reach INTEGER, impressions INTEGER, likes INTEGER,
    comments INTEGER, saves INTEGER, shares INTEGER, watch_time REAL,
    captured_at TEXT, source_file TEXT, source_type TEXT, confidence REAL,
    needs_verification INTEGER
);
CREATE TABLE IF NOT EXISTS exceptions (
    exception_id TEXT PRIMARY KEY, campaign_id TEXT, creator_id TEXT,
    content_id TEXT, exception_type TEXT, severity TEXT, description TEXT,
    expected_value TEXT, actual_value TEXT, evidence_json TEXT,
    source_files TEXT, status TEXT, created_at TEXT, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS file_uploads (
    filename TEXT, category TEXT, file_type TEXT, status TEXT,
    records_extracted INTEGER, warnings TEXT, processed_at TEXT
);
"""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    p = str(db_path or settings.db_path)
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def reset_data(conn: sqlite3.Connection) -> None:
    """Wipe all rows (fresh demo load)."""
    for t in ("campaigns", "creators", "contracts", "deliverables", "invoices",
              "payouts", "analytics_records", "exceptions", "file_uploads"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


# ----------------------------------------------------------------- writers

def upsert_campaign(conn, c) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO campaigns VALUES (?,?,?,?,?,?,?,?)",
        (c.campaign_id, c.client_name, c.campaign_name,
         str(c.start_date) if c.start_date else None,
         str(c.end_date) if c.end_date else None,
         c.currency, json.dumps(c.platforms), str(c.created_at)),
    )


def upsert_creator(conn, cr) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO creators VALUES (?,?,?,?,?)",
        (cr.creator_id, cr.canonical_name, cr.instagram_handle,
         cr.tiktok_handle, cr.email),
    )


def insert_contract(conn, ct) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ct.contract_id, ct.campaign_id, ct.creator_id, ct.source_file,
         ct.source_page, ct.agreed_fee, ct.currency, ct.deadline,
         json.dumps(ct.deliverables_json), ct.extraction_confidence,
         ct.match_confidence, ct.match_method, ct.match_reason),
    )


def insert_invoice(conn, iv) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (iv.invoice_id, iv.invoice_number, iv.campaign_id, iv.creator_id,
         iv.source_file, iv.source_page, iv.amount, iv.currency,
         iv.invoice_date, iv.due_date, iv.tax, iv.commission,
         iv.extraction_confidence, iv.match_confidence, iv.match_method,
         iv.match_reason),
    )


def insert_payout(conn, py) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO payouts VALUES (?,?,?,?,?,?,?,?,?)",
        (py.payout_id, py.invoice_id, py.invoice_number, py.creator_id,
         py.amount, py.currency, py.payment_date, py.status, py.source_file),
    )


def insert_deliverable(conn, dv) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO deliverables VALUES (?,?,?,?,?,?,?,?,?,?)",
        (dv.deliverable_id, dv.campaign_id, dv.creator_id, dv.content_id,
         dv.platform, dv.content_type, int(dv.required), dv.published_at,
         dv.approval_status, dv.source_file),
    )


def insert_analytics(conn, ar) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO analytics_records VALUES (?,?,?,?,?,?,?,?,?,?,?,"
        "?,?,?,?,?,?,?,?,?,?,?,?)",
        (ar.analytics_id, ar.campaign_id, ar.creator_id, ar.content_id,
         ar.platform, ar.content_type, ar.publish_date, ar.views, ar.reach,
         ar.impressions, ar.likes, ar.comments, ar.saves, ar.shares,
         ar.watch_time, ar.captured_at, ar.source_file, ar.source_type,
         ar.confidence, int(ar.needs_verification)),
    )


def insert_exception(conn, ex) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO exceptions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ex.exception_id, ex.campaign_id, ex.creator_id, ex.content_id,
         ex.exception_type, ex.severity, ex.description,
         json.dumps(ex.expected_value), json.dumps(ex.actual_value),
         json.dumps(ex.evidence, default=str), json.dumps(ex.source_files),
         ex.status, str(ex.created_at),
         str(ex.resolved_at) if ex.resolved_at else None),
    )


def set_exception_status(conn, exception_id: str, status: str) -> None:
    from datetime import datetime

    resolved = datetime.utcnow().isoformat() if status == "RESOLVED" else None
    conn.execute(
        "UPDATE exceptions SET status = ?, resolved_at = COALESCE(?, resolved_at) "
        "WHERE exception_id = ?",
        (status, resolved, exception_id),
    )
    conn.commit()


def record_upload(conn, filename: str, category: str, file_type: str,
                  status: str, records: int, warnings: list[str]) -> None:
    from datetime import datetime

    conn.execute(
        "INSERT INTO file_uploads VALUES (?,?,?,?,?,?,?)",
        (filename, category, file_type, status, records,
         "; ".join(warnings), datetime.utcnow().isoformat(timespec="seconds")),
    )
    conn.commit()


def persist_result(conn, result) -> None:
    """Persist a full PipelineResult."""
    reset_data(conn)
    if result.campaign:
        upsert_campaign(conn, result.campaign)
    for cr in result.creators.values():
        upsert_creator(conn, cr)
    for ct in result.contracts:
        insert_contract(conn, ct)
    for iv in result.invoices:
        insert_invoice(conn, iv)
    for py in result.payouts:
        insert_payout(conn, py)
    for dv in result.deliverables:
        insert_deliverable(conn, dv)
    for ar in result.analytics:
        insert_analytics(conn, ar)
    for ex in result.exceptions:
        insert_exception(conn, ex)
    conn.commit()
