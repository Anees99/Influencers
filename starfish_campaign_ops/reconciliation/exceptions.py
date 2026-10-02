"""Exception factory + stable IDs."""
from __future__ import annotations

import itertools
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

_counter = itertools.count(1)


def make(exception_type: str, description: str, *, campaign_id: str = "",
         creator_id: str | None = None, content_id: str | None = None,
         expected: Any = None, actual: Any = None,
         evidence: dict | None = None, source_files: list[str] | None = None) -> ExceptionItem:
    return ExceptionItem(
        exception_id=f"EX-{next(_counter):03d}",
        campaign_id=campaign_id, creator_id=creator_id, content_id=content_id,
        exception_type=exception_type,
        severity=SEVERITY.get(exception_type, "LOW"),
        description=description, expected_value=expected, actual_value=actual,
        evidence=evidence or {}, source_files=source_files or [])


def reset_counter() -> None:
    global _counter
    _counter = itertools.count(1)
