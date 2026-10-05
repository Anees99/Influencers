"""Exceptions queue: filters, evidence drill-down, status workflow."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from database import db
from ui.common import badge, empty_state, needs_data

STATUS_OPTIONS = ["OPEN", "IN_REVIEW", "RESOLVED", "IGNORED"]


def render(conn):
    st.title("⚠️ Exception Queue")
    if needs_data(conn):
        empty_state("No exceptions — load a campaign first.")
        return

    rows = conn.execute(
        "SELECT e.*, c.canonical_name FROM exceptions e "
        "LEFT JOIN creators c ON c.creator_id = e.creator_id "
        "ORDER BY CASE e.severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END, "
        "e.exception_type").fetchall()

    open_n = sum(1 for r in rows if r["status"] in ("OPEN", "IN_REVIEW"))
    st.caption(f"**{len(rows)}** exceptions detected · **{open_n}** awaiting action. "
               "Nothing here was decided by an LLM — every flag is rule-based and "
               "traceable to source files.")

    f1, f2, f3, f4 = st.columns(4)
    sev = f1.multiselect("Severity", ["HIGH", "MEDIUM", "LOW"],
                         ["HIGH", "MEDIUM", "LOW"])
    typ = f2.multiselect("Type", sorted({r["exception_type"] for r in rows}))
    cre = f3.multiselect("Creator",
                         sorted({r["canonical_name"] for r in rows if r["canonical_name"]}))
    sta = f4.multiselect("Status", STATUS_OPTIONS, ["OPEN", "IN_REVIEW"])

    filtered = [r for r in rows
                if (not sev or r["severity"] in sev)
                and (not typ or r["exception_type"] in typ)
                and (not cre or (r["canonical_name"] or "(unmatched)") in cre)
                and (not sta or r["status"] in sta)]

    df = pd.DataFrame([{
        "Severity": r["severity"], "Type": r["exception_type"],
        "Creator": r["canonical_name"] or "(unmatched)",
        "Description": r["description"], "Status": r["status"],
        "ID": r["exception_id"]} for r in filtered])
    if df.empty:
        st.info("No exceptions match the current filters.")
        return
    disp = df.drop(columns=["ID"]).copy()
    disp["Severity"] = disp["Severity"].map(badge)
    disp["Status"] = disp["Status"].map(badge)
    st.markdown(disp.to_html(index=False, border=0, escape=False),
                unsafe_allow_html=True)

    st.divider()
    st.subheader("Open an exception to see the evidence trail")
    labels = {f"[{r['severity']}] {r['exception_type']} — "
              f"{r['canonical_name'] or '(unmatched)'} · {r['status']}": r
              for r in filtered}
    pick = st.selectbox("Exception", list(labels))
    e = labels[pick]

    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"##### {badge(e['severity'])} &nbsp; `{e['exception_type']}`")
        st.markdown(f"**{e['description']}**")
        ev = json.loads(e["evidence_json"] or "{}")
        if ev:
            st.markdown("**Evidence**")
            st.table(pd.DataFrame({"Field": list(ev.keys()),
                                   "Value": [str(v) for v in ev.values()]}))
        st.markdown(
            f"**Expected:** `{e['expected_value']}`  \n"
            f"**Actual:** `{e['actual_value']}`")
        srcs = json.loads(e["source_files"] or "[]")
        if srcs:
            st.markdown("**Source files:** " + " · ".join(f"`{s}`" for s in srcs))
        if e["content_id"]:
            st.markdown(f"**Content ID:** `{e['content_id']}`")
    with c2:
        st.markdown("**Workflow**")
        st.markdown(f"Current status: {badge(e['status'])}")
        new_status = st.selectbox("Change status", STATUS_OPTIONS,
                                  index=STATUS_OPTIONS.index(e["status"]),
                                  key=f"st_{e['exception_id']}")
        if st.button("💾 Update status", key=f"btn_{e['exception_id']}"):
            db.set_exception_status(conn, e["exception_id"], new_status)
            st.success(f"Marked {new_status}.")
            st.rerun()
        if e["resolved_at"]:
            st.caption(f"Resolved at {e['resolved_at']}")
