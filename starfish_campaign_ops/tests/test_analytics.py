"""Analytics reconciliation: snapshot dedupe, missing coverage, ER math."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reconciliation.analytics import (  # noqa: E402
    engagement_rate,
    latest_snapshots,
    reconcile_analytics,
)
from schemas.analytics import AnalyticsRecord  # noqa: E402


def _rec(cid, views, captured="2026-03-10", src="a.csv", **kw):
    return AnalyticsRecord(analytics_id=f"AN-{cid}-{captured}-{src}", campaign_id="CMP",
                           creator_id="ST-001", content_id=cid, platform="Instagram",
                           content_type="Reel", publish_date="2026-03-05",
                           views=views, reach=kw.get("reach", views // 2),
                           impressions=views, likes=kw.get("likes", 100),
                           comments=10, saves=5, shares=5,
                           captured_at=captured, source_file=src)


def test_latest_snapshot_wins_no_double_count():
    early = _rec("IG-1", 100_000, captured="2026-06-10")
    late = _rec("IG-1", 125_000, captured="2026-06-12")
    latest = latest_snapshots([early, late])
    assert len(latest) == 1
    assert latest["IG-1"].views == 125_000


def test_identical_duplicate_snapshot_flagged_but_counted_once():
    r1 = _rec("IG-2", 50_000, captured="2026-06-10", src="export1.csv")
    r2 = _rec("IG-2", 50_000, captured="2026-06-10", src="export1.csv")
    r2.analytics_id = "AN-dup"
    excs, _ = reconcile_analytics([r1, r2], {})
    assert any(e.exception_type == "DUPLICATE_ANALYTICS_SNAPSHOT" for e in excs)
    assert len(latest_snapshots([r1, r2])) == 1


def test_published_content_without_analytics_is_missing():
    dv = {"IG-7": {"creator_id": "ST-001", "published_at": "2026-03-08",
                   "platform": "Instagram", "content_type": "Reel",
                   "source_file": "deliverables.xlsx"}}
    excs, _ = reconcile_analytics([], dv)
    am = [e for e in excs if e.exception_type == "ANALYTICS_MISSING"]
    assert len(am) == 1 and am[0].severity == "MEDIUM"


def test_engagement_rate_math_and_zero_reach_guard():
    latest = {"IG-1": _rec("IG-1", 1000, reach=800, likes=50)}
    er = engagement_rate(latest)
    # engagements = likes+comments+saves+shares = 50+10+5+5 = 70; 70/800*100
    assert er["engagements"] == 70
    assert er["engagement_rate_pct"] == round(70 / 800 * 100, 2)
    zero = {"IG-2": AnalyticsRecord(
        analytics_id="x", campaign_id="C", content_id="IG-2", platform="Instagram",
        content_type="Reel", views=100, reach=0, likes=1, comments=0, saves=0, shares=0)}
    assert engagement_rate(zero)["engagement_rate_pct"] is None
