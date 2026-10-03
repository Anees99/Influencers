"""Deterministic financial reconciliation. Python decides 1200 != 1350."""
from __future__ import annotations

from config.settings import settings
from reconciliation.exceptions import make
from schemas.contract import Contract
from schemas.invoice import Invoice
from schemas.payout import Payout


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(settings.amount_tol_abs,
                             settings.amount_tol_pct * max(abs(a), abs(b)))


def money(v: float | None) -> str:
    return "n/a" if v is None else f"${v:,.2f}"


def reconcile_financials(contracts: list[Contract], invoices: list[Invoice],
                        payouts: list[Payout]) -> tuple[list[dict], list]:
    """Returns (per-creator financial rows, exceptions)."""
    exceptions: list = []
    by_creator: dict[str, dict] = {}

    for ct in contracts:
        row = by_creator.setdefault(ct.creator_id or "?", {"creator_id": ct.creator_id})
        row["contract_fee"] = round(row.get("contract_fee", 0) + (ct.agreed_fee or 0), 2)
        row.setdefault("contract_files", []).append(
            f"{ct.source_file}" + (f" p.{ct.source_page}" if ct.source_page else ""))
        row["currency"] = ct.currency

    seen_numbers: dict[str, list[Invoice]] = {}
    for iv in invoices:
        seen_numbers.setdefault(iv.invoice_number, []).append(iv)
    for num, group in seen_numbers.items():
        if len(group) > 1:
            files = sorted({g.source_file for g in group})
            exceptions.append(make(
                "DUPLICATE_INVOICE",
                f"Invoice number {num} appears {len(group)} times.",
                creator_id=group[0].creator_id,
                expected="unique invoice number", actual=f"{len(group)} records",
                evidence={"invoice_number": num,
                          "amounts": [g.amount for g in group],
                          "files": files},
                source_files=files))

    for iv in invoices:
        if iv.creator_id is None:
            continue
        row = by_creator.setdefault(iv.creator_id, {"creator_id": iv.creator_id})
        row["invoiced"] = round(row.get("invoiced", 0) + (iv.amount or 0), 2)
        row.setdefault("invoice_details", []).append(
            {"number": iv.invoice_number, "amount": iv.amount,
             "file": iv.source_file + (f" p.{iv.source_page}" if iv.source_page else "")})

    # link payouts to invoices by invoice_number first, creator second
    inv_by_num = {}
    for iv in invoices:
        inv_by_num.setdefault(iv.invoice_number, iv)

    def _paid_status(py) -> bool:
        """A zero-amount row is a placeholder (e.g. a pending line), not money."""
        return py.status.lower() in ("paid", "completed", "sent") and (py.amount or 0) > 0

    paid_by_creator: dict[str, float] = {}
    for py in payouts:
        if not _paid_status(py):
            continue
        target = inv_by_num.get(py.invoice_number or "")
        cid = (target.creator_id if target else py.creator_id)
        if cid is None:
            continue
        paid_by_creator[cid] = round(paid_by_creator.get(cid, 0) + (py.amount or 0), 2)
        if target and not _close(target.amount or 0, py.amount or 0):
            exceptions.append(make(
                "PAYOUT_VARIANCE",
                f"Payout {py.payout_id} ({money(py.amount)}) does not match invoice "
                f"{target.invoice_number} ({money(target.amount)}).",
                creator_id=cid, expected=target.amount, actual=py.amount,
                evidence={"payout_id": py.payout_id, "invoice": target.invoice_number,
                          "invoice_amount": target.amount, "payout_amount": py.amount,
                          "difference": round((py.amount or 0) - (target.amount or 0), 2)},
                source_files=[py.source_file, target.source_file]))

    rows: list[dict] = []
    for cid, row in sorted(by_creator.items(), key=lambda kv: str(kv[0])):
        fee = row.get("contract_fee")
        invoiced = row.get("invoiced", 0)
        paid = paid_by_creator.get(cid, 0)
        variance = round(invoiced - (fee or 0), 2)
        status = "OK"
        if fee is not None and invoiced and not _close(fee, invoiced):
            if invoiced > fee:
                status = "REVIEW REQUIRED"
                exceptions.append(make(
                    "PAYMENT_VARIANCE",
                    f"Invoiced {money(invoiced)} vs contracted {money(fee)} "
                    f"(variance {variance:+,.2f}).",
                    creator_id=cid, expected=fee, actual=invoiced,
                    evidence={"contract": money(fee), "invoice": money(invoiced),
                              "variance": variance,
                              "invoices": row.get("invoice_details", [])},
                    source_files=row.get("contract_files", []) +
                                 [d["file"] for d in row.get("invoice_details", [])]))
            else:
                status = "UNDER-BILLED"
                exceptions.append(make(
                    "INVOICE_UNDERBILLED",
                    f"Invoiced {money(invoiced)} is below contracted {money(fee)} "
                    f"({variance:+,.2f}); confirm remaining deliverables.",
                    creator_id=cid, expected=fee, actual=invoiced,
                    evidence={"contract": money(fee), "invoice": money(invoiced),
                              "variance": variance,
                              "invoices": row.get("invoice_details", [])},
                    source_files=row.get("contract_files", []) +
                                 [d["file"] for d in row.get("invoice_details", [])]))
        elif invoiced and paid == 0:
            status = "PENDING PAYMENT"
            exceptions.append(make(
                "PAYMENT_PENDING",
                f"Invoice(s) totalling {money(invoiced)} have no completed payout.",
                creator_id=cid, expected=invoiced, actual=paid,
                evidence={"invoiced": invoiced, "paid": paid,
                          "invoices": [d["number"] for d in row.get("invoice_details", [])]},
                source_files=[d["file"] for d in row.get("invoice_details", [])]))
        elif paid and not _close(invoiced, paid):
            status = "PAYOUT VARIANCE"   # exception already raised above
        elif invoiced and paid:
            status = "PAID"
        elif fee is not None and not invoiced:
            status = "NOT INVOICED"
        row.update({"creator_id": cid, "contract_fee": fee, "invoiced": invoiced,
                    "paid": paid, "outstanding": round(invoiced - paid, 2),
                    "variance": variance, "status": status})
        rows.append(row)
    return rows, exceptions
