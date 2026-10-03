"""Shared Streamlit UI helpers: metric cards, badges, formatting."""
from __future__ import annotations

import pandas as pd
import streamlit as st

SEVERITY_COLORS = {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#2980b9"}
STATUS_COLORS = {
    "PAID": "#1e8449", "OK": "#1e8449",
    "REVIEW REQUIRED": "#c0392b", "PAYOUT VARIANCE": "#c0392b",
    "UNDER-BILLED": "#e67e22", "PENDING PAYMENT": "#e67e22",
    "NOT INVOICED": "#7f8c8d",
    "OPEN": "#c0392b", "IN_REVIEW": "#e67e22",
    "RESOLVED": "#1e8449", "IGNORED": "#7f8c8d",
    "PROCESSED": "#1e8449", "ERROR": "#c0392b",
}


def fmt_int(v) -> str:
    if v is None:
        return "-"
    return f"{int(v):,}"


def fmt_money(v) -> str:
    if v is None:
        return "-"
    return f"${v:,.0f}" if float(v) == int(float(v)) else f"${v:,.2f}"


def fmt_compact(v) -> str:
    """2,943,700 -> 2.94M (display only; underlying values never change)."""
    if v is None:
        return "-"
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.1f}K"
    return f"{v:,.0f}"


def badge(text: str) -> str:
    color = STATUS_COLORS.get(str(text).upper(), "#555555")
    return (f"<span style='background:{color};color:white;padding:2px 10px;"
            f"border-radius:12px;font-size:0.78rem;font-weight:600;'>"
            f"{text}</span>")


def kpi_row(items: list[tuple[str, str, str]]):
    """items: [(label, value, help)] rendered as equal-width metric cards."""
    cols = st.columns(max(len(items), 1))
    for col, (label, value, help_txt) in zip(cols, items):
        with col:
            st.metric(label, value, help=help_txt or None)


def empty_state(message: str) -> None:
    st.info(f"⚪ {message}")
    st.caption("Use **Home → Load Demo Campaign** to populate the workspace.")


def needs_data() -> bool:
    conn = st.session_state.get("conn")
    if conn is None:
        return True
    try:
        n = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
    except Exception:
        return True
    return n == 0


def styled_table(df: pd.DataFrame, use_html_cols: tuple[str, ...] = ()) -> str:
    """Render a DataFrame as an HTML table with right-aligned numerics."""
    return df.to_html(index=False, border=0, classes="sf-table",
                       escape=not use_html_cols, na_rep="-")
