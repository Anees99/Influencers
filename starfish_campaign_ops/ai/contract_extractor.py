"""Contract extraction.

DEMO MODE: ingestion/pdf.py regex parser produces a raw field dict, which is
validated here into the strict ContractExtraction schema.
AI MODE: the same PDF text can go through Qwen first; failures fall back to
the deterministic result. Missing values stay null - never invented.
"""
from __future__ import annotations

from schemas.creator import ContractExtraction


def validate_contract_payload(raw: dict) -> ContractExtraction:
    """Coerce a raw extraction dict into the strict schema, dropping unknowns."""
    allowed = set(ContractExtraction.model_fields)
    clean = {k: v for k, v in raw.items() if k in allowed and v is not None}
    if "deliverables" in clean and isinstance(clean["deliverables"], list):
        clean["deliverables"] = [d if isinstance(d, (str, dict)) else str(d)
                                 for d in clean["deliverables"]]
    return ContractExtraction(**clean)


def extract_contract(pdf_text: str, fallback_raw: dict, filename: str) -> ContractExtraction:
    """AI-mode entry point: try Qwen, merge nothing numeric unless validated."""
    from ai.qwen_client import complete_json, is_available

    if is_available():
        prompt = (
            "Extract contract fields as strict JSON with keys: creator_name, "
            "instagram_handle, campaign_name, fee (number), currency, deadline, "
            "deliverables (list of strings), payment_terms, commission, bonus. "
            "Use null when a value is not present. NEVER invent data.\n\n" + pdf_text[:6000])
        out = complete_json("You are a precise document-extraction assistant.", prompt)
        if out:
            src = {"source_file": filename, "source_type": "pdf", "page": 1}
            merged = {**fallback_raw, **{k: v for k, v in out.items() if v is not None}}
            merged["source"] = src
            merged.setdefault("warnings", [])
            merged["confidence"] = min(float(merged.get("confidence", 0.9)), 0.9)
            return validate_contract_payload(merged)
    return validate_contract_payload(fallback_raw)
