"""Deterministic reconciliation rules.

All matching is rule-based (exact keys + tolerance thresholds). Every
exception carries structured evidence drawn from the source records.
"""
from __future__ import annotations

import pandas as pd

from app.core.matching import CreatorMatcher
from app.models import ExceptionItem, ReconResult

TOL_PCT = 0.02       # 2% amount tolerance before flagging a mismatch
TOL_ABS = 1.00       # ... or $1 absolute, whichever is larger


def _amount_ok(a: float, b: float) -> bool:
    return abs(a - b) <= max(TOL_ABS, TOL_PCT * max(abs(a), abs(b)))


def _attach_creator(df: pd.DataFrame, matcher: CreatorMatcher) -> pd.DataFrame:
    out = df.copy()
    resolved = out["creator"].astype(str).map(lambda r: matcher.resolve(r))
    out["creator_id"] = [r[0] for r in resolved]
    out["match_score"] = [r[1] for r in resolved]
    out["match_status"] = [r[2] for r in resolved]
    return out


def reconcile_contracts_invoices(
    contracts: pd.DataFrame, invoices: pd.DataFrame, matcher: CreatorMatcher
) -> ReconResult:
    """Per creator: contract total vs invoice total for the campaign period."""
    c = _attach_creator(contracts, matcher)
    i = _attach_creator(invoices, matcher)
    res = ReconResult()
    ids = sorted(set(c["creator_id"].dropna()) | set(i["creator_id"].dropna()))
    for cid in ids:
        cs = c[c["creator_id"] == cid]
        ivs = i[i["creator_id"] == cid]
        contracted = round(float(cs["amount"].sum()), 2)
        invoiced = round(float(ivs["amount"].sum()), 2)
        row = {
            "creator_id": cid,
            "name": matcher.display.get(cid, cid),
            "contracted_total": contracted,
            "invoiced_total": invoiced,
            "variance": round(invoiced - contracted, 2),
            "contracts": len(cs),
            "invoices": len(ivs),
        }
        if len(ivs) == 0:
            res.exceptions.append(ExceptionItem(
                exception_id="", severity="high", category="missing_invoice",
                entity=f"{matcher.display.get(cid, cid)} ({cid})",
                description=(f"Active contract(s) totalling ${contracted:,.2f} but no invoice received."),
                evidence={
                    "contract_ids": list(cs["contract_id"].astype(str)),
                    "contracted_total": contracted,
                    "invoice_count": 0,
                }))
            row["state"] = "no invoice"
        elif len(cs) == 0:
            res.exceptions.append(ExceptionItem(
                exception_id="", severity="medium", category="invoice_no_contract",
                entity=f"{matcher.display.get(cid, cid)} ({cid})",
                description=(f"Invoice(s) totalling ${invoiced:,.2f} received with no matching contract."),
                evidence={
                    "invoice_numbers": list(ivs["invoice_number"].astype(str)),
                    "invoiced_total": invoiced,
                    "contract_count": 0,
                }))
            row["state"] = "orphan invoice"
        elif not _amount_ok(contracted, invoiced):
            res.exceptions.append(ExceptionItem(
                exception_id="", severity="medium", category="contract_invoice_mismatch",
                entity=f"{matcher.display.get(cid, cid)} ({cid})",
                description=(f"Invoiced ${invoiced:,.2f} vs contracted ${contracted:,.2f} "
                             f"(variance ${invoiced - contracted:+,.2f})."),
                evidence={
                    "contract_ids": list(cs["contract_id"].astype(str)),
                    "contracted_total": contracted,
                    "invoice_numbers": list(ivs["invoice_number"].astype(str)),
                    "invoiced_total": invoiced,
                    "variance": round(invoiced - contracted, 2),
                    "tolerance": f"{TOL_PCT:.0%} / ${TOL_ABS:.0f}",
                }))
            row["state"] = "mismatch"
        else:
            row["state"] = "matched"
            res.matched.append(row)
        if row["state"] != "matched":
            res.summary.setdefault("rows", []).append(row)
    res.summary.update({
        "creators_checked": len(ids),
        "matched": len(res.matched),
        "exceptions": len(res.exceptions),
    })
    return res


