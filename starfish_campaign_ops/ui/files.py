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
    if needs_data(conn):
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

            camp_row = conn.execute("SELECT * FROM campaigns LIMIT 1").fetchone()
            files = [(u.name, u.getvalue(), categories[u.name]) for u in uploaded]

            # Roster: rebuild it from the contracts in this batch so creators
            # that exist only in contract PDFs are never dumped into
            # "(unmatched)". If a demo campaign is already loaded, seed the
            # roster with its known creators first (preserves ST-xxx IDs).
            roster = []
            prev_ids: dict[str, str] = {}
            try:
                for r in conn.execute(
                        "SELECT creator_id, canonical_name, instagram_handle "
                        "FROM creators ORDER BY creator_id").fetchall():
                    prev_ids[r["canonical_name"].lower()] = (
                        r["creator_id"], r["instagram_handle"])
            except Exception:
                pass
            used_ids = {v[0] for v in prev_ids.values()}
            next_n = 1
            from ingestion.router import process_file as _pf
            from matching.creator_matching import CreatorRegistry
            names_seen: set[str] = set()
            for fname, blob, cat in files:
                if cat != "Contract":
                    continue
                try:
                    pr = _pf(fname, blob, "Contract")
                except Exception:
                    continue
                for ct in pr.contracts:
                    nm = (ct.__dict__.get("_extracted") or {}).get("creator_name")
                    if not nm or nm.lower() in names_seen:
                        continue
                    names_seen.add(nm.lower())
                    handle = (ct.__dict__.get("_extracted") or {}).get("handle")
                    existing_id = None
                    if prev_ids:
                        reg = CreatorRegistry()
                        for k, (cid, h) in prev_ids.items():
                            reg.add(cid, k, instagram_handle=h)
                        d = reg.resolve(nm)
                        if d.creator_id and not d.needs_review:
                            existing_id = d.creator_id
                    if existing_id:
                        cid = existing_id
                    else:
                        cid = next((f"ST-{i:03d}" for i in range(next_n, 1000)
                                    if f"ST-{i:03d}" not in used_ids), None)
                        used_ids.add(cid)
                        next_n = max(next_n, int(cid.split("-")[1]) + 1)
                    from schemas.creator import Creator as _Cr
                    roster.append(_Cr(creator_id=cid, canonical_name=nm,
                                      instagram_handle=handle))
            if not roster and not prev_ids:
                from demo_loader import ROSTER
                roster = list(ROSTER)
            elif prev_ids:
                from schemas.creator import Creator as _Cr
                by_cid: dict[str, tuple[str, str]] = {}
                for k, (cid, h) in prev_ids.items():
                    by_cid.setdefault(cid, (k, h))
                roster_ids = {c.creator_id for c in roster}
                for cid, (nm, h) in by_cid.items():
                    if cid not in roster_ids:
                        roster.append(_Cr(creator_id=cid,
                                          canonical_name=nm.title(),
                                          instagram_handle=h))

            try:
                campaign = Campaign(
                    campaign_id=camp_row["campaign_id"] if camp_row else "CMP-UPLOAD",
                    client_name=camp_row["client_name"] if camp_row else "Uploaded",
                    campaign_name=camp_row["campaign_name"] if camp_row else "Upload batch",
                    start_date=None, end_date=None,
                    currency=camp_row["currency"] if camp_row else "USD",
                    platforms=["Instagram", "TikTok"])
                result = build_result(files, roster, campaign)
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
