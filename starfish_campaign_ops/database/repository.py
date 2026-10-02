"""Query API used by the UI and reporting layers."""
from __future__ import annotations

import sqlite3

from database import db
from database.models import (row_to_analytics, row_to_contract, row_to_creator,
                             row_to_deliverable, row_to_exception,
                             row_to_invoice, row_to_payout)


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        db.init_db(conn)

    # -- reads ----------------------------------------------------------
    def creators(self) -> list:
        rows = self.conn.execute("SELECT * FROM creators ORDER BY creator_id").fetchall()
        return [row_to_creator(r) for r in rows]

    def contracts(self) -> list:
        rows = self.conn.execute("SELECT * FROM contracts ORDER BY contract_id").fetchall()
        return [row_to_contract(r) for r in rows]

    def invoices(self) -> list:
        rows = self.conn.execute("SELECT * FROM invoices ORDER BY invoice_number").fetchall()
        return [row_to_invoice(r) for r in rows]

    def payouts(self) -> list:
        rows = self.conn.execute("SELECT * FROM payouts ORDER BY payout_id").fetchall()
        return [row_to_payout(r) for r in rows]

    def deliverables(self) -> list:
        rows = self.conn.execute("SELECT * FROM deliverables ORDER BY deliverable_id").fetchall()
        return [row_to_deliverable(r) for r in rows]

    def analytics(self) -> list:
        rows = self.conn.execute(
            "SELECT * FROM analytics_records ORDER BY content_id, captured_at").fetchall()
        return [row_to_analytics(r) for r in rows]

    def exceptions(self, status: str | None = None) -> list:
        q = "SELECT * FROM exceptions"
        args: tuple = ()
        if status:
            q += " WHERE status = ?"
            args = (status,)
        q += " ORDER BY CASE severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END, exception_id"
        return [row_to_exception(r) for r in self.conn.execute(q, args).fetchall()]

    def uploads(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM file_uploads ORDER BY processed_at").fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict:
        out = {}
        for t in ("campaigns", "creators", "contracts", "invoices", "payouts",
                  "deliverables", "analytics_records", "exceptions"):
            out[t] = self.conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        return out

    # -- writes -----------------------------------------------------------
    def persist(self, result) -> None:
        db.persist_result(self.conn, result)

    def set_exception_status(self, exception_id: str, status: str) -> None:
        db.set_exception_status(self.conn, exception_id, status)

    def record_upload(self, *a, **kw) -> None:
        db.record_upload(self.conn, *a, **kw)
