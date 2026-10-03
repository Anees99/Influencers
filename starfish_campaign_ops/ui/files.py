"""Files page: processed-file ledger + operator upload & processing."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import settings
from ingestion.router import CATEGORIES, guess_category
from ui.common import badge, empty_state, needs_data


def render(conn):
    st.title("📁 Campaign Files")

    # --------------------------------------------------- processed ledger
    if needs_data():
        empty_state("No files processed yet.")
    else:
        rows = conn.execute(
            "SELECT * FROM file_uploads ORDER BY category, filename").fetchall()
        df = pd.DataFrame([{
            "Filename": r["filename"],
            "Category": r["category"],
            "Type": r["file_type"].upper(),
            "Status": r["status"],
            "Records": r["records_extracted"],
            "Warnings / Errors": r["warnings"] or "",
        } for r in rows])
        n_ok = (df["Status"] == "PROCESSED").sum()
        n_err = (df["Status"] == "ERROR").sum()
        st.caption(f"{len(df)} files · {n_ok} processed · "
                   f"{n_err} with errors — a bad file never blocks the campaign.")
        styled = df.copy()
        styled["Status"] = styled["Status"].map(badge)
        st.markdown(styled.to_html(index=False, border=0, escape=False),
                    unsafe_allow_html=True)

    st.divider()

    # ------------------------------------------------------- upload panel
    st.subheader("Upload campaign files")
    st.caption("Supported: PDF · CSV · XLSX · PNG · JPG. One file failing does not "
               "stop the rest of the batch.")

    uploaded = st.file_uploader(
        "Drop contracts, invoices, payouts, analytics exports, deliverable "
        "trackers or screenshots",
        type=["pdf", "csv", "xlsx", "png", "jpg", "jpeg"],
        accept_multiple_files=True, key="sf_uploader")

    categories: dict[str, str] = {}
    if uploaded:
        st.markdown("**Assign a category to each file:**")
        for u in uploaded:
            guess = guess_category(u.name, u.name.rsplit(".", 1)[-1].lower()) or "Contract"
            sel = st.selectbox(f"{u.name} ({u.size/1024:.0f} KB)", CATEGORIES,
                               index=CATEGORIES.index(guess) if guess in CATEGORIES else 0,
                               key=f"cat_{u.name}_{u.size}")
            categories[u.name] = sel

        if st.button("⚙️ Process Uploaded Files", type="primary"):
            from reconciliation.engine import build_result
            from database import db
            from schemas.campaign import Campaign
            from demo_loader import ROSTER

            camp_row = conn.execute("SELECT * FROM campaigns LIMIT 1").fetchone()
            files = [(u.name, u.getvalue(), categories[u.name]) for u in uploaded]
            try:
                campaign = Campaign(
                    campaign_id=camp_row["campaign_id"] if camp_row else "CMP-UPLOAD",
                    client_name=camp_row["client_name"] if camp_row else "Uploaded",
                    campaign_name=camp_row["campaign_name"] if camp_row else "Upload batch",
                    start_date=None, end_date=None,
                    currency=camp_row["currency"] if camp_row else "USD",
                    platforms=["Instagram", "TikTok"])
                result = build_result(files, list(ROSTER), campaign)
                db.persist_result(conn, result)
                for fr in result.file_results:
                    db.record_upload(conn, fr.filename, fr.category, fr.file_type,
                                     fr.status, fr.records_extracted,
                                     ([fr.error] if fr.error else []) + list(fr.warnings))
                st.session_state["last_pipeline_result"] = result
                ok = sum(1 for f in result.file_results if f.status == "PROCESSED")
                err = sum(1 for f in result.file_results if f.status == "ERROR")
                st.success(f"Processed {ok} file(s)"
                           + (f", {err} error(s) — see ledger above" if err else ""))
                st.rerun()
            except Exception as exc:  # defensive: surface, never crash the app
                st.error(f"Processing failed without affecting existing data: {exc}")
