"""Pydantic schemas shared across the pipeline."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Campaign(Strict):
    campaign_id: str
    client_name: str
    campaign_name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    currency: str = "USD"
    platforms: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SourceRef(Strict):
    """Traceability: every extracted value knows where it came from."""
    source_file: str
    source_type: str = "file"          # pdf | csv | xlsx | screenshot
    page: Optional[int] = None


class Warning_(Strict):
    code: str
    message: str