def reconcile_invoices_payouts(
    invoices: pd.DataFrame, payouts: pd.DataFrame, matcher: CreatorMatcher
) -> ReconResult:
    """Invoice-level match by creator + amount; leftovers become exceptions."""
    i = _attach_creator(invoices, matcher)
    p = _attach_creator(payouts, matcher)
    res = ReconResult()
    used_pay: set[int] = set()

    for idx, inv in i.iterrows():
        cand = p[(p["creator_id"] == inv["creator_id"]) & (~p.index.isin(used_pay))]
        hit = None
        for j, pay in cand.iterrows():
            if _amount_ok(float(inv["amount"]), float(pay["amount"])):
                hit = (j, pay)
                break
        if hit is not None:
            j, pay = hit
            used_pay.add(j)
            res.matched.append({
                "invoice_number": str(inv["invoice_number"]),
                "creator_id": inv["creator_id"],
                "name": matcher.display.get(inv["creator_id"], ""),
                "invoice_amount": round(float(inv["amount"]), 2),
                "paid_amount": round(float(pay["amount"]), 2),
                "payment_ref": str(pay["payment_ref"]),
                "payment_date": str(pay["date"]),
                "state": "paid",
            })
        else:
            partial = cand[cand["amount"].astype(float) > 0]
            sev = "high" if str(inv.get("status", "")).lower() == "approved" else "medium"
            res.exceptions.append(ExceptionItem(
                exception_id="", severity=sev, category="missing_payout",
                entity=f"INV {inv['invoice_number']} — {matcher.display.get(inv['creator_id'], inv['creator_id'])}",
                description=(f"Approved invoice ${float(inv['amount']):,.2f} has no matching payout."
                             if str(inv.get("status", "")).lower() == "approved"
                             else f"Invoice ${float(inv['amount']):,.2f} unpaid (status: {inv.get('status')})."),
                evidence={
                    "invoice_number": str(inv["invoice_number"]),
                    "invoice_amount": round(float(inv["amount"]), 2),
                    "invoice_status": str(inv.get("status", "")),
                    "period": str(inv.get("period", "")),
                    "candidate_payments_for_creator": [
                        {"payment_ref": str(r["payment_ref"]),
                         "amount": round(float(r["amount"]), 2),
                         "date": str(r["date"])}
                        for _, r in partial.iterrows()
                    ],
                }))
    unmatched_pays = p[~p.index.isin(used_pay)]
    for _, pay in unmatched_pays.iterrows():
        res.exceptions.append(ExceptionItem(
            exception_id="", severity="medium", category="payout_no_invoice",
            entity=f"PAY {pay['payment_ref']} — {matcher.display.get(pay['creator_id'], pay['creator_id'])}",
            description=(f"Payment of ${float(pay['amount']):,.2f} recorded without a matching invoice."),
            evidence={
                "payment_ref": str(pay["payment_ref"]),
                "amount": round(float(pay["amount"]), 2),
                "date": str(pay["date"]),
                "creator_id": str(pay["creator_id"]),
            }))
    res.summary.update({
        "invoices": len(i),
        "payouts": len(p),
        "matched": len(res.matched),
        "exceptions": len(res.exceptions),
    })
    return res


