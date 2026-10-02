"""Analytics reconciliation: snapshots, dedupe, coverage checks.

Same content appearing in multiple exports = snapshots, never double-counted.
Reporting always uses the latest valid snapshot per content id.
"""
from __future__ import annotations

from reconciliation.exceptions import make
from schemas.analytics import AnalyticsRecord

METRIC_FIELDS = ("views", "reach", "impressions", "likes", "comments",
                 "saves", "shares", "watch_time")


def latest_snapshots(records: list[AnalyticsRecord]) -> dict[str, AnalyticsRecord]:
    """content_id -> most recent trustworthy snapshot."""
    out: dict[str, AnalyticsRecord] = {}
    for r in records:
        if not r.content_id:
            continue
        prev = out.get(r.content_id)
        key = (r.captured_at or "", r.source_file)
        pkey = (prev.captured_at or "", prev.source_file) if prev else ("", "")
        if prev is None or key >= pkey:
            out[r.content_id] = r
    return out


def reconcile_analytics(analytics: list[AnalyticsRecord],
                        deliverables_by_content: dict[str, dict],
                        campaign_id: str = "") -> tuple[list, list]:
    """Returns (exceptions, notes). deliverables_by_content: content_id->row."""
    exceptions: list = []
    # duplicate identical snapshots (same content, same captured_at, same views)
    seen: dict[tuple, AnalyticsRecord] = {}
    for r in analytics:
        k = (r.content_id, r.captured_at, r.views, r.source_file)
        if r.content_id and k in seen:
            prev = seen[k]
            exceptions.append(make(
                "DUPLICATE_ANALYTICS_SNAPSHOT",
                f"Identical snapshot for {r.content_id} captured at {r.captured_at} "
                f"in {prev.source_file} and {r.source_file}; counted once.",
                content_id=r.content_id, expected="one snapshot", actual="duplicate row",
                evidence={"content_id": r.content_id, "captured_at": r.captured_at,
                          "views": r.views},
                source_files=[prev.source_file, r.source_file]))
            continue
        seen[k] = r

    # published deliverables without any analytics
    covered = {r.content_id for r in analytics if r.content_id}
    for cid, dv in sorted(deliverables_by_content.items()):
        if cid in covered:
            continue
        if dv.get("published_at"):
            exceptions.append(make(
                "ANALYTICS_MISSING",
                f"Published content {cid} has no analytics snapshot.",
                creator_id=dv.get("creator_id"), content_id=cid,
                expected="analytics snapshot", actual="none found",
                evidence={"content_id": cid, "platform": dv.get("platform"),
                          "content_type": dv.get("content_type"),
                          "published_at": dv.get("published_at")},
                source_files=[dv.get("source_file", "")]))

    # low-confidence screenshots
    for r in analytics:
        if r.source_type == "screenshot" and r.needs_verification:
            exceptions.append(make(
                "SCREENSHOT_REVIEW",
                f"Screenshot metrics for {r.content_id} have confidence "
                f"{r.confidence:.0%} (< threshold); excluded from totals until verified.",
                creator_id=r.creator_id, content_id=r.content_id,
                expected=f">= configured confidence", actual=f"{r.confidence:.0%}",
                evidence={"file": r.source_file, "views": r.views, "reach": r.reach,
                          "confidence": r.confidence},
                source_files=[r.source_file]))
    return exceptions, []


def engagement_rate(latest: dict[str, AnalyticsRecord]) -> dict:
    """Campaign-level ER computed only from summed reach (never averaged ERs)."""
    reach = sum((r.reach or 0) for r in latest.values())
    eng = sum(_engagements(r) for r in latest.values())
    er = round(eng / reach * 100, 2) if reach else None
    return {"reach": reach, "engagements": eng, "engagement_rate_pct": er}


def _engagements(r: AnalyticsRecord) -> int:
    return sum((getattr(r, f) or 0) for f in ("likes", "comments", "saves", "shares"))
