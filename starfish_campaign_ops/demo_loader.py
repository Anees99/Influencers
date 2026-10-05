"""One-click demo loader: collect every file in a dataset folder (input_data/,
input_data2/, ... or legacy demo_data/) and run the full deterministic
pipeline, persisting the result to SQLite.

Used by the Streamlit UI ("Load Demo Campaign") and by tests. No LLM calls.
"""
from __future__ import annotations

import json
from pathlib import Path

from config.settings import settings
from database import db
from datasets import DEFAULT_DATASET, DATASETS, brief_overrides, get_dataset
from ingestion.router import guess_category
from reconciliation.engine import build_result
from schemas.campaign import Campaign
from schemas.creator import Creator

CAMPAIGN_ID = DATASETS[DEFAULT_DATASET].campaign_id

# Back-compat: default roster (Ramadan campaign). Prefer load_demo(dataset=...).
ROSTER = list(DATASETS[DEFAULT_DATASET].roster)


def _resolve_base(base: Path | str | None, dataset: str | None) -> tuple[Path, object]:
    """Map a dataset key / explicit path to (folder, Dataset)."""
    ds = get_dataset(dataset)
    if isinstance(base, Path) or (isinstance(base, str) and base):
        p = Path(base)
        # legacy callers pass demo_data/ — treat it as the default dataset
        if p.name == "demo_data":
            return ds.directory, ds
        return p, ds
    return ds.directory, ds


def _category_for(path: Path) -> str | None:
    if path.parent.name == "contracts":
        return "Contract"
    if path.parent.name == "invoices":
        return "Invoice"
    if path.parent.name == "screenshots":
        # PNG/JPG screenshots are ingested; .json sidecars attach to them.
        if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
            return "Screenshot"
        return None
    return guess_category(path.name, path.suffix.lstrip("."))


def collect_demo_files(base: Path | None = None,
                       dataset: str | None = None) -> tuple[list[tuple[str, bytes, str]], dict]:
    """Return (files, sidecars) for everything in the dataset folder."""
    base, _ds = _resolve_base(base, dataset)
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
                sidecars[path.name] = json.loads(side.read_text())
    return files, sidecars


def load_demo(db_path: Path | str | None = None,
              dataset: str | None = None):
    """Run the deterministic pipeline over a dataset folder and persist to SQLite.

    `dataset` is a folder key registered in datasets.DATASETS (e.g.
    "input_data2").  The stored campaign metadata comes from the dataset and
    is overridden by campaign_brief.xlsx inside the folder when present.
    """
    base, ds = _resolve_base(None, dataset)
    files, sidecars = collect_demo_files(base)
    meta = {"campaign_id": ds.campaign_id, "client_name": ds.client_name,
            "campaign_name": ds.campaign_name}
    meta.update(brief_overrides(base))
    campaign = Campaign(
        campaign_id=meta["campaign_id"], client_name=meta["client_name"],
        campaign_name=meta["campaign_name"],
        start_date=None, end_date=None, currency="USD",
        platforms=["Instagram", "TikTok"])
    result = build_result(files, list(ds.roster), campaign, sidecars)
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
