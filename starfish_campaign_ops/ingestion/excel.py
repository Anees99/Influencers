"""XLSX ingestion (openpyxl via pandas) with the same canonical columns."""
from __future__ import annotations

import io

import pandas as pd

from ingestion.csv_ingest import COLUMN_ALIASES


class ExcelError(Exception):
    pass


def read_rows(blob: bytes, filename: str = "", sheet: int | str = 0) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    try:
        df = pd.read_excel(io.BytesIO(blob), sheet_name=sheet)
    except Exception as exc:
        raise ExcelError(f"{filename}: invalid or unreadable Excel file ({exc})") from exc
    df.columns = [str(c).strip().lower().replace("_", " ") for c in df.columns]
    df = df.rename(columns={c: COLUMN_ALIASES.get(c, c.replace(" ", "_")) for c in df.columns})
    df = df.loc[:, [c for c in df.columns if not c.startswith("unnamed")]]
    rows = []
    for i, (_, r) in enumerate(df.iterrows(), start=2):
        d = {k: (None if pd.isna(v) else (v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else
                                            v.item() if hasattr(v, "item") else
                                            (v.strip() if isinstance(v, str) else v)))
             for k, v in r.to_dict().items()}
        if all(v is None or str(v).strip() == "" for v in d.values()):
            warnings.append(f"row {i}: blank row skipped")
            continue
        rows.append(d)
    return rows, warnings
