"""Report metrics: every number is recomputed from the persisted DB rows."""
from __future__ import annotations

import sqlite3

ENG_FIELDS = ("likes", "comments", "saves", "shares")


def _latest_snapshot_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """One row per content_id: latest captured_at; screenshots excluded until
    their verification exception is resolved (needs_verification flag)."""
    return conn.execute(
        """
        SELECT a.* FROM analytics_records a
        JOIN (SELECT content_id, MAX(captured_at) mc FROM analytics_records
              WHERE needs_verification = 0 GROUP BY content_id) t
          ON a.content_id = t.content_id AND a.captured_at = t.mc
        WHERE a.needs_verification = 0
        GROUP BY a.content_id
        ORDER BY a.content_id
        """).fetchall()


def campaign_totals(conn: sqlite3.Connection) -> dict:
    rows = _latest_snapshot_rows(conn)
    views = sum(r["views"] or 0 for r in rows)
    reach = sum(r["reach"] or 0 for r in rows)
    impressions = sum(r["impressions"] or 0 for r in rows)
    likes = sum(r["likes"] or 0 for r in rows)
    comments = sum(r["comments"] or 0 for r in rows)
    saves = sum(r["saves"] or 0 for r in rows)
    shares = sum(r["shares"] or 0 for r in rows)
    engagements = likes + comments + saves + shares
    fin = financial_rollup(conn)
    exc_open = conn.execute(
        "SELECT COUNT(*) c FROM exceptions WHERE status IN ('OPEN','IN_REVIEW')"
    ).fetchone()["c"]
    deliv = conn.execute("SELECT * FROM deliverables WHERE required=1").fetchall()
    published = [d for d in deliv if d["published_at"]]
    return {
        "creators": conn.execute("SELECT COUNT(*) c FROM creators").fetchone()["c"],
        "content_count": len(rows),
        "deliverables_required": len(deliv),
        "deliverables_published": len(published),
        "views": views, "reach": reach, "impressions": impressions,
        "likes": likes, "comments": comments, "saves": saves, "shares": shares,
        "engagements": engagements,
        "engagement_rate_pct": round(engagements / reach * 100, 2) if reach else None,
        **fin,
        "open_exceptions": exc_open,
    }


def financial_rollup(conn: sqlite3.Connection) -> dict:
    contracted = conn.execute(
        "SELECT COALESCE(SUM(agreed_fee),0) s FROM contracts").fetchone()["s"]
    invoiced = conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM invoices").fetchone()["s"]
    paid = conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM payouts "
        "WHERE LOWER(status) IN ('paid','completed','sent')").fetchone()["s"]
    return {"contracted_fees": round(contracted, 2), "invoiced": round(invoiced, 2),
            "paid": round(paid, 2), "outstanding": round(invoiced - paid, 2)}


def creator_performance(conn: sqlite3.Connection) -> list[dict]:
    rows = _latest_snapshot_rows(conn)
    names = {r["creator_id"]: r["canonical_name"] for r in
             conn.execute("SELECT creator_id, canonical_name FROM creators")}
    agg: dict[str | None, dict] = {}
    for r in rows:
        cid = r["creator_id"]
        a = agg.setdefault(cid, {"creator_id": cid,
                                 "creator": names.get(cid, cid or "(unmatched)"),
                                 "content_count": 0, "views": 0, "reach": 0,
                                 "impressions": 0, "likes": 0, "comments": 0,
                                 "saves": 0, "shares": 0})
        a["content_count"] += 1
        for k in ("views", "reach", "impressions", "likes", "comments", "saves",
                  "shares"):
            a[k] += r[k] or 0
    out = []
    for a in agg.values():
        a["engagements"] = sum(a[k] for k in ENG_FIELDS)
        a["engagement_rate_pct"] = (round(a["engagements"] / a["reach"] * 100, 2)
                                    if a["reach"] else None)
        out.append(a)
    return sorted(out, key=lambda x: -x["views"])


