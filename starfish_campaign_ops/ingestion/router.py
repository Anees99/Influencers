"""File router: classify an uploaded file and turn it into normalized records.

One bad file must never crash the campaign: every parse path returns either
records + warnings, or a clean error string that the UI displays.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import csv
import itertools

from ingestion import csv_ingest as csv_ing
from ingestion import excel as excel_ing
from ingestion import pdf as pdf_ing
from ingestion.normalization import (normalize_platform, parse_amount,
                                     parse_date_any, parse_deliverables,
                                     parse_metric)
from schemas.analytics import AnalyticsRecord
from schemas.contract import Contract
from schemas.deliverable import Deliverable
from schemas.invoice import Invoice, InvoiceExtraction
from schemas.payout import Payout

CATEGORIES = ["Campaign Brief", "Contract", "Invoice", "Payout",
              "Analytics Export", "Deliverables", "Approval", "Screenshot"]

_KEYWORDS = {
    "Contract": ("contract", "agreement"),
    "Invoice": ("invoice", "inv-"),
    "Payout": ("payout", "payment"),
    "Analytics Export": ("analytic", "insight", "metrics", "performance"),
    "Deliverables": ("deliverable", "content_tracker", "tracker"),
    "Approval": ("approval",),
    "Campaign Brief": ("brief",),
    "Screenshot": (),
}


def guess_category(filename: str, file_type: str) -> str | None:
    n = filename.lower()
    if file_type in ("png", "jpg", "jpeg"):
        return "Screenshot"
    for cat, kws in _KEYWORDS.items():
        if any(k in n for k in kws):
            return cat
    return None


@dataclass
class FileResult:
    category: str
    filename: str
    file_type: str
    status: str = "PROCESSED"          # PROCESSED | ERROR
    contracts: list[Contract] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    payouts: list[Payout] = field(default_factory=list)
    deliverables: list[Deliverable] = field(default_factory=list)
    analytics: list[AnalyticsRecord] = field(default_factory=list)
    brief: dict | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def records_extracted(self) -> int:
        return (len(self.contracts) + len(self.invoices) + len(self.payouts)
                + len(self.deliverables) + len(self.analytics) + (1 if self.brief else 0))


def _ftype(filename: str, blob: bytes) -> str:
    low = filename.lower()
    if low.endswith(".pdf") or blob[:4] == b"%PDF":
        return "pdf"
    if low.endswith((".xlsx", ".xls")):
        return "xlsx"
    if low.endswith(".csv"):
        return "csv"
    if low.endswith((".png", ".jpg", ".jpeg")):
        return low.rsplit(".", 1)[-1]
    return "unknown"


# ------------------------------------------------------------------ routers

_id_seq = itertools.count(1)


def _rid(prefix: str) -> str:
    """Globally unique record id (per-file counters collide across files)."""
    return f"{prefix}-{next(_id_seq):05d}"


def process_file(filename: str, blob: bytes, category: str,
                 campaign_id: str = "CMP-RAMADAN-26",
                 sidecar: dict | None = None) -> FileResult:
    ftype = _ftype(filename, blob)
    res = FileResult(category=category, filename=filename, file_type=ftype)
    try:
        if category == "Contract":
            _route_contract(res, blob, campaign_id)
        elif category == "Invoice":
            _route_invoice(res, blob, campaign_id)
        elif category == "Payout":
            _route_payout(res, blob, campaign_id)
        elif category == "Analytics Export":
            _route_analytics(res, blob, campaign_id)
        elif category in ("Deliverables", "Approval"):
            _route_deliverables(res, blob, campaign_id)
        elif category == "Campaign Brief":
            _route_brief(res, blob)
        elif category == "Screenshot":
            _route_screenshot(res, campaign_id, sidecar)
        else:
            raise ValueError(f"unknown category '{category}'")
    except (ValueError, csv_ing.CsvError, excel_ing.ExcelError) as exc:
        res.status = "ERROR"
        res.error = str(exc)
    except Exception as exc:  # never let one file kill the run
        res.status = "ERROR"
        res.error = f"unexpected error ({type(exc).__name__}: {exc})"
    return res


def _rows_for(res: FileResult, blob: bytes) -> tuple[list[dict], list[str]]:
    if res.file_type == "pdf":
        pages = pdf_ing.extract_text(blob)
        return [{"_pdf_text": p, "_page": i + 1} for i, p in enumerate(pages)], []
    if res.file_type == "csv":
        return csv_ing.read_rows(blob, res.filename)
    if res.file_type == "xlsx":
        return excel_ing.read_rows(blob, res.filename)
    raise ValueError(f"{res.filename}: unsupported file type '{res.file_type}' "
                     "(accepted: PDF, CSV, XLSX, PNG/JPG screenshot)")


def _route_contract(res: FileResult, blob: bytes, campaign_id: str) -> None:
    rows, warns = _rows_for(res, blob)
    res.warnings.extend(warns)
    for idx, row in enumerate(rows, start=1):
        if "_pdf_text" in row:
            fields = pdf_ing.parse_contract_text(row["_pdf_text"])
            page = row["_page"]
            creator_name = fields["creator_name"]
            handle = fields["instagram_handle"]
            fee, cur = parse_amount(fields["fee_raw"])
            deadline = parse_date_any(fields["deadline_raw"])[1]
            deliv = parse_deliverables(fields["deliverables_text"] or "")
            conf = 0.95 if (creator_name and fee is not None and deliv) else 0.7
            extraction_warns = []
            if creator_name is None:
                extraction_warns.append("creator name not found")
            if fee is None:
                extraction_warns.append("fee not found")
            if not deliv:
                extraction_warns.append("no deliverables parsed")
            raw = {"creator_name": creator_name, "instagram_handle": handle,
                   "campaign_name": fields["campaign_name"], "fee": fee,
                   "currency": cur or "USD", "deadline": deadline,
                   # ContractExtraction.deliverables is list[str]; the typed
                   # [{type,count}] structure is kept on the Contract record.
                   "deliverables": [f"{d['count']} {d['type']}" for d in deliv],
                   "payment_terms": fields["payment_terms"],
                   "commission": parse_amount(fields["commission_raw"])[0],
                   "bonus": parse_amount(fields["bonus_raw"])[0],
                   "warnings": extraction_warns, "confidence": conf,
                   "source": {"source_file": res.filename, "source_type": "pdf",
                              "page": page}}
            if creator_name is None and fee is None and not deliv:
                # Nothing recoverable from this page — treat the file as a
                # per-file ERROR (e.g. corrupt contract) without crashing
                # the rest of the campaign batch.
                raise ValueError(
                    f"{res.filename} (page {page}): no creator, fee or "
                    "deliverables could be extracted — unreadable or "
                    "corrupt contract document")
            from ai.contract_extractor import validate_contract_payload
            ext = validate_contract_payload(raw)
            res.warnings.extend(ext.warnings)
            res.contracts.append(Contract(
                contract_id=_rid("CT"), campaign_id=campaign_id,
                source_file=res.filename, source_page=ext.source.page if ext.source else None,
                agreed_fee=ext.fee, currency=ext.currency, deadline=ext.deadline,
                deliverables_json=_deliv_dicts(ext),
                extraction_confidence=ext.confidence,
            ))
            # store extracted identity strings for the matching stage
            res.contracts[-1].__dict__["_extracted"] = {
                "creator_name": ext.creator_name, "handle": ext.instagram_handle}
        else:
            # tabular contracts (CSV/XLSX)
            name = row.get("creator") or row.get("creator_name")
            fee, cur = parse_amount(row.get("amount") or row.get("fee"))
            if not name or fee is None:
                res.warnings.append(f"row {idx}: missing creator or amount - skipped")
                continue
            deadline = parse_date_any(row.get("deadline"))[1]
            deliv = parse_deliverables(row.get("deliverable") or row.get("deliverables") or "")
            res.contracts.append(Contract(
                contract_id=str(row.get("contract_id") or f"CT-{idx:03d}"),
                campaign_id=campaign_id, source_file=res.filename,
                agreed_fee=fee, currency=cur or row.get("currency") or "USD",
                deadline=deadline,
                deliverables_json=deliv, extraction_confidence=1.0,
            ))
            res.contracts[-1].__dict__["_extracted"] = {
                "creator_name": str(name), "handle": row.get("handle")}


def _deliv_dicts(ext) -> list[dict]:
    out = []
    for d in ext.deliverables:
        if isinstance(d, dict):
            out.append(d)
        else:
            out.extend(parse_deliverables(str(d)))
    return out


def _route_invoice(res: FileResult, blob: bytes, campaign_id: str) -> None:
    rows, warns = _rows_for(res, blob)
    res.warnings.extend(warns)
    for idx, row in enumerate(rows, start=1):
        if "_pdf_text" in row:
            fields = pdf_ing.parse_invoice_text(row["_pdf_text"])
            amount, cur = parse_amount(fields["amount_raw"])
            extraction_warns = []
            if not fields["invoice_number"]:
                extraction_warns.append("invoice number not found")
            if amount is None:
                extraction_warns.append("amount not found")
            if not fields["creator_name"] and not fields["instagram_handle"]:
                extraction_warns.append("no creator identified")
            conf = 0.95 if not extraction_warns else 0.7
            raw = {"invoice_number": fields["invoice_number"],
                   "creator_name": fields["creator_name"],
                   "instagram_handle": fields["instagram_handle"],
                   "campaign_name": fields["campaign_name"], "amount": amount,
                   "currency": cur or "USD",
                   "invoice_date": parse_date_any(fields["invoice_date_raw"])[1],
                   "due_date": parse_date_any(fields["due_date_raw"])[1],
                   "tax": parse_amount(fields["tax_raw"])[0], "commission": None,
                   "warnings": extraction_warns, "confidence": conf,
                   "source": {"source_file": res.filename, "source_type": "pdf",
                              "page": row["_page"]}}
            from ai.invoice_extractor import validate_invoice_payload
            ext = validate_invoice_payload(raw)
            res.warnings.extend(ext.warnings)
            res.invoices.append(Invoice(
                invoice_id=_rid("IV"),
                invoice_number=ext.invoice_number or f"AUTO-{idx:03d}",
                campaign_id=campaign_id, source_file=res.filename,
                source_page=row["_page"], amount=ext.amount, currency=ext.currency,
                invoice_date=ext.invoice_date, due_date=ext.due_date, tax=ext.tax,
                extraction_confidence=ext.confidence,
            ))
            res.invoices[-1].__dict__["_extracted"] = {
                "creator_name": ext.creator_name, "handle": ext.instagram_handle}
        else:
            num = row.get("invoice_number")
            amount, cur = parse_amount(row.get("amount"))
            name = row.get("creator") or row.get("creator_name")
            if not num or amount is None:
                res.warnings.append(f"row {idx}: missing invoice number or amount - skipped")
                continue
            res.invoices.append(Invoice(
                invoice_id=_rid("IV"), invoice_number=str(num),
                campaign_id=campaign_id, source_file=res.filename, amount=amount,
                currency=cur or row.get("currency") or "USD",
                invoice_date=parse_date_any(row.get("invoice_date"))[1],
                due_date=parse_date_any(row.get("due_date"))[1],
                extraction_confidence=1.0))
            res.invoices[-1].__dict__["_extracted"] = {
                "creator_name": name, "handle": row.get("handle")}


def _route_payout(res: FileResult, blob: bytes, campaign_id: str) -> None:
    rows, warns = _rows_for(res, blob)
    res.warnings.extend(warns)
    for idx, row in enumerate(rows, start=1):
        pid = row.get("payout_id") or f"PAY-{idx:04d}"
        amount, cur = parse_amount(row.get("amount"))
        name = row.get("creator") or row.get("creator_name") or ""
        if amount is None:
            res.warnings.append(f"row {idx} ({pid}): invalid amount - skipped")
            continue
        res.payouts.append(Payout(
            payout_id=str(pid), invoice_number=row.get("invoice_number"),
            creator_raw=str(name), amount=amount,
            currency=cur or row.get("currency") or "USD",
            payment_date=parse_date_any(row.get("payment_date"))[1],
            status=str(row.get("status") or "Paid"), source_file=res.filename))


def _route_analytics(res: FileResult, blob: bytes, campaign_id: str) -> None:
    rows, warns = _rows_for(res, blob)
    res.warnings.extend(warns)
    for idx, row in enumerate(rows, start=1):
        cid = row.get("content_id")
        if not cid:
            res.warnings.append(f"row {idx}: no content id - skipped")
            continue
        rec = AnalyticsRecord(
            analytics_id=_rid("AN"), campaign_id=campaign_id,
            creator_raw=str(row.get("creator") or ""),
            handle_raw=row.get("handle"), content_id=str(cid),
            platform=normalize_platform(row.get("platform") or ""),
            content_type=str(row.get("content_type") or ""),
            publish_date=parse_date_any(row.get("publish_date"))[1],
            views=parse_metric(row.get("views")), reach=parse_metric(row.get("reach")),
            impressions=parse_metric(row.get("impressions")),
            likes=parse_metric(row.get("likes")), comments=parse_metric(row.get("comments")),
            saves=parse_metric(row.get("saves")), shares=parse_metric(row.get("shares")),
            watch_time=(float(row["watch_time"]) if str(row.get("watch_time") or "").replace(".", "", 1).isdigit() else None),
            captured_at=parse_date_any(row.get("captured_at"))[1] or str(row.get("captured_at") or ""),
            source_file=res.filename, source_type="export", confidence=1.0)
        res.analytics.append(rec)


def _route_deliverables(res: FileResult, blob: bytes, campaign_id: str) -> None:
    rows, warns = _rows_for(res, blob)
    res.warnings.extend(warns)
    for idx, row in enumerate(rows, start=1):
        did = row.get("deliverable_id") or f"DV-{idx:04d}"
        req_raw = row.get("required")
        required = True if req_raw is None else str(req_raw).lower() not in ("false", "0", "no", "n")
        res.deliverables.append(Deliverable(
            deliverable_id=str(did), campaign_id=campaign_id,
            content_id=row.get("content_id"),
            platform=normalize_platform(row.get("platform") or ""),
            content_type=str(row.get("content_type") or ""),
            required=required,
            published_at=parse_date_any(row.get("published_at"))[1],
            approval_status=str(row.get("approval_status") or "pending").lower(),
            source_file=res.filename))
        res.deliverables[-1].__dict__["_extracted"] = {
            "creator_name": row.get("creator") or row.get("creator_name")}


def _route_brief(res: FileResult, blob: bytes) -> None:
    rows, warns = _rows_for(res, blob)
    res.warnings.extend(warns)
    if not rows:
        raise ValueError(f"{res.filename}: brief has no readable content")
    first = rows[0]
    if "_pdf_text" in first:
        text = "\n".join(r["_pdf_text"] for r in rows)
        res.brief = {"kind": "text", "text": text}
    else:
        res.brief = {"kind": "table", "rows": rows}


def _route_screenshot(res: FileResult, campaign_id: str, sidecar: dict | None) -> None:
    """Demo mode uses the generator's sidecar to simulate vision extraction."""
    from config.settings import settings
    if sidecar is None:
        raise ValueError(
            f"{res.filename}: no OCR/vision result available in demo mode. "
            "Include the matching .json sidecar, or enable AI mode.")
    conf = float(sidecar.get("confidence", 0.0))
    needs_ver = conf < settings.screenshot_confidence_min
    m = sidecar.get("metrics", {})
    res.analytics.append(AnalyticsRecord(
        analytics_id=f"SS-{sidecar.get('content_id', 'x')}",
        campaign_id=campaign_id,
        creator_raw=sidecar.get("creator", ""), handle_raw=sidecar.get("handle"),
        content_id=sidecar.get("content_id"),
        platform=normalize_platform(sidecar.get("platform") or "Instagram"),
        content_type=sidecar.get("content_type") or "Reel",
        publish_date=sidecar.get("publish_date"),
        views=parse_metric(m.get("views")), reach=parse_metric(m.get("reach")),
        impressions=parse_metric(m.get("impressions")),
        likes=parse_metric(m.get("likes")), comments=parse_metric(m.get("comments")),
        saves=parse_metric(m.get("saves")), shares=parse_metric(m.get("shares")),
        captured_at=sidecar.get("captured_at"),
        source_file=res.filename, source_type="screenshot",
        confidence=conf, needs_verification=needs_ver))
    if needs_ver:
        res.warnings.append(
            f"screenshot confidence {conf:.0%} below threshold "
            f"{settings.screenshot_confidence_min:.0%} - flagged for verification")
