"""Financials page: contract ↔ invoice ↔ payout reconciliation view."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from reporting import metrics
from ui.common import badge, empty_state, fmt_money, kpi_row, needs_data


def render(conn):
    st.title("💵 Financial Reconciliation")
    if needs_data(conn):
        empty_state("No financial records loaded yet.")
        return

    t = metrics.campaign_totals(conn)
    kpi_row([
        ("Contracted", fmt_money(t["contracted_fees"]), "Sum of agreed fees"),
        ("Invoiced", fmt_money(t["invoiced"]), "Sum of invoice amounts"),
        ("Paid", fmt_money(t["paid"]), "Completed payouts only"),
        ("Outstanding", fmt_money(t["outstanding"]), "Invoiced − paid"),
    ])

    rows = metrics.financial_table(conn)
    df = pd.DataFrame([{
        "Creator": r["creator"],
        "Contract": fmt_money(r["contract_fee"]),
        "Invoice": fmt_money(r["invoice"]),
        "Payout": fmt_money(r["payout"]),
        "Variance": fmt_money(r["variance"]),
        "Outstanding": fmt_money(r["outstanding"]),
        "Status": r["status"],
    } for r in rows])

    # make discrepancies visually obvious
    def _row_style(status):
        if status in ("REVIEW REQUIRED", "PAYOUT VARIANCE"):
            return "background-color:#fdecea;font-weight:600"
        if status in ("UNDER-BILLED", "PENDING PAYMENT"):
            return "background-color:#fef5e7"
        return ""

    disp = df.copy()
    disp["Status"] = disp["Status"].map(badge)
    html = (disp.style
            .apply(lambda row: [_row_style(rows[i]["status"])] * len(disp.columns),
                   axis=1)
            .to_html(index=False)) if hasattr(disp, "style") else disp.to_html(index=False)
    st.markdown(html, unsafe_allow_html=True)

    st.divider()
    st.subheader("Document-level detail")
    fin_ex = conn.execute(
        "SELECT e.*, c.canonical_name FROM exceptions e "
        "LEFT JOIN creators c ON c.creator_id = e.creator_id "
        "WHERE e.exception_type IN ('PAYMENT_VARIANCE','PAYOUT_VARIANCE',"
        "'INVOICE_UNDERBILLED','PAYMENT_PENDING','DUPLICATE_INVOICE') "
        "ORDER BY e.severity").fetchall()
    if not fin_ex:
        st.success("No open financial exceptions.")
    else:
        for e in fin_ex:
            with st.expander(
                    f"{badge(e['severity'])} &nbsp; {e['exception_type']} — "
                    f"{e['canonical_name'] or '(unmatched)'} · {e['status']}",
                    expanded=False):
                st.markdown(f"**{e['description']}**")
                st.json(__import__("json").loads(e["evidence_json"] or "{}"))
                st.caption(f"Expected: {e['expected_value']} · "
                           f"Actual: {e['actual_value']}")
                st.caption(f"Source files: {e['source_files']}")

    st.caption("All amounts above are produced by the deterministic reconciliation "
               "engine — never by an LLM.")
