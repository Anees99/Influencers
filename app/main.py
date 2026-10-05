"""Streamlit UI for Starfish Campaign Operations Automation.

Demo flow: Upload -> Process -> Creators identified -> Reconciliation ->
Exceptions (open + evidence) -> Performance -> Financials -> Reports.
Run with:  streamlit run app/main.py
"""
from __future__ import annotations

import io
import time

import pandas as pd
import streamlit as st

from app.core.excel import build_workbook, exceptions_frame
from app.core.loader import LoadError, detect_source, load_table
from app.core.pdf import build_pdf
from app.core.pipeline import run_pipeline

st.set_page_config(page_title="Starfish Campaign Ops", page_icon="⭐", layout="wide")

CSS = """
<style>
[data-testid="stMetric"] {background: #f2f7f6; border-left: 4px solid #134E4A;
    padding: 12px 16px; border-radius: 6px;}
[data-testid="stMetricLabel"] {color:#3a5a56; font-weight:600;}
.divider {height: 3px; background: linear-gradient(90deg,#134E4A,#e8b04a);
    border-radius:2px; margin: 4px 0 14px 0;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

SEV_ICON = {"high": "🔴", "medium": "🟠", "low": "🔵"}

SOURCE_LABELS = {
    "creators": "Creator roster",
    "contracts": "Contracts",
    "invoices": "Invoices",
    "payouts": "Payouts / bank feed",
    "analytics": "Analytics export",
}


@st.cache_resource(show=False)
def _noop():
    return None


def demo_frames() -> dict[str, bytes]:
    base = "data/raw"
    out = {}
    for src, fn in [("creators", "creators.csv"), ("contracts", "contracts.csv"),
                    ("invoices", "invoices.csv"), ("payouts", "payouts.csv"),
                    ("analytics", "analytics.csv")]:
        try:
            out[src] = open(f"{base}/{fn}", "rb").read()
        except FileNotFoundError:
            pass
    return out


def process_bytes(items: list[tuple[str, bytes]]) -> None:
    """Load uploaded files, run the pipeline, store result in session."""
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    for name, blob in items:
        src = detect_source(name)
        if src is None:
            errors.append(
                f"**{name}** — could not tell which file type this is. "
                "Rename it to include one of: creators, contracts, invoices, "
                "payouts, analytics.")
            continue
        if src in frames:
            errors.append(f"**{name}** — a {src} file was already supplied; skipped duplicate input.")
            continue
        try:
            frames[src] = load_table(io.BytesIO(blob), name, src).df
        except LoadError as exc:
            errors.append(str(exc))
    if errors:
        st.session_state["load_errors"] = errors
        st.session_state.pop("result", None)
        return
    st.session_state["load_errors"] = []
    t0 = time.perf_counter()
    try:
        result = run_pipeline(frames)
    except ValueError as exc:
        st.session_state["load_errors"] = [f"Processing stopped: {exc}"]
        st.session_state.pop("result", None)
        return
    st.session_state["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
    st.session_state["result"] = result


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("⭐ Starfish Ops")
    st.caption("Campaign reconciliation & reporting")
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    uploads = st.file_uploader(
        "Upload campaign files (CSV / XLSX)",
        accept_types=["csv", "xlsx", "xls"],
        type="binary",
        key="uploader",
        help="Expected: creator roster, contracts, invoices, payouts, analytics. "
             "Files are detected by name.",
    )
    use_demo = st.toggle("Use bundled September demo data", value=True,
                         help="12 active creators, 5 source files, 12 planted exceptions.")
    run_btn = st.button("▶  Process files", use_container_width=True, type="primary")

    st.markdown("---")
    st.caption("**How matching works** — deterministic rules only: normalized "
               "name keys, alias tables and token-overlap scores with fixed "
               "thresholds. No LLM, no invented numbers. Every figure traces "
               "back to a source row.")

if run_btn:
    items: list[tuple[str, bytes]] = []
    if uploads:
        items = [(u.name, u.getvalue()) for u in uploads]
    elif use_demo:
        items = list(demo_frames().items())
    if not items:
        st.warning("Upload at least the contracts and invoices files, or switch on the demo dataset.")
    else:
        with st.spinner("Matching creators, reconciling finances and content…"):
            process_bytes(items)

res = st.session_state.get("result")
errs = st.session_state.get("load_errors", [])
if errs:
    st.error("\n\n".join(errs))

# ---------------------------------------------------------------- main flow
if res is None:
    st.markdown("## Campaign Operations Automation")
    st.markdown(
        "Point-and-click reconciliation for creator campaigns:\n\n"
        "1. **Upload** contracts, invoices, payouts, analytics and the creator roster\n"
        "2. **Process** — creators are matched across files with deterministic rules\n"
        "3. **Reconcile** contract ↔ invoice ↔ payout and deliverables ↔ contracts\n"
        "4. **Investigate** every exception with its source-record evidence\n"
        "5. **Deliver** a branded Excel workbook and PDF client report"
    )
    st.info("👈 Load the bundled September demo (or your own files) from the sidebar, then press **Process files**.")
else:
    active = res.roster[res.roster["appears_in"] != "roster only"]
    hi = sum(1 for e in res.exceptions if e.severity == "high")
    med = sum(1 for e in res.exceptions if e.severity == "medium")
    low = sum(1 for e in res.exceptions if e.severity == "low")
    ci = res.contracts_vs_invoices
    ip = res.invoices_vs_payouts
    dv = res.deliverables

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Creators identified", len(active))
    c2.metric("Contract ↔ invoice", f"{ci.summary.get('matched', 0)} matched")
    c3.metric("Invoice ↔ payout", f"{ip.summary.get('matched', 0)} paid")
    c4.metric("Deliverable checks", f"{len(dv.matched)} passed")
    c5.metric("Open exceptions", len(res.exceptions), delta=f"{hi} high · {med} med · {low} low",
              delta_color="off")
    st.caption(f"Processed {sum(len(df) for df in res.inputs.values())} source rows "
               f"in {st.session_state.get('elapsed_ms', 0)} ms — deterministic rules, no estimates.")
    for w in res.warnings:
        st.warning(w)

    tab_fin, tab_perf, tab_exc, tab_roster, tab_rep = st.tabs([
        "💰 Financial reconciliation",
        "📈 Campaign performance",
        "🚩 Exceptions",
        "👥 Creator matching",
        "📤 Client reports",
    ])

    with tab_fin:
        st.subheader("Contracts vs invoices (per creator)")
        rows = ci.matched + ci.summary.get("rows", [])
        if rows:
            fin = pd.DataFrame(rows).rename(columns={
                "creator_id": "Creator ID", "name": "Creator",
                "contracted_total": "Contracted $", "invoiced_total": "Invoiced $",
                "variance": "Variance $", "contracts": "# Contracts",
                "invoices": "# Invoices", "state": "State"})
            st.dataframe(fin, hide_index=True, use_container_width=True)
        st.subheader("Approved invoices matched to bank payouts")
        if ip.matched:
            pay = pd.DataFrame(ip.matched).rename(columns={
                "invoice_number": "Invoice", "name": "Creator",
                "invoice_amount": "Invoice $", "paid_amount": "Paid $",
                "payment_ref": "Payment ref", "payment_date": "Paid on"})
            st.dataframe(pay[["Invoice", "Creator", "Invoice $", "Paid $",
                              "Payment ref", "Paid on"]],
                         hide_index=True, use_container_width=True)
        else:
            st.info("No invoice/payout matches in this dataset.")
        st.caption("Tolerances: variance ≤ max($1, 2%) counts as matched. "
                   "Unmatched records appear in the Exceptions tab with evidence.")

    with tab_perf:
        st.subheader("Performance by creator")
        st.caption("Duplicate analytics snapshots are collapsed to the latest "
                   "report per post before aggregation — metrics are never double-counted.")
        if len(res.creator_summary):
            cs = res.creator_summary.rename(columns={
                "creator_id": "Creator ID", "name": "Creator", "posts": "Posts",
                "impressions": "Impressions", "engagements": "Engagements",
                "clicks": "Clicks", "conversions": "Conversions", "spend": "Spend $",
                "engagement_rate": "Engagement rate", "cpa": "CPA $"})
            st.dataframe(cs, hide_index=True, use_container_width=True)
            left, right = st.columns(2)
            with left:
                st.altair_chart(
                    cs.sort_values("Impressions", ascending=False)
                    .plot.barh(x="Creator", y="Impressions", legend=False, height=340),
                    use_container_width=True)
            with right:
                if len(res.platform_summary):
                    st.altair_chart(
                        res.platform_summary.plot.bar(x="platform", y="impressions",
                                                      legend=False, color="teal", height=340),
                        use_container_width=True)
        else:
            st.info("No analytics supplied.")
        if len(res.analytics_deduped):
            with st.expander("Deduplicated post-level data"):
                show = ["post_id", "creator", "platform", "published_date",
                        "impressions", "engagements", "clicks", "conversions", "spend"]
                cols = [c for c in show if c in res.analytics_deduped.columns]
                st.dataframe(res.analytics_deduped[cols], hide_index=True,
                             use_container_width=True)

    with tab_exc:
        st.subheader(f"Exception register ({len(res.exceptions)} open)")
        ef = exceptions_frame(res)
        if len(ef):
            st.dataframe(ef.drop(columns=["Evidence"]), hide_index=True,
                         use_container_width=True)
            choice = st.selectbox(
                "Open an exception to inspect its evidence",
                options=list(ef["Exception ID"]),
                format_func=lambda x: next(
                    f'{x} · {SEV_ICON.get(e.severity,"")} [{e.severity.upper()}] '
                    f'{e.category} — {e.entity}'
                    for e in res.exceptions if e.exception_id == x),
                key="exc_pick")
            exc = next(e for e in res.exceptions if e.exception_id == choice)
            col_a, col_b = st.columns([1, 1])
            with col_a:
                st.markdown(f"**{SEV_ICON[exc.severity]} {exc.exception_id} — "
                            f"{exc.category.replace('_',' ').title()}**")
                st.markdown(f"*Entity:* {exc.entity}")
                st.markdown(exc.description)
                st.markdown(f"**Status:** `{exc.status}`")
                if st.button("Mark acknowledged", key=f"ack_{choice}"):
                    exc.status = "acknowledged"
                    st.rerun()
            with col_b:
                st.markdown("**Evidence (straight from source records)**")
                ev = pd.DataFrame(
                    [{"Field": k, "Value": v} for k, v in exc.evidence.items()])
                st.dataframe(ev.astype({"Value": str}), hide_index=True,
                             use_container_width=True)
        else:
            st.success("No exceptions — everything reconciles cleanly. 🎉")

    with tab_roster:
        st.subheader("Creator identification & name matching")
        act = res.roster[res.roster["appears_in"] != "roster only"].rename(columns={
            "creator_id": "ID", "name": "Canonical name",
            "name_variants": "Name variants seen", "appears_in": "Appears in files",
            "min_match_score": "Min score", "needs_review": "Needs review"})
        st.dataframe(act, hide_index=True, use_container_width=True)
        st.caption(f"{len(act)} creators referenced by operational files "
                   f"(+{len(res.roster) - len(act)} roster-only, not active this period).")
        with st.expander("Raw match log (every name string encountered)"):
            st.dataframe(res.match_log, hide_index=True, use_container_width=True)

    with tab_rep:
        st.subheader("Generate client deliverables")
        st.markdown("Both documents are built from the same reconciled numbers you see on screen.")
        r1, r2 = st.columns(2)
        with r1:
            st.markdown("**Excel workbook** — overview, both reconciliations, "
                        "deliverables, performance, exception register, roster and raw inputs.")
            try:
                xlsx = build_workbook(res)
                st.download_button("⬇️ Download Excel report", data=xlsx,
                                   file_name="starfish_september_reconciliation.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   use_container_width=True, type="primary")
            except Exception as exc:
                st.error(f"Excel generation failed: {exc}")
        with r2:
            st.markdown("**PDF report** — executive summary, financial "
                        "reconciliation, performance and the full exception "
                        "register with evidence.")
            try:
                pdf = build_pdf(res)
                st.download_button("⬇️ Download PDF report", data=pdf,
                                   file_name="starfish_september_client_report.pdf",
                                   mime="application/pdf",
                                   use_container_width=True)
            except Exception as exc:
                st.error(f"PDF generation failed: {exc}")
