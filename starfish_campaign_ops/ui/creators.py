"""Creators page: normalized roster + per-creator campaign record."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from reporting import metrics
from ui.common import badge, empty_state, fmt_money, needs_data


def render(conn):
    st.title("👥 Creators")
    if needs_data():
        empty_state("No creators loaded yet.")
        return

    perf = {p["creator_id"]: p for p in metrics.creator_performance(conn)}
    fin = {f["creator_id"]: f for f in metrics.financial_table(conn)}
    deliv = {d["creator_id"]: d for d in metrics.deliverable_table(conn)}

    rows = conn.execute("SELECT * FROM creators ORDER BY canonical_name").fetchall()
    exc_count = {r["creator_id"]: r["c"] for r in conn.execute(
        "SELECT creator_id, COUNT(*) c FROM exceptions "
        "WHERE status IN ('OPEN','IN_REVIEW') GROUP BY creator_id")}

    table = []
    for r in rows:
        cid = r["creator_id"]
        p = perf.get(cid, {})
        f = fin.get(cid, {})
        d = deliv.get(cid, {})
        table.append({
            "Creator": r["canonical_name"],
            "ID": cid,
            "Instagram": r["instagram_handle"] or "-",
            "Deliverables": f"{d.get('published', 0)}/{d.get('required', 0)}",
            "Views": p.get("views"),
            "Reach": p.get("reach"),
            "Engagements": p.get("engagements"),
            "Contract": fmt_money(f.get("contract_fee")),
            "Invoice": fmt_money(f.get("invoice")),
            "Payout": fmt_money(f.get("payout")),
            "Payment Status": f.get("status", "-"),
            "Exceptions": exc_count.get(cid, 0),
        })
    df = pd.DataFrame(table)
    disp = df.copy()
    for c in ("Views", "Reach", "Engagements"):
        disp[c] = disp[c].map(lambda v: f"{v:,}" if pd.notna(v) and v is not None else "-")
    disp["Payment Status"] = disp["Payment Status"].map(badge)
    st.markdown(disp.to_html(index=False, border=0, escape=False),
                unsafe_allow_html=True)

    st.divider()
    st.subheader("Creator profile")
    names = {r["canonical_name"]: r["creator_id"] for r in rows}
    pick = st.selectbox("Select a creator", sorted(names))
    cid = names[pick]

    tabs = st.tabs(["📦 Deliverables", "📈 Performance", "💵 Financials",
                    "⚠️ Exceptions", "🧾 Identity & Match"])
    with tabs[0]:
        d = pd.DataFrame([{
            "Content ID": x["content_id"] or "-", "Platform": x["platform"],
            "Type": x["content_type"], "Required": bool(x["required"]),
            "Published": x["published_at"] or "— not published —",
            "Approval": x["approval_status"] or "-", "Source": x["source_file"],
        } for x in conn.execute(
            "SELECT * FROM deliverables WHERE creator_id=? ORDER BY content_id",
            (cid,)).fetchall()])
        if d.empty:
            st.info("No deliverable tracker rows for this creator.")
        else:
            st.dataframe(d, use_container_width=True, hide_index=True)
    with tabs[1]:
        cp = [c for c in metrics.content_performance(conn) if c["creator"] == pick]
        d = pd.DataFrame(cp)
        if d.empty:
            st.info("No analytics snapshots linked to this creator.")
        else:
            st.dataframe(d, use_container_width=True, hide_index=True)
    with tabs[2]:
        f = fin.get(cid, {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Contracted", fmt_money(f.get("contract_fee")))
        c2.metric("Invoiced", fmt_money(f.get("invoice")))
        c3.metric("Paid", fmt_money(f.get("payout")))
        c4.metric("Variance", fmt_money(f.get("variance")))
        inv_rows = pd.DataFrame([{
            "Invoice #": x["invoice_number"], "Amount": x["amount"],
            "Date": x["invoice_date"], "Due": x["due_date"],
            "Source": x["source_file"]}
            for x in conn.execute(
                "SELECT * FROM invoices WHERE creator_id=?", (cid,)).fetchall()])
        pay_rows = pd.DataFrame([{
            "Payout #": x["payout_id"], "Invoice ref": x["invoice_number"],
            "Amount": x["amount"], "Date": x["payment_date"],
            "Status": x["status"], "Source": x["source_file"]}
            for x in conn.execute(
                "SELECT * FROM payouts WHERE creator_id=?", (cid,)).fetchall()])
        st.markdown("**Invoices**"); st.dataframe(inv_rows, use_container_width=True,
                                                 hide_index=True)
        st.markdown("**Payouts**"); st.dataframe(pay_rows, use_container_width=True,
                                                 hide_index=True)
    with tabs[3]:
        ex = pd.DataFrame([{
            "Severity": x["severity"], "Type": x["exception_type"],
            "Description": x["description"], "Status": x["status"],
            "Sources": x["source_files"]}
            for x in conn.execute(
                "SELECT * FROM exceptions WHERE creator_id=? "
                "AND status IN ('OPEN','IN_REVIEW')", (cid,)).fetchall()])
        if ex.empty:
            st.success("No open exceptions for this creator.")
        else:
            ex["Severity"] = ex["Severity"].map(badge)
            st.markdown(ex.to_html(index=False, border=0, escape=False),
                        unsafe_allow_html=True)
    with tabs[4]:
        cr = conn.execute("SELECT * FROM creators WHERE creator_id=?", (cid,)).fetchone()
        st.json({
            "creator_id": cr["creator_id"],
            "canonical_name": cr["canonical_name"],
            "instagram_handle": cr["instagram_handle"],
            "tiktok_handle": cr["tiktok_handle"],
            "email": cr["email"],
        })
        matches = pd.DataFrame([{
            "Record type": kind, "Source file": x["source_file"],
            "Match method": x["match_method"] or "-",
            "Confidence": f"{(x['match_confidence'] or 0):.0%}",
            "Reason": x["match_reason"] or "-"}
            for kind, q in (("contract", "SELECT * FROM contracts WHERE creator_id=?"),
                           ("invoice", "SELECT * FROM invoices WHERE creator_id=?"))
            for x in conn.execute(q, (cid,)).fetchall()])
        st.caption("Every record bound to this creator carries its match method and "
                   "confidence — low-confidence links are never merged silently.")
        st.dataframe(matches, use_container_width=True, hide_index=True)
