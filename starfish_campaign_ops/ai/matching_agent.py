"""AI-assisted ambiguous matching (optional).

Only ever *suggests*; the decision policy (auto-accept vs human review) stays
in deterministic code (matching/confidence.py). The suggestion is surfaced in
the evidence panel, never auto-applied.
"""
from __future__ import annotations


def suggest_match(raw_value: str, candidates: list[dict]) -> dict | None:
    """candidates: [{creator_id, name, handle}] -> {creator_id, reason} | None."""
    from ai.qwen_client import complete_json, is_available

    if not is_available() or not candidates:
        return None
    prompt = (
        "Which existing creator does this record refer to? Answer strict JSON "
        '{"creator_id": ... or null, "reason": "..."} - null if genuinely unsure.\n\n'
        f"Record: {raw_value}\nCandidates: {candidates}")
    out = complete_json("You are a careful data-linking assistant.", prompt)
    if not out:
        return None
    cid = out.get("creator_id")
    if cid and any(c["creator_id"] == cid for c in candidates):
        return {"creator_id": cid, "reason": str(out.get("reason", ""))[:300]}
    return None
