"""Deterministic narrative builder (AI mode may rephrase it - numbers stay)."""
from __future__ import annotations

import sqlite3

from reporting import metrics


def _m(v) -> str:
    return f"${v:,.0f}" if v is not None else "n/a"


def build_narrative(conn: sqlite3.Connection) -> dict:
    t = metrics.campaign_totals(conn)
    fin = metrics.financial_table(conn)
    perf = metrics.creator_performance(conn)
    ex_rows = conn.execute(
        "SELECT exception_type, severity, COUNT(*) c FROM exceptions "
        "WHERE status IN ('OPEN','IN_REVIEW') GROUP BY 1,2 ORDER BY c DESC").fetchall()
    by_type = {r["exception_type"]: r["c"] for r in ex_rows}

    top = perf[0] if perf else None
    er_txt = f"{t['engagement_rate_pct']}%" if t["engagement_rate_pct"] is not None \
        else "not calculable (no reach data)"

    exec_sum = (
        f"The campaign engaged {t['content_count']} pieces of published content from "
        f"{t['creators']} creators, generating {t['views']:,} views, {t['reach']:,} reach "
        f"and {t['engagements']:,} engagements (engagement rate {er_txt}). "
        f"{_m(t['contracted_fees'])} was contracted, {_m(t['invoiced'])} invoiced and "
        f"{_m(t['paid'])} paid, leaving {_m(t['outstanding'])} outstanding. "
        f"{t['open_exceptions']} operational exceptions are open for review.")

    key_obs = []
    if top:
        key_obs.append(
            f"{top['creator']} delivered the highest reach ({top['reach']:,}) across "
            f"{top['content_count']} tracked posts.")
    if t["deliverables_published"] < t["deliverables_required"]:
        key_obs.append(
            f"{t['deliverables_published']} of {t['deliverables_required']} contracted "
            f"deliverables are confirmed published; the gap is under active review.")
    if by_type.get("PAYMENT_VARIANCE"):
        key_obs.append(
            f"{by_type['PAYMENT_VARIANCE']} creator(s) invoiced above contract value; "
            f"finance should confirm before further payouts.")

    ops_obs = []
    if by_type.get("MISSING_DELIVERABLE"):
        ops_obs.append(f"{by_type['MISSING_DELIVERABLE']} missing-deliverable case(s) detected.")
    if by_type.get("LATE_DELIVERABLE"):
        ops_obs.append(f"{by_type['LATE_DELIVERABLE']} late publication(s) vs contract deadlines.")
    if by_type.get("ANALYTICS_MISSING"):
        ops_obs.append(f"{by_type['ANALYTICS_MISSING']} published post(s) lack an analytics snapshot.")
    if by_type.get("MATCH_REVIEW") or by_type.get("UNKNOWN_CREATOR"):
        ops_obs.append(
            f"{by_type.get('MATCH_REVIEW', 0)} low-confidence and "
            f"{by_type.get('UNKNOWN_CREATOR', 0)} unknown creator link(s) awaiting human review; "
            "nothing was merged automatically.")
    if by_type.get("DUPLICATE_INVOICE"):
        ops_obs.append(f"{by_type['DUPLICATE_INVOICE']} duplicate invoice number(s) found.")

    recs = []
    if any(r["status"] == "REVIEW REQUIRED" for r in fin):
        recs.append("Resolve invoice variances with creators before releasing remaining payments.")
    if by_type.get("PAYMENT_PENDING"):
        recs.append("Release pending payments for creators who completed all deliverables.")
    if by_type.get("ANALYTICS_MISSING"):
        recs.append("Request missing analytics exports so performance reporting is complete.")
    if by_type.get("MISSING_DELIVERABLE"):
        recs.append("Chase unpublished contracted items ahead of campaign close-out.")
    if not recs:
        recs.append("No blocking issues; archive reconciled records and close the campaign.")

    out = {"executive_summary": exec_sum, "key_observations": key_obs,
           "operational_observations": ops_obs or ["No operational anomalies detected."],
           "recommendations": recs}

    # Optional AI rephrasing (never changes numbers; falls back silently)
    try:
        from ai.report_agent import generate_narrative
        ai = generate_narrative(out)
        if ai:
            out["source"] = "qwen-assisted (numbers validated)"
            out.update({k: v for k, v in ai.items() if k in out})
        else:
            out["source"] = "deterministic template"
    except Exception:
        out["source"] = "deterministic template"
    return out
