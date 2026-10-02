"""Creator entity + extraction schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from schemas.campaign import SourceRef, Strict


class Creator(Strict):
    creator_id: str
    canonical_name: str
    instagram_handle: Optional[str] = None
    tiktok_handle: Optional[str] = None
    email: Optional[str] = None


class ContractExtraction(Strict):
    """Strict output of contract extraction (demo parser or Qwen)."""
    creator_name: Optional[str] = None
    instagram_handle: Optional[str] = None
    campaign_name: Optional[str] = None
    fee: Optional[float] = None
    currency: str = "USD"
    deadline: Optional[str] = None
    deliverables: list[str] = Field(default_factory=list)
    payment_terms: Optional[str] = None
    commission: Optional[float] = None
    bonus: Optional[float] = None
    warnings: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    source: Optional[SourceRef] = None
