"""Contract record persisted after extraction/matching."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from schemas.campaign import Strict


class Contract(Strict):
    contract_id: str
    campaign_id: str
    creator_id: Optional[str] = None
    source_file: str = ""
    source_page: Optional[int] = None
    agreed_fee: Optional[float] = None
    currency: str = "USD"
    deadline: Optional[str] = None
    deliverables_json: list[dict] = Field(default_factory=list)  # [{type, count}]
    extraction_confidence: float = 1.0
    match_confidence: float = 0.0
    match_method: str = ""
    match_reason: str = ""
