"""Payout (bank/payment feed) record."""
from __future__ import annotations

from typing import Optional

from schemas.campaign import Strict


class Payout(Strict):
    payout_id: str
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    creator_id: Optional[str] = None
    creator_raw: str = ""
    amount: Optional[float] = None
    currency: str = "USD"
    payment_date: Optional[str] = None
    status: str = "Paid"
    source_file: str = ""
    match_confidence: float = 0.0
    match_method: str = ""
    match_reason: str = ""
