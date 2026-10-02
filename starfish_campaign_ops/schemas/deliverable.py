"""Deliverable tracking record (content tracker rows)."""
from __future__ import annotations

from typing import Optional

from schemas.campaign import Strict


class Deliverable(Strict):
    deliverable_id: str
    campaign_id: str
    creator_id: Optional[str] = None
    content_id: Optional[str] = None
    platform: str = ""
    content_type: str = ""
    required: bool = True
    published_at: Optional[str] = None
    approval_status: str = "pending"   # approved | pending | rejected | draft
    source_file: str = ""
    match_confidence: float = 0.0
    match_method: str = ""
    match_reason: str = ""
