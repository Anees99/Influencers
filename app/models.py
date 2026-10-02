"""Data models for the campaign reconciliation pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Creator:
    creator_id: str
    display_name: str
    normalized_name: str
    platforms: list[str] = field(default_factory=list)


@dataclass
class Contract:
    contract_id: str
    creator_key: str          # normalized creator name
    deliverable_type: str     # e.g. "1x Instagram Reel"
    agreed_amount: float
    currency: str = "USD"
    status: str = "active"


@dataclass
class Invoice:
    invoice_number: str
    creator_key: str
    amount: float
    currency: str
    period: str               # e.g. "2026-09"
    status: str               # approved / pending / rejected


@dataclass
class Payout:
    payment_ref: str
    creator_key: str
    amount: float
    currency: str
    date: str                 # ISO date string


@dataclass
class Deliverable:
    post_id: str
    creator_key: str
    platform: str
    url: str
    published_date: str
    metrics: dict             # impressions, engagements, clicks, conversions, spend


@dataclass
class ExceptionItem:
    exception_id: str
    severity: str             # high / medium / low
    category: str             # missing_payout / amount_mismatch / ...
    entity: str               # human-readable entity reference
    description: str
    evidence: dict            # field -> value(s) from source records
    status: str = "open"      # open / acknowledged


@dataclass
class ReconResult:
    """Container for one reconciliation section's output."""
    matched: list[dict] = field(default_factory=list)
    exceptions: list[ExceptionItem] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
