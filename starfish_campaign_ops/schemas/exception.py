"""Exception queue item with full evidence trail."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from schemas.campaign import Strict

SEVERITIES = ("HIGH", "MEDIUM", "LOW")
STATUSES = ("OPEN", "IN_REVIEW", "RESOLVED", "IGNORED")


class ExceptionItem(Strict):
    exception_id: str
    campaign_id: str = ""
    creator_id: Optional[str] = None
    content_id: Optional[str] = None
    exception_type: str            # PAYMENT_VARIANCE, MISSING_DELIVERABLE, ...
    severity: str                  # HIGH | MEDIUM | LOW
    description: str
    expected_value: Optional[Any] = None
    actual_value: Optional[Any] = None
    evidence: dict = {}            # human-readable field -> value
    source_files: list[str] = []
    status: str = "OPEN"
    created_at: datetime = None  # type: ignore[assignment]
    resolved_at: Optional[datetime] = None

    def model_post_init(self, _ctx: Any) -> None:
        if self.created_at is None:
            self.created_at = datetime.utcnow()
