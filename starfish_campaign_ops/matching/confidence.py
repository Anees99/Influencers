"""Match confidence policy.

Scores are produced by deterministic algorithms only. The thresholds decide
between auto-accept and human review - uncertain creators are NEVER silently
merged.
"""
from __future__ import annotations

from dataclasses import dataclass

from config.settings import settings


@dataclass(frozen=True)
class MatchDecision:
    creator_id: str | None
    score: float
    method: str        # id | handle | email | exact_name | fuzzy | none
    reason: str
    needs_review: bool


def decide(creator_id: str | None, score: float, method: str, reason: str) -> MatchDecision:
    if creator_id is None:
        return MatchDecision(None, round(score, 3), "none", reason or "no candidate found", False)
    review = method == "fuzzy" and score < settings.auto_accept
    return MatchDecision(creator_id, round(score, 3), method, reason, review)
