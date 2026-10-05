"""PDF text extraction + deterministic contract/invoice field parsers.

In DEMO MODE these regex parsers do the extraction (fully local, no LLM).
In AI MODE the same text can be handed to a Qwen-compatible extractor; if
that fails we fall back here automatically.
"""
from __future__ import annotations

import re


def extract_text(blob: bytes) -> list[str]:
    """Return one string per page. Raises ValueError on corrupt PDFs."""
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(stream=blob, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"corrupt or unreadable PDF ({exc})") from exc
    if doc.page_count == 0:
        raise ValueError("PDF contains no pages")
    return [page.get_text("text") for page in doc]


# ---------------------------------------------------------------- field labels
_LABELS = {
    "creator": r"Creator\s*:?\s*\n?\s*(.+)",
    "instagram": r"(?:Instagram|Handle)\s*:?\s*\n?\s*(@[\w.\-]+)",
    "campaign": r"Campaign\s*:?\s*\n?\s*(.+)",
    "fee": r"(?:Fee|Total Fee|Agreed Fee)\s*:?\s*\n?\s*(USD\s*[\d,.]+|\$[\d,.]+)",
    "deadline": r"(?:Deadline|Publication Deadline)\s*:?\s*\n?\s*(.+)",
    "payment_terms": r"Payment Terms\s*:?\s*\n?\s*(.+)",
    "commission": r"Commission\s*:?\s*\n?\s*(USD\s*[\d,.]+|\$[\d,.]+|\d+(?:\.\d+)?%)",
    "bonus": r"(?:Performance )?Bonus\s*:?\s*\n?\s*(USD\s*[\d,.]+|\$[\d,.]+)",
    "invoice_number": r"(INV-\d+)",
    "amount_due": r"Amount Due\s*:?\s*\n?\s*(USD\s*[\d,.]+|\$[\d,.]+)",
    "invoice_date": r"Invoice Date\s*:?\s*\n?\s*(.+)",
    "due_date": r"Due Date\s*:?\s*\n?\s*(.+)",
    "tax": r"(?:Tax|VAT)\s*:?\s*\n?\s*(USD\s*[\d,.]+|\$[\d,.]+)",
}


def _find(text: str, key: str) -> str | None:
    m = re.search(_LABELS[key], text, re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).strip()
    return val or None


def _sanitize_creator_name(name: str | None) -> str | None:
    """Guard against documents where the header ('CREATOR AGREEMENT') sits on
    the same line as the 'Creator:' label, so the regex captures
    'AGREEMENT\\nReal Name'. Keep only the plausible name line(s)."""
    if not name:
        return None
    lines = [l.strip() for l in str(name).splitlines() if l.strip()]
    noise = {"agreement", "creator agreement", "contract", "invoice"}
    kept = [l for l in lines if l.lower() not in noise]
    return kept[0] if kept else None


def _deliverables_block(text: str) -> str | None:
    m = re.search(r"Deliverables\s*:?\s*\n(.*?)(?:\n\s*\n|Fee\s*:|Payment Terms|Deadline|$)",
                  text, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


def parse_contract_text(text: str) -> dict:
    """Deterministic contract field extraction from raw PDF text."""
    return {
        "creator_name": _sanitize_creator_name(_find(text, "creator")),
        "instagram_handle": _find(text, "instagram"),
        "campaign_name": _find(text, "campaign"),
        "fee_raw": _find(text, "fee"),
        "deadline_raw": _find(text, "deadline"),
        "payment_terms": _find(text, "payment_terms"),
        "commission_raw": _find(text, "commission"),
        "bonus_raw": _find(text, "bonus"),
        "deliverables_text": _deliverables_block(text),
    }


def parse_invoice_text(text: str) -> dict:
    return {
        "invoice_number": _find(text, "invoice_number"),
        "creator_name": _sanitize_creator_name(_find(text, "creator")),
        "instagram_handle": _find(text, "instagram"),
        "campaign_name": _find(text, "campaign"),
        "amount_raw": _find(text, "amount_due"),
        "invoice_date_raw": _find(text, "invoice_date"),
        "due_date_raw": _find(text, "due_date"),
        "tax_raw": _find(text, "tax"),
    }
