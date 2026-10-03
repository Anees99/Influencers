"""Creator matching: exact, handle, fuzzy and unknown-handle behaviour.

Uses the real CreatorRegistry API (add / resolve -> MatchDecision with
creator_id, confidence, method, reason).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matching.creator_matching import CreatorRegistry  # noqa: E402


def _registry() -> CreatorRegistry:
    reg = CreatorRegistry()
    reg.add("ST-001", "Sara Ahmed", instagram_handle="@sara.ahmed")
    reg.add("ST-002", "Omar Ali", instagram_handle="@omar.ali")
    return reg


def test_exact_name_match():
    d = _registry().resolve("Sara Ahmed")
    assert d.creator_id == "ST-001"
    assert d.score >= 0.85
    assert d.method in ("exact_name", "id", "handle")


def test_handle_match():
    d = _registry().resolve("@omar.ali")
    assert d.creator_id == "ST-002"
    assert d.score == 1.0


def test_embedded_handle_in_name_string():
    d = _registry().resolve("Sara Ahmed (@sara.ahmed)")
    assert d.creator_id == "ST-001"


def test_creator_id_exact():
    d = _registry().resolve("ST-002")
    assert d.creator_id == "ST-002"
    assert d.score == 1.0


def test_fuzzy_initial_returns_decision_not_silent_drop():
    # "Sara A." must never be silently merged with full confidence; either a
    # reviewable decision or no match is acceptable, but not an error.
    d = _registry().resolve("Sara A.")
    assert 0.0 <= d.score <= 1.0
    if d.creator_id == "ST-001":
        assert d.score < 1.0  # fuzzy, recorded as such


def test_unknown_handle_never_false_merges():
    d = _registry().resolve("@milo.g")
    assert d.creator_id is None


def test_empty_input_is_no_match():
    d = _registry().resolve("")
    assert d.creator_id is None
    assert d.score == 0.0
