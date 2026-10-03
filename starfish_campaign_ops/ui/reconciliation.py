"""Reconciliation overview + human-review queue for ambiguous matches."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from reporting import metrics
from ui.common import badge, empty_state, needs_data


def render(conn):
    st.title("🔁 Reconciliation")
    if needs_data():
        empty_state("No reconciliation data yet.")
        return

    t = metrics.campaign_totals(conn)
    st.subheader("Coverage")
    cov = pd.DataFrame([
        {"Stream": "Contracts ↔ Invoices",
         "Records": f"{t['creators']} creators · ${t['contracted_fees']:,.0f} contracted "
                    f"vs ${t['invoiced']:,.0f} invoiced",
         "Exceptions": sum(1 for r in conn.execute(
             "SELECT 1 FROM exceptions WHERE exception_type IN "
             "('PAYMENT_VARIANCE','INVOICE_UNDERBILLED','DUPLICATE_INVOICE')"))},
        {"Stream": "Invoices ↔ Payouts",
         "Records": f"${t['paid']:,.0f} paid · ${t['outstanding']:,.0f} outstanding",
         "Exceptions": sum(1 for r in conn.execute(
             "SELECT 1 FROM exceptions WHERE exception_type IN "
             "('PAYOUT_VARIANCE','PAYMENT_PENDING')"))},
        {"Stream": "Contracts ↔ Deliverables",
         "Records": f"{t['deliverables_published']}/{t['deliverables_required']} published",
         "Exceptions": sum(1 for r in conn.execute(
             "SELECT 1 FROM exceptions WHERE exception_type IN "
             "('MISSING_DELIVERABLE','LATE_DELIVERABLE')"))},
        {"Stream": "Deliverables ↔ Analytics",
         "Records": f"{t['content_count']} content pieces tracked (latest snapshots)",
         "Exceptions": sum(1 for r in conn.execute(
             "SELECT 1 FROM exceptions WHERE exception_type IN "
             "('ANALYTICS_MISSING','SCREENSHOT_REVIEW')"))},
        {"Stream": "Creator identity matching",
         "Records": f"{t['creators']} normalized creators",
         "Exceptions": sum(1 for r in conn.execute(
             "SELECT 1 FROM exceptions WHERE exception_type IN "
             "('MATCH_REVIEW','NAME_MISMATCH','UNKNOWN_CREATOR')"))},
    ])
    st.dataframe(cov, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🧑‍⚖️ Human review — ambiguous creator matches")
    st.caption("Low-confidence identities are **never merged automatically**. "
               "Approve to bind the record, or reject and leave it unmatched. "
               "(Review decisions apply to the current session; source-file "
               "reprocessing regenerates deterministic suggestions.)")

    result = st.session_state.get("last_pipeline_result")
    if result is None:
        st.info("Pending-match queue is available after processing files in this "
                "session (Home → Load Demo Campaign, or Files → Process).")
        return
    pending = [pm for pm in getattr(result, "pending_matches", [])
               if not getattr(pm, "resolved", False)]
    if not pending:
        st.success("No unresolved identity matches pending review. 🎉")
        return
    names = {cid: c.canonical_name for cid, c in result.creators.items()}
    for i, pm in enumerate(pending):
        sugg = names.get(pm.suggested_id, pm.suggested_id or "no candidate")
        with st.expander(f"❓ `{pm.raw_value}` ({pm.record_kind} · {pm.source_file}) "
                         f"→ suggested **{sugg}** at {pm.score:.0%}"):
            st.markdown(f"**Reason:** {pm.reason}")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Approve match", key=f"appr_{i}"):
                    ok = result.apply_approved_match(i, pm.suggested_id) \
                        if hasattr(result, "apply_approved_match") else False
                    if not ok:
                        from reconciliation.engine import ReconciliationEngine
                        eng = ReconciliationEngine(result.campaign)
                        eng.result = result
                        ok = eng.apply_approved_match(i, pm.suggested_id)
                    st.success("Match approved and bound." if ok
                               else "Could not bind this record.")
                    st.rerun()
            with c2:
                if st.button("❌ Reject match", key=f"rej_{i}"):
                    pm.resolved = True
                    st.warning("Rejected — record left unmerged.")
                    st.rerun()
