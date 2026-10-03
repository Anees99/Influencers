"""Exception factory + stable IDs."""
from __future__ import annotations

import hashlib
from typing import Any

from schemas.exception import ExceptionItem

SEVERITY = {
    "PAYMENT_VARIANCE": "HIGH",
    "PAYOUT_VARIANCE": "HIGH",
    "MISSING_DELIVERABLE": "HIGH",
    "UNKNOWN_CREATOR": "HIGH",
    "DUPLICATE_INVOICE": "HIGH",
    "INVOICE_UNDERBILLED": "MEDIUM",
    "PAYMENT_PENDING": "MEDIUM",
    "LATE_DELIVERABLE": "MEDIUM",
    "ANALYTICS_MISSING": "MEDIUM",
    "MATCH_REVIEW": "MEDIUM",
    "SCREENSHOT_REVIEW": "MEDIUM",
    "NAME_MISMATCH": "LOW",
    "DUPLICATE_ANALYTICS_SNAPSHOT": "LOW",
}

def _stable_id(exception_type: str, creator_id: str | None, content_id: str | None,
               description: str) -> str:
    """Deterministic exception ID so operator status changes survive re-runs."""
    key = f"{exception_type}|{creator_id or ''}|{content_id or ''}|{description}"
    return "EX-" + hashlib.sha1(key.encode()).hexdigest()[:8].upper()


def make(exception_type: str, description: str, *, campaign_id: str = "",
         creator_id: str | None = None, content_id: str | None = None,
         expected: Any = None, actual: Any = None,
         evidence: dict | None = None, source_files: list[str] | None = None) -> ExceptionItem:
    return ExceptionItem(
        exception_id=_stable_id(exception_type, creator_id, content_id, description),
        campaign_id=campaign_id, creator_id=creator_id, content_id=content_id,
        severity=SEVERITY.get(exception_type, "LOW"),
        description=description, expected_value=expected, actual_value=actual,
        evidence=evidence or {}, source_files=source_files or [])


def reset_counter() -> None:
    """Kept for API compatibility; IDs are now deterministic hashes."""
