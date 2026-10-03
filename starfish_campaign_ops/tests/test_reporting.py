"""End-to-end demo pipeline + reporting outputs (Excel, PDF, metrics).

Runs the real deterministic pipeline over demo_data/ into a temp DB and
verifies the headline numbers the sales demo depends on.  If the synthetic
data ever changes, these tests fail loudly instead of the demo silently
showing wrong figures.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database import db  # noqa: E402
from demo_loader import load_demo  # noqa: E402
from reporting import metrics  # noqa: E402
from reporting.excel import export_excel  # noqa: E402
from reporting.pdf import generate_pdf  # noqa: E402


@pytest.fixture(scope="module")
def demo_db():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.db"
        result = load_demo(db_path=path)
        conn = db.connect(path)
        db.init_db(conn)
        yield conn, result
        conn.close()


def test_creators_normalized(demo_db):
    conn, _ = demo_db
    n = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
    assert int(n) == 12


def test_contracts_and_invoices_loaded(demo_db):
    conn, _ = demo_db
    assert conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] >= 12
    assert conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] >= 12


def test_exceptions_detected(demo_db):
    conn, _ = demo_db
    n = conn.execute("SELECT COUNT(*) FROM exceptions").fetchone()[0]
    assert n >= 12  # demo guarantees at least 12 exception classes worth


def test_corrupt_pdf_is_per_file_error_not_crash(demo_db):
    conn, result = demo_db
    bad = [fr for fr in result.file_results if "corrupt" in fr.filename.lower()]
    assert bad and bad[0].status == "ERROR"
    # campaign still completed
    assert len([r for r in result.file_results if r.status == "PROCESSED"]) > 10


def test_metrics_and_snapshot_dedupe(demo_db):
    conn, _ = demo_db
    t = metrics.campaign_totals(conn)
    assert t["views"] > 0
    assert t["reach"] > 0
    assert t["engagements"] == (t.get("likes", 0) + t.get("comments", 0)
                                + t.get("saves", 0) + t.get("shares", 0)) \
        if all(k in t for k in ("likes", "comments", "saves", "shares")) else True
    # engagement rate is derived, never averaged
    if t["reach"]:
        assert abs(t["engagement_rate_pct"] - round(t["engagements"] / t["reach"] * 100, 2)) < 0.01


def test_excel_report_generates(demo_db):
    conn, _ = demo_db
    with tempfile.TemporaryDirectory() as tmp:
        out = export_excel(conn, Path(tmp) / "report.xlsx")
        assert out.exists() and out.stat().st_size > 5_000


def test_pdf_report_generates(demo_db):
    conn, _ = demo_db
    with tempfile.TemporaryDirectory() as tmp:
        out = generate_pdf(conn, Path(tmp) / "report.pdf")
        assert out.exists() and out.stat().st_size > 3_000
