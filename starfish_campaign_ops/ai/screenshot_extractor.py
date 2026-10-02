"""Vision extraction of platform-insight screenshots (AI mode only).

Demo mode substitutes the generator's sidecar file (see ingestion/router.py)
so the pipeline shape is identical without shipping an OCR/vision model.
Results below the configured confidence threshold become REVIEW exceptions -
uncertain vision output is never authoritative.
"""
from __future__ import annotations

import base64


def extract_metrics(png_bytes: bytes) -> dict | None:
    from ai.qwen_client import complete_json, is_available

    if not is_available():
        return None
    b64 = base64.b64encode(png_bytes).decode()
    prompt = (
        "This is a social-platform insights screenshot. Extract strict JSON: "
        '{"views":int|null,"reach":int|null,"likes":int|null,"comments":int|null,'
        '"shares":int|null,"saves":int|null,"confidence":float}. '
        "Use null for anything unreadable. Never guess.")
    out = complete_json("You are a precise OCR assistant.", prompt)
    if out is None:
        return None
    out["_image_b64_len"] = len(b64)
    return out
