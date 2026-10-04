"""Financial reconciliation: contract <-> invoice <-> payout rules."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reconciliation.financial import reconcile_financials  # noqa: E402
from schemas.contract import Contract  # noqa: E402
from schemas.invoice import Invoice  # noqa: E402
from schemas.payout import Payout  # noqa: E402


def _c(cid, fee):
    return Contract(contract_id=f"CT-{cid}", campaign_id="CMP", creator_id=cid,
                    source_file="contract.pdf", agreed_fee=fee)


def _i(num, cid, amount):
    return Invoice(invoice_id=num, invoice_number=num, campaign_id="CMP",
                   creator_id=cid, source_file=f"{num}.pdf", amount=amount)


def _p(pid, num, cid, amount, status="Paid"):
    return Payout(payout_id=pid, invoice_number=num, creator_id=cid,
                  amount=amount, status=status, source_file="payouts.xlsx")


def test_invoice_matches_contract_passes():
    rows, excs = reconcile_financials([_c("ST-001", 800)], [_i("INV-1", "ST-001", 800)], [])
    assert rows[0]["status"] != "REVIEW REQUIRED"
    assert not [e for e in excs if e.exception_type == "PAYMENT_VARIANCE"]


def test_invoice_above_contract_is_payment_variance():
    rows, excs = reconcile_financials([_c("ST-002", 1200)], [_i("INV-2", "ST-002", 1350)], [])
    var = [e for e in excs if e.exception_type == "PAYMENT_VARIANCE"]
    assert len(var) == 1
    assert var[0].severity == "HIGH"
    assert var[0].expected_value == 1200 and var[0].actual_value == 1350
    assert rows[0]["variance"] == 150.0


def test_invoice_below_contract_is_underbilled():
    _, excs = reconcile_financials([_c("ST-003", 900)], [_i("INV-3", "ST-003", 750)], [])
    assert any(e.exception_type == "INVOICE_UNDERBILLED" for e in excs)


def test_missing_payout_is_pending():
    rows, excs = reconcile_financials([_c("ST-004", 600)], [_i("INV-4", "ST-004", 600)], [])
    assert any(e.exception_type == "PAYMENT_PENDING" for e in excs) or rows[0]["status"] == "PENDING PAYMENT"


def test_payout_mismatch_is_payout_variance():
    _, excs = reconcile_financials(
        [_c("ST-005", 500)], [_i("INV-5", "ST-005", 500)],
        [_p("PAY-1", "INV-5", "ST-005", 450)])
    pv = [e for e in excs if e.exception_type == "PAYOUT_VARIANCE"]
    assert len(pv) == 1
    assert pv[0].evidence["difference"] == -50.0


def test_duplicate_invoice_number_detected():
    _, excs = reconcile_financials(
        [_c("ST-006", 700)],
        [_i("INV-6", "ST-006", 700), _i("INV-6", "ST-006", 700)], [])
    assert any(e.exception_type == "DUPLICATE_INVOICE" for e in excs)


def test_zero_amount_pending_line_is_not_paid():
    rows, _ = reconcile_financials(
        [_c("ST-007", 800)], [_i("INV-7", "ST-007", 800)],
        [_p("PAY-7", "INV-7", "ST-007", 0, status="Pending")])
    assert rows[0]["paid"] == 0
