"""Operations dashboard: campaign KPIs + exception breakdown."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from reporting import metrics
from ui.common import empty_state, fmt_compact, fmt_money, kpi_row, needs_data


def render(conn):
    st.title("📊 Operations Dashboard")
    if needs_data():
        empty_state("No campaign loaded yet.")
        return

    camp = conn.execute("SELECT * FROM campaigns LIMIT 1").fetchone()
    t = metrics.campaign_totals(conn)
    st.caption(f"**{camp['client_name']}** — {camp['campaign_name']} · "
               f"{camp['currency']} · reconciled from source files")

    # ---------------------------------------------------------------- KPIs
    kpi_row([
        ("Creators", str(t["creators"]), "Normalized creator records"),
        ("Deliverables Required", str(t["deliverables_required"]),
         "Items contracted across all creators"),
        ("Deliverables Completed", str(t["deliverables_published"]),
         "Confirmed published in deliverable tracker"),
        ("Views", fmt_compact(t["views"]), "Latest snapshot per content piece"),
        ("Reach", fmt_compact(t["reach"]), "Latest snapshot per content piece"),
        ("Engagements", fmt_compact(t["engagements"]),
         "likes + comments + saves + shares"),
        ("Engagement Rate",
         f"{t['engagement_rate_pct']}%" if t["engagement_rate_pct"] is not None else "n/a",
         "engagements / reach × 100"),
    ])
    kpi_row([
        ("Contracted", fmt_money(t["contracted_fees"]), "Sum of contract fees"),
        ("Invoiced", fmt_money(t["invoiced"]), "Sum of invoice amounts"),
        ("Paid", fmt_money(t["paid"]), "Completed payouts only"),
        ("Outstanding", fmt_money(t["outstanding"]), "Invoiced − paid"),
        ("Open Exceptions", str(t["open_exceptions"]),
         "Items requiring operator action"),
    ])

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Exceptions by severity")
        rows = conn.execute(
            "SELECT severity, COUNT(*) c FROM exceptions "
            "WHERE status IN ('OPEN','IN_REVIEW') GROUP BY severity").fetchall()
        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        df = pd.DataFrame([(r["severity"], r["c"]) for r in rows],
                          columns=["Severity", "Count"])
        if df.empty:
            st.success("No open exceptions 🎉")
        else:
            df["o"] = df["Severity"].map(order)
            df = df.sort_values("o")
            fig = px.bar(df, x="Severity", y="Count", color="Severity",
                         color_discrete_map={"HIGH": "#c0392b",
                                             "MEDIUM": "#e67e22",
                                             "LOW": "#2980b9"},
                         text="Count")
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False, height=280, margin=dict(l=0, r=0, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Exceptions by type")
        rows = conn.execute(
            "SELECT exception_type, COUNT(*) c FROM exceptions "
            "WHERE status IN ('OPEN','IN_REVIEW') GROUP BY exception_type "
            "ORDER BY c DESC").fetchall()
        df = pd.DataFrame([(r["exception_type"], r["c"]) for r in rows],
                          columns=["Type", "Count"])
        if not df.empty:
            fig = px.bar(df, x="Count", y="Type", orientation="h",
                         text="Count", color="Count",
                         color_continuous_scale="Oranges")
            fig.update_layout(showlegend=False, coloraxis_showscale=False,
                              height=280, margin=dict(l=0, r=0, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    st.divider()
    cols = st.columns(3)
    with cols[0]:
        st.subheader("Financial position")
        fin = pd.DataFrame({
            "Item": ["Contracted", "Invoiced", "Paid", "Outstanding"],
            "USD": [t["contracted_fees"], t["invoiced"], t["paid"], t["outstanding"]]})
        fig = px.bar(fin, x="USD", y="Item", orientation="h", text="USD",
                     color=fin["Item"] == "Outstanding",
                     color_discrete_map={False: "#1F6FB2", True: "#e67e22"})
        fig.update_layout(showlegend=False, height=240,
                          margin=dict(l=0, r=0, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with cols[1]:
        st.subheader("Content delivery")
        fig = px.bar(x=["Required", "Published"],
                     y=[t["deliverables_required"], t["deliverables_published"]],
                     labels={"x": "", "y": "Items"}, text="auto",
                     color=["Required", "Published"],
                     color_discrete_map={"Required": "#1F6FB2", "Published": "#1e8449"})
        fig.update_layout(showlegend=False, height=240,
                          margin=dict(l=0, r=0, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with cols[2]:
        st.subheader("Pipeline status")
        steps = [
            ("Files ingested", conn.execute(
                "SELECT COUNT(*) c FROM file_uploads").fetchone()["c"]),
            ("Contracts", conn.execute(
                "SELECT COUNT(*) c FROM contracts").fetchone()["c"]),
            ("Invoices", conn.execute(
                "SELECT COUNT(*) c FROM invoices").fetchone()["c"]),
            ("Payouts", conn.execute(
                "SELECT COUNT(*) c FROM payouts").fetchone()["c"]),
            ("Analytics snapshots", conn.execute(
                "SELECT COUNT(*) c FROM analytics_records").fetchone()["c"]),
        ]
        for label, n in steps:
            st.markdown(f"✅ **{label}** — {n}")
