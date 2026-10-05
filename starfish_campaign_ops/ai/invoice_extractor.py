"""Invoice extraction (same pattern as contracts; deterministic fallback)."""
from __future__ import annotations

from schemas.invoice import InvoiceExtraction


def validate_invoice_payload(raw: dict) -> InvoiceExtraction:
    allowed = set(InvoiceExtraction.model_fields)
    clean = {k: v for k, v in raw.items() if k in allowed and v is not None}
    return InvoiceExtraction(**clean)


def extract_invoice(pdf_text: str, fallback_raw: dict, filename: str) -> InvoiceExtraction:
    from ai.qwen_client import complete_json, is_available

    if is_available():
        prompt = (
            "Extract invoice fields as strict JSON with keys: invoice_number, "
            "creator_name, instagram_handle, campaign_name, amount (number), "
            "currency, invoice_date, due_date, tax, commission. Use null when "
            "not present. NEVER invent data.\n\n" + pdf_text[:6000])
        out = complete_json("You are a precise document-extraction assistant.", prompt)
        if out:
            src = {"source_file": filename, "source_type": "pdf", "page": 1}
            merged = {**fallback_raw, **{k: v for k, v in out.items() if v is not None}}
            merged["source"] = src
            merged.setdefault("warnings", [])
            merged["confidence"] = min(float(merged.get("confidence", 0.9)), 0.9)
            return validate_invoice_payload(merged)
    return validate_invoice_payload(fallback_raw)
