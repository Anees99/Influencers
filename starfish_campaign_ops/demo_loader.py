"""One-click demo loader: collect every file in demo_data/ and run the full
deterministic pipeline, persisting the result to SQLite.

Used by the Streamlit UI ("Load Demo Campaign") and by tests. No LLM calls.
"""
from __future__ import annotations

from pathlib import Path

from config.settings import settings
from database import db
from ingestion.router import guess_category
from reconciliation.engine import build_result
from schemas.campaign import Campaign
from schemas.creator import Creator

CAMPAIGN_ID = "CMP-RAMADAN-26"

# canonical roster (same people the generator creates files for)
ROSTER = [
    Creator(creator_id="ST-001", canonical_name="Sara Ahmed", instagram_handle="@sara.ahmed"),
    Creator(creator_id="ST-002", canonical_name="Omar Ali", instagram_handle="@omar.ali"),
    Creator(creator_id="ST-003", canonical_name="Lina Hassan", instagram_handle="@lina.hassan"),
    Creator(creator_id="ST-004", canonical_name="Youssef Karim", instagram_handle="@youssefk"),
    Creator(creator_id="ST-005", canonical_name="Nour El-Sayed", instagram_handle="@nour.elsayed"),
    Creator(creator_id="ST-006", canonical_name="Maya Farouk", instagram_handle="@maya.farouk"),
    Creator(creator_id="ST-007", canonical_name="Hana Mostafa", instagram_handle="@hana.mostafa"),
    Creator(creator_id="ST-008", canonical_name="Rana Khalil", instagram_handle="@rana.khalil"),
    Creator(creator_id="ST-009", canonical_name="Dina Fathy", instagram_handle="@dina.fathy"),
    Creator(creator_id="ST-010", canonical_name="Salma Adel", instagram_handle="@salma.adel"),
    Creator(creator_id="ST-011", canonical_name="Aya Rahman", instagram_handle="@aya.rahman"),
    Creator(creator_id="ST-012", canonical_name="Karim Nasser", instagram_handle="@karim.nasser"),
]


def _category_for(path: Path) -> str | None:
    if path.parent.name == "contracts":
        return "Contract"
    if path.parent.name == "invoices":
        return "Invoice"
    if path.parent.name == "screenshots":
        return None  # skip sidecars; png handled below
    return guess_category(path.name, path.suffix.lstrip("."))


def collect_demo_files(base: Path | None = None) -> tuple[list[tuple[str, bytes, str]], dict]:
    """Return (files, sidecars) for everything under demo_data/."""
    base = base or settings.demo_data_dir
    files: list[tuple[str, bytes, str]] = []
    sidecars: dict[str, dict] = {}
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() == ".py" or "__pycache__" in str(path):
            continue
        if path.suffix.lower() == ".json" and path.parent.name == "screenshots":
            continue  # sidecar, attached to its png below
        cat = _category_for(path)
        if cat is None:
            continue
        blob = path.read_bytes()
        files.append((path.name, blob, cat))
        if cat == "Screenshot":
            side = path.with_suffix(".json")
            if side.exists():
                import json
                sidecars[path.name] = json.loads(side.read_text())
    return files, sidecars


def load_demo(db_path: Path | str | None = None):
    """Run the deterministic pipeline over demo_data/ and persist to SQLite."""
    files, sidecars = collect_demo_files()
    campaign = Campaign(
        campaign_id=CAMPAIGN_ID, client_name="ABC Beauty",
        campaign_name="Ramadan Skincare Campaign",
        start_date=None, end_date=None, currency="USD",
        platforms=["Instagram", "TikTok"])
    result = build_result(files, ROSTER, campaign, sidecars)
    conn = db.connect(db_path or settings.db_path)
    try:
        db.init_db(conn)
        db.persist_result(conn, result)
        for fr in result.file_results:
            db.record_upload(conn, fr.filename, fr.category, fr.file_type,
                             fr.status, fr.records_extracted,
                             ([fr.error] if fr.error else []) + list(fr.warnings))
    finally:
        conn.close()
    return result
