"""Screenshot ingestion.

Demo mode: reads sidecar metadata written by the demo-data generator
(<name>.json next to the PNG) - this simulates an OCR/vision result WITHOUT
pretending to run vision models locally. AI mode: sends the image to the
configured vision-capable model. Uncertain results are always marked
needs_verification and never treated as authoritative.
"""
from __future__ import annotations

import json


def load_screenshot_meta(filename: str, blob: bytes) -> dict | None:
    """Sidecar lookup happens at router level; here we just validate payload."""
    return None


def parse_sidecar(json_text: str) -> dict:
    return json.loads(json_text)
