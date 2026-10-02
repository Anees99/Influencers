"""Analytics snapshot record (one row per export capture)."""
from __future__ import annotations

from typing import Optional

from schemas.campaign import Strict


class AnalyticsRecord(Strict):
    analytics_id: str
    campaign_id: str
    creator_id: Optional[str] = None
    creator_raw: str = ""
    handle_raw: Optional[str] = None
    content_id: Optional[str] = None
    platform: str = ""
    content_type: str = ""
    publish_date: Optional[str] = None
    views: Optional[int] = None
    reach: Optional[int] = None
    impressions: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    saves: Optional[int] = None
    shares: Optional[int] = None
    watch_time: Optional[float] = None
    captured_at: Optional[str] = None
    source_file: str = ""
    source_type: str = "export"        # export | screenshot
    confidence: float = 1.0
    needs_verification: bool = False