def reconcile_deliverables(
    contracts: pd.DataFrame, analytics: pd.DataFrame, matcher: CreatorMatcher
) -> ReconResult:
    """Contract deliverable count vs posted content per creator."""
    c = _attach_creator(contracts, matcher)
    a = _attach_creator(analytics, matcher)
    res = ReconResult()
    ids = sorted(set(c["creator_id"].dropna()) | set(a["creator_id"].dropna()))
    for cid in ids:
        cs = c[c["creator_id"] == cid]
        posts = a[a["creator_id"] == cid]
        n_contract = len(cs)
        n_posts = len(posts)
        row = {
            "creator_id": cid,
            "name": matcher.display.get(cid, cid),
            "deliverables_agreed": n_contract,
            "posts_live": n_posts,
            "state": "ok" if n_posts >= n_contract > 0 or (n_contract == 0 and n_posts > 0) else "",
        }
        if n_contract > 0 and n_posts < n_contract:
            row["state"] = "under-delivered"
            res.exceptions.append(ExceptionItem(
                exception_id="", severity="medium", category="deliverable_shortfall",
                entity=f"{matcher.display.get(cid, cid)} ({cid})",
                description=(f"Contracted {n_contract} deliverable(s) but only {n_posts} post(s) live."),
                evidence={
                    "contract_ids": list(cs["contract_id"].astype(str)),
                    "deliverables_agreed": n_contract,
                    "live_post_ids": list(posts["post_id"].astype(str)),
                    "shortfall": n_contract - n_posts,
                }))
        elif n_contract == 0 and n_posts > 0:
            row["state"] = "uncontracted posts"
            res.exceptions.append(ExceptionItem(
                exception_id="", severity="low", category="uncontracted_content",
                entity=f"{matcher.display.get(cid, cid)} ({cid})",
                description=(f"{n_posts} post(s) live with no contract on file."),
                evidence={"live_post_ids": list(posts["post_id"].astype(str))}))
        else:
            res.matched.append(row)
    res.summary.update({"creators_checked": len(ids),
                        "matched": len(res.matched),
                        "exceptions": len(res.exceptions)})
    return res


def aggregate_analytics(analytics: pd.DataFrame, matcher: CreatorMatcher) -> tuple[pd.DataFrame, pd.DataFrame, list[ExceptionItem]]:
    """Deduplicate snapshot rows, then aggregate per creator and platform.

    Returns (deduped_rows, per_creator_summary, duplicate_exceptions).
    Duplicate handling: same post_id appearing more than once is collapsed to
    the row with the latest published/report date; earlier copies are logged
    as low-severity duplicate-snapshot exceptions with full evidence.
    """
    a = _attach_creator(analytics, matcher)
    exceptions: list[ExceptionItem] = []
    metric_cols = [m for m in ("impressions", "engagements", "clicks", "conversions", "spend")
                   if m in a.columns]
    date_col = "published_date" if "published_date" in a.columns else None

    dup_groups = a[a.duplicated(subset=["post_id"], keep=False)]
    if date_col:
        sort_df = a.sort_values([ "post_id", date_col], ascending=[True, True])
    else:
        sort_df = a
    deduped = sort_df.drop_duplicates(subset=["post_id"], keep="last").copy()

    for pid, grp in dup_groups.groupby("post_id"):
        kept = deduped[deduped["post_id"] == pid].iloc[0]
        exceptions.append(ExceptionItem(
            exception_id="", severity="low", category="duplicate_snapshot",
            entity=f"Post {pid}",
            description=(f"{len(grp)} analytics snapshots for the same post; "
                         f"kept latest, discarded {len(grp) - 1}. Metrics were NOT summed."),
            evidence={
                "post_id": str(pid),
                "snapshot_count": len(grp),
                "kept_row": {c: str(kept.get(c, "")) for c in ["creator", *metric_cols]},
                "discarded_rows": [
                    {c: str(r.get(c, "")) for c in ["creator", *metric_cols]}
                    for _, r in grp.iterrows() if r.name != kept.name
                ],
            }))

    rows = []
    for cid, grp in deduped.groupby("creator_id", dropna=False):
        s = {"creator_id": cid if isinstance(cid, str) else "(unmatched)",
             "name": matcher.display.get(cid, str(cid)),
             "posts": len(grp)}
        for m in metric_cols:
            s[m] = float(pd.to_numeric(grp[m], errors="coerce").fillna(0).sum())
        imp, eng = s.get("impressions", 0), s.get("engagements", 0)
        s["engagement_rate"] = round(eng / imp, 4) if imp else 0.0
        conv, spend = s.get("conversions", 0), s.get("spend", 0)
        s["cpa"] = round(spend / conv, 2) if conv else None
        rows.append(s)
    summary = pd.DataFrame(rows).sort_values("impressions", ascending=False).reset_index(drop=True)
    return deduped, summary, exceptions
