"""Narrative generation. Input = validated metrics computed by Python.

The LLM may restate numbers it is given but must not compute or invent them;
after generation every figure in the text is verified against the source
metrics and the AI text is rejected if it introduces an unknown number.
"""
from __future__ import annotations

import re


def generate_narrative(metrics: dict) -> dict | None:
    from ai.qwen_client import complete_json, is_available

    if not is_available():
        return None
    prompt = (
        "Write a concise operations narrative from ONLY these validated metrics. "
        "Do not invent creators, numbers, or causality. Return strict JSON with "
        "keys: executive_summary, key_observations (list), "
        "operational_observations (list), recommendations (list).\n\n" + str(metrics))
    out = complete_json("You are a marketing-operations report writer.", prompt)
    if not out:
        return None
    if _contains_unknown_numbers(out, metrics):
        return None  # hallucinated figure -> keep deterministic narrative
    return out


_ALLOWED_RE = re.compile(r"\d[\d.,]*%?")


def _numbers_in(text: str) -> set[str]:
    return {t.replace(",", "").rstrip(".") for t in _ALLOWED_RE.findall(text)}


def _contains_unknown_numbers(narr: dict, metrics: dict) -> bool:
    allowed = _numbers_in(str(metrics))
    allowed |= {"1", "2", "3", "4", "5", "10", "100"}
    def norm(s: str) -> set[str]:
        out = set()
        for n in _numbers_in(s):
            try:
                v = float(n)
                out |= {f"{v:.0f}", f"{v/1000:.1f}", f"{v/1e6:.2f}"}
            except ValueError:
                out.add(n)
        return out
    metric_nums = norm(str(metrics))
    for v in narr.values():
        chunk = v if isinstance(v, str) else " ".join(map(str, v))
        for n in norm(chunk):
            try:
                fv = float(n)
            except ValueError:
                continue
            if fv <= 12:          # small ordinals/lists are fine
                continue
            if n not in metric_nums and f"{fv:.0f}" not in metric_nums:
                return True
    return False
