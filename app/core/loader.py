"""Robust loading of uploaded campaign files (CSV / XLSX).

Every failure path raises LoadError with an actionable message so the UI
can surface it instead of crashing.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd


class LoadError(Exception):
    """Raised when a file cannot be loaded or is missing required columns."""


@dataclass
class LoadedFile:
    source: str            # logical source name, e.g. "contracts"
    filename: str
    df: pd.DataFrame
    row_count: int


REQUIRED_COLUMNS: dict[str, list[str]] = {
    "creators": ["creator_id", "name"],
    "contracts": ["contract_id", "creator", "deliverable", "amount"],
    "invoices": ["invoice_number", "creator", "amount", "period"],
    "payouts": ["payment_ref", "creator", "amount", "date"],
    "analytics": ["post_id", "creator", "platform", "impressions"],
}

# Column-name cleanup map applied to every sheet/file.
_ALIASES = {
    "creator name": "creator",
    "influencer": "creator",
    "influencer name": "creator",
    "handle": "creator",
    "username": "creator",
    "fee": "amount",
    "contract amount": "amount",
    "invoice amount": "amount",
    "gross amount": "amount",
    "paid amount": "amount",
    "payment amount": "amount",
    "total impressions": "impressions",
    "views": "impressions",
    "engagements total": "engagements",
    "clicks total": "clicks",
    "conversions tracked": "conversions",
    "spend usd": "spend",
    "published": "published_date",
    "live date": "published_date",
    "month": "period",
    "billing period": "period",
    "invoice no": "invoice_number",
    "invoice #": "invoice_number",
    "contract id ": "contract_id",
    "id": "creator_id",
    "post": "post_id",
    "url ": "url",
    "payment reference": "payment_ref",
    "payment ref ": "payment_ref",
    "txn id": "payment_ref",
}


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    new_cols = []
    for c in out.columns:
        key = str(c).strip().lower().replace("_", " ")
        key = " ".join(key.split())
        key = _ALIASES.get(key, key).strip().lower().replace(" ", "_")
        new_cols.append(key)
    out.columns = new_cols
    # Drop fully-empty unnamed index columns from Excel exports.
    out = out.loc[:, [c for c in out.columns if not c.startswith("unnamed")]]
    return out


def load_table(file_bytes: bytes | io.IOBase, filename: str, source: str) -> LoadedFile:
    name = str(filename)
    lower = name.lower()
    try:
        if lower.endswith(".csv"):
            df = pd.read_csv(file_bytes)
        elif lower.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file_bytes, sheet_name=0)
        else:
            raise LoadError(f"{name}: unsupported file type (use CSV or XLSX).")
    except LoadError:
        raise
    except Exception as exc:  # parse errors etc.
        raise LoadError(f"{name}: could not be parsed ({exc}).") from exc

    df = clean_columns(df)
    missing = [c for c in REQUIRED_COLUMNS.get(source, []) if c not in df.columns]
    if missing:
        raise LoadError(
            f"{name} ({source}): missing required column(s): {', '.join(missing)}. "
            f"Found: {', '.join(df.columns)}"
        )
    return LoadedFile(source=source, filename=name, df=df, row_count=len(df))


def detect_source(filename: str) -> str | None:
    """Infer logical source from the file name (first match wins)."""
    n = str(filename).lower()
    order = ["creators", "contracts", "invoices", "payouts", "analytics"]
    keywords = {
        "creators": ("creator", "roster"),
        "contracts": ("contract",),
        "invoices": ("invoice",),
        "payouts": ("payout", "payment"),
        "analytics": ("analytic", "performance", "metrics", "post"),
    }
    for src in order:
        if any(k in n for k in keywords[src]):
            return src
    return None
