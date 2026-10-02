"""Row helpers: convert sqlite Rows back into Pydantic schemas."""
from __future__ import annotations

import json

from schemas.analytics import AnalyticsRecord
from schemas.contract import Contract
from schemas.creator import Creator
from schemas.deliverable import Deliverable
from schemas.exception import ExceptionItem
from schemas.invoice import Invoice
from schemas.payout import Payout

CREATOR_KEYS = {"creator_id", "canonical_name", "instagram_handle", "tiktok_handle", "email"}


def row_to_contract(row) -> Contract:
    d = dict(row)
    d["deliverables_json"] = json.loads(d.get("deliverables_json") or "[]")
    return Contract(**d)


def row_to_invoice(row) -> Invoice:
    return Invoice(**dict(row))


def row_to_payout(row) -> Payout:
    return Payout(**dict(row))


def row_to_deliverable(row) -> Deliverable:
    d = dict(row)
    d["required"] = bool(d.get("required", 1))
    return Deliverable(**d)


def row_to_analytics(row) -> AnalyticsRecord:
    d = dict(row)
    d["needs_verification"] = bool(d.get("needs_verification", 0))
    return AnalyticsRecord(**d)


def row_to_exception(row) -> ExceptionItem:
    d = dict(row)
    for k in ("expected_value", "actual_value", "evidence"):
        d[k] = json.loads(d[k]) if d.get(k) else ({} if k == "evidence" else None)
    d["source_files"] = json.loads(d.get("source_files") or "[]")
    return ExceptionItem(**d)


def row_to_creator(row) -> Creator:
    return Creator(**{k: v for k, v in dict(row).items() if k in CREATOR_KEYS})
