"""Performance page: campaign & creator analytics (computed from DB)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from reporting import metrics
from ui.common import empty_state, fmt_compact, kpi_row, needs_data


def render(conn):
    st.title("📈 Campaign Performance")
    if needs_data():
        empty_state("No analytics loaded yet.")
        return

    t = metrics.campaign_totals(conn)
    kpi_row([
        ("Total Views", fmt_compact(t["views"]), "Sum of latest snapshots"),
        ("Total Reach", fmt_compact(t["reach"]), "Sum of latest snapshots"),
        ("Impressions", fmt_compact(t["impressions"]), ""),
        ("Engagements", fmt_compact(t["engagements"]),
         "likes + comments + saves + shares"),
        ("Engagement Rate",
         f"{t['engagement_rate_pct']}%" if t["engagement_rate_pct"] is not None else "n/a",
         "engagements / reach × 100 — null when reach unavailable"),
        ("Content Tracked", str(t["content_count"]),
         "Unique posts after snapshot deduplication"),
    ])

    perf = metrics.creator_performance(conn)
    df = pd.DataFrame(perf)
    if df.empty:
        st.info("No analytics rows matched to creators.")
        return

    st.subheader("Views by creator")
    fig = px.bar(df, x="views", y="creator", orientation="h",
                 labels={"y": "", "x": "Views"})
    fig.update_traces(marker_color="#1F6FB2")
    fig.update_layout(height=400, margin=dict(l=0, r=20, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Reach by creator")
        fig = px.bar(df, x="reach", y="creator", orientation="h",
                     labels={"y": "", "x": "Reach"})
        fig.update_traces(marker_color="#2E8B57")
        fig.update_layout(height=400, margin=dict(l=0, r=20, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Engagements by creator")
        fig = px.bar(df, x="engagements", y="creator", orientation="h",
                     labels={"y": "", "x": "Engagements"})
        fig.update_traces(marker_color="#E67E22")
        fig.update_layout(height=400, margin=dict(l=0, r=20, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Creator summary")
    show = df[["creator", "content_count", "views", "reach", "impressions",
               "likes", "comments", "saves", "shares", "engagements",
               "engagement_rate_pct"]]
    st.dataframe(show.rename(columns={
        "creator": "Creator", "content_count": "Posts", "views": "Views",
        "reach": "Reach", "impressions": "Impressions", "likes": "Likes",
        "comments": "Comments", "saves": "Saves", "shares": "Shares",
        "engagements": "Engagements",
        "engagement_rate_pct": "ER %"}),
        use_container_width=True, hide_index=True)

    st.subheader("Content performance (latest snapshot per post)")
    cp = pd.DataFrame(metrics.content_performance(conn))
    top = cp.sort_values("views", ascending=False)
    st.dataframe(top[["content_id", "creator", "platform", "content_type",
                      "publish_date", "views", "reach", "engagements",
                      "engagement_rate_pct", "source_file"]].rename(columns={
                          "content_id": "Content", "creator": "Creator",
                          "platform": "Platform", "content_type": "Type",
                          "publish_date": "Published", "views": "Views",
                          "reach": "Reach", "engagements": "Eng.",
                          "engagement_rate_pct": "ER %",
                          "source_file": "Source"}),
        use_container_width=True, hide_index=True)

    st.caption("Duplicate analytics exports are stored as snapshots; totals above "
               "use only the latest captured snapshot per content ID.")
