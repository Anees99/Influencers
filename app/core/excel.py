"""Excel workbook generation for client delivery (deterministic, styled)."""
from __future__ import annotations

import io

import pandas as pd

from app.core.pipeline import PipelineResult


def exceptions_frame(result: PipelineResult) -> pd.DataFrame:
    rows = []
    for e in result.exceptions:
        rows.append({
            "Exception ID": e.exception_id,
            "Severity": e.severity.upper(),
            "Category": e.category,
            "Entity": e.entity,
            "Description": e.description,
            "Evidence": "; ".join(f"{k}={v}" for k, v in e.evidence.items()),
            "Status": e.status.capitalize(),
        })
    return pd.DataFrame(rows)


def _title_case(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).replace("_", " ").strip().title() for c in out.columns]
    return out


def build_workbook(result: PipelineResult) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        wb = xw.book
        header_fmt = wb.add_format({"bold": True, "bg_color": "#134E4A",
                                    "font_color": "white", "border": 1})

        def write(sheet: str, df: pd.DataFrame):
            df.to_excel(xw, sheet_name=sheet, index=False)
            ws = xw.sheets[sheet]
            for r, h in enumerate(df.columns):
                ws.write(0, r, str(h), header_fmt)
            for i, h in enumerate(df.columns):
                width = max(12, min(42, len(str(h)) + 4))
                if h and "evidence" in str(h).lower():
                    width = 60
                ws.set_column(i, i, width)
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 1))

        overview = pd.DataFrame([
            ["Campaign", "Starfish - Autumn Creator Program"],
            ["Reporting period", "September 2026"],
            ["Creators identified", result.creator_count],
            ["Contracts loaded", len(result.inputs.get("contracts", pd.DataFrame()))],
            ["Invoices loaded", len(result.inputs.get("invoices", pd.DataFrame()))],
            ["Payouts loaded", len(result.inputs.get("payouts", pd.DataFrame()))],
            ["Analytics rows (deduplicated)", len(result.analytics_deduped)],
            ["Contract vs invoice reconciliations matched",
             result.contracts_vs_invoices.summary.get("matched", 0)],
            ["Invoice vs payout reconciliations matched",
             result.invoices_vs_payouts.summary.get("matched", 0)],
            ["Deliverable checks passed", len(result.deliverables.matched)],
            ["Open exceptions", len(result.exceptions)],
            ["High severity exceptions",
             sum(1 for e in result.exceptions if e.severity == "high")],
        ], columns=["Metric", "Value"])
        write("Overview", overview)

        ci_rows = result.contracts_vs_invoices.matched + \
            result.contracts_vs_invoices.summary.get("rows", [])
        if ci_rows:
            write("Contract vs Invoice", _title_case(pd.DataFrame(ci_rows)))

        ip_rows = list(result.invoices_vs_payouts.matched)
        unpaid = [e.evidence for e in result.exceptions
                  if e.category in ("missing_payout", "payout_no_invoice")]
        if ip_rows:
            write("Invoice vs Payout", _title_case(pd.DataFrame(ip_rows)))
        if unpaid:
            write("Unpaid & Orphan Payments", pd.DataFrame(unpaid))

        dv_rows = result.deliverables.matched
        if dv_rows:
            write("Deliverables", _title_case(pd.DataFrame(dv_rows)))

        if len(result.creator_summary):
            cs = _title_case(result.creator_summary)
            write("Performance by Creator", cs)
            ws = xw.sheets["Performance by Creator"]
            money_fmt = wb.add_format({"num_format": "$#,##0.00"})
            pct_fmt = wb.add_format({"num_format": "0.0%"})
            cols = list(cs.columns)
            for name, fmt in (("Spend", money_fmt), ("Cpa", money_fmt),
                              ("Engagement Rate", pct_fmt)):
                if name in cols:
                    ci = cols.index(name)
                    for r in range(1, len(cs) + 1):
                        ws.write_number(r, ci, float(cs.iloc[r - 1][name] or 0), fmt)

        exc = exceptions_frame(result)
        write("Exceptions", exc if len(exc) else
              pd.DataFrame([{"Exception ID": "-", "Severity": "-", "Category": "None",
                             "Entity": "No exceptions found", "Description": "",
                             "Evidence": "", "Status": ""}]))

        write("Creator Roster", result.roster)

        # Raw inputs for full auditability
        for src in ("contracts", "invoices", "payouts", "analytics"):
            df = result.inputs.get(src)
            if df is not None and len(df):
                sheet = f"Raw {src.title()}"[:31]
                write(sheet, df)
    return buf.getvalue()
