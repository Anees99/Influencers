"""Invoice record + strict extraction schema."""
from __future__ import annotations

from typing import Optional

from schemas.campaign import SourceRef, Strict


class InvoiceExtraction(Strict):
    invoice_number: Optional[str] = None
    creator_name: Optional[str] = None
    instagram_handle: Optional[str] = None
    campaign_name: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "USD"
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    tax: Optional[float] = None
    commission: Optional[float] = None
    warnings: list[str] = []
    confidence: float = 1.0
    source: Optional[SourceRef] = None


class Invoice(Strict):
    invoice_id: str
    invoice_number: str
    campaign_id: str
    creator_id: Optional[str] = None
    source_file: str = ""
    source_page: Optional[int] = None
    amount: Optional[float] = None
    currency: str = "USD"
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    tax: Optional[float] = None
    commission: Optional[float] = None
    extraction_confidence: float = 1.0
    match_confidence: float = 0.0
    match_method: str = ""
    match_reason: str = ""