def content_performance(conn: sqlite3.Connection) -> list[dict]:
    names = {r["creator_id"]: r["canonical_name"] for r in
             conn.execute("SELECT creator_id, canonical_name FROM creators")}
    out = []
    for r in _latest_snapshot_rows(conn):
        eng = sum(r[k] or 0 for k in ENG_FIELDS)
        out.append({"content_id": r["content_id"],
                    "creator": names.get(r["creator_id"], "(unmatched)"),
                    "platform": r["platform"], "content_type": r["content_type"],
                    "publish_date": r["publish_date"], "views": r["views"],
                    "reach": r["reach"], "impressions": r["impressions"],
                    "likes": r["likes"], "comments": r["comments"],
                    "saves": r["saves"], "shares": r["shares"],
                    "engagements": eng,
                    "engagement_rate_pct": (round(eng / r["reach"] * 100, 2)
                                            if r["reach"] else None),
                    "source_file": r["source_file"], "source_type": r["source_type"]})
    return out


def financial_table(conn: sqlite3.Connection) -> list[dict]:
    """Per-creator contract/invoice/payout table computed by SQL sums."""
    names = {r["creator_id"]: r["canonical_name"] for r in
             conn.execute("SELECT creator_id, canonical_name FROM creators")}
    ids = set(names)
    q = lambda sql: conn.execute(sql).fetchall()
    contracted, invoiced, paid = {}, {}, {}
    for r in q("SELECT creator_id, SUM(agreed_fee) s FROM contracts GROUP BY creator_id"):
        contracted[r["creator_id"]] = r["s"] or 0
    for r in q("SELECT creator_id, SUM(amount) s FROM invoices GROUP BY creator_id"):
        invoiced[r["creator_id"]] = r["s"] or 0
    for r in q("SELECT i.creator_id cid, SUM(p.amount) s FROM payouts p "
               "LEFT JOIN invoices i ON i.invoice_number = p.invoice_number "
               "WHERE LOWER(p.status) IN ('paid','completed','sent') "
               "GROUP BY COALESCE(i.creator_id, p.creator_id)"):
        paid[r["cid"]] = r["s"] or 0
    all_ids = set(contracted) | set(invoiced) | set(paid)
    rows = []
    tol = 0.01
    for cid in sorted(all_ids, key=lambda c: names.get(c, str(c))):
        fee, inv, py = contracted.get(cid), invoiced.get(cid, 0), paid.get(cid, 0)
        variance = round((inv or 0) - (fee or 0), 2)
        if fee is not None and abs(variance) > tol:
            status = "REVIEW REQUIRED" if inv > fee else "UNDER-BILLED"
        elif inv and py == 0:
            status = "PENDING PAYMENT"
        elif py and abs(inv - py) > tol:
            status = "PAYOUT VARIANCE"
        elif inv and py:
            status = "PAID"
        elif fee is not None and not inv:
            status = "NOT INVOICED"
        else:
            status = "OK"
        rows.append({"creator_id": cid, "creator": names.get(cid, cid),
                     "contract_fee": fee, "invoice": inv, "payout": py,
                     "variance": variance, "outstanding": round(inv - py, 2),
                     "status": status})
    return rows


def deliverable_table(conn: sqlite3.Connection) -> list[dict]:
    names = {r["creator_id"]: r["canonical_name"] for r in
             conn.execute("SELECT creator_id, canonical_name FROM creators")}
    rows = []
    for ct in conn.execute("SELECT * FROM contracts ORDER BY creator_id"):
        import json
        items = json.loads(ct["deliverables_json"] or "[]")
        required = sum(int(i.get("count", 1)) for i in items)
        dvs = conn.execute(
            "SELECT * FROM deliverables WHERE creator_id=? AND required=1",
            (ct["creator_id"],)).fetchall()
        published = [d for d in dvs if d["published_at"]]
        late = []
        deadline = ct["deadline"]
        if deadline:
            late = [d for d in published if str(d["published_at"]) > str(deadline)]
        statuses = sorted({d["approval_status"] for d in dvs} or ["-"])
        rows.append({"creator_id": ct["creator_id"],
                     "creator": names.get(ct["creator_id"], "(unmatched)"),
                     "required": required, "published": len(published),
                     "missing": max(required - len(published), 0),
                     "late": len(late),
                     "approval_statuses": ", ".join(statuses),
                     "source_file": ct["source_file"]})
    return rows
