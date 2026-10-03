"""Deliverables page: contracted vs published reconciliation per creator."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from reporting import metrics
from ui.common import empty_state, needs_data


def render(conn):
    st.title("📦 Deliverable Reconciliation")
    if needs_data():
        empty_state("No deliverables loaded yet.")
        return

    rows = metrics.deliverable_table(conn)
    df = pd.DataFrame([{
        "Creator": r["creator"], "Required": r["required"],
        "Published": r["published"], "Missing": r["missing"],
        "Late": r["late"], "Approval Statuses": r["approval_statuses"],
        "Contract Source": r["source_file"]} for r in rows])

    def _style(row):
        color = ""
        if row["Missing"] > 0:
            color = "background-color:#fdecea;font-weight:600"
        elif row["Late"] > 0:
            color = "background-color:#fef5e7"
        return [color] * len(row)

    st.dataframe(df.style.apply(_style, axis=1), use_container_width=True,
                 hide_index=True)

    tot_req = int(df["Required"].sum())
    tot_pub = int(df["Published"].sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Required", tot_req)
    c2.metric("Published", tot_pub)
    c3.metric("Missing", tot_req - tot_pub)
    c4.metric("Late", int(df["Late"].sum()))

    st.divider()
    st.subheader("Tracker detail (per content item)")
    d = conn.execute(
        "SELECT d.*, c.canonical_name FROM deliverables d "
        "LEFT JOIN creators c ON c.creator_id = d.creator_id "
        "ORDER BY c.canonical_name, d.content_id").fetchall()
    td = pd.DataFrame([{
        "Creator": x["canonical_name"] or "(unmatched)",
        "Content ID": x["content_id"] or "-", "Platform": x["platform"],
        "Type": x["content_type"], "Required": bool(x["required"]),
        "Published": x["published_at"] or "— not published —",
        "Approval": x["approval_status"] or "-",
        "Source": x["source_file"]} for x in d])
    st.dataframe(td, use_container_width=True, hide_index=True)
    st.caption("Late = published after the contract deadline. Missing = contracted "
               "item with no publication record. Rules applied deterministically by "
               "the reconciliation engine.")
