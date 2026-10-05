"""Deliverable reconciliation: missing + late detection."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reconciliation.deliverables import reconcile_deliverables, type_matches  # noqa: E402
from schemas.contract import Contract  # noqa: E402
from schemas.deliverable import Deliverable  # noqa: E402


def _contract(items, deadline="2026-03-15"):
    return Contract(contract_id="CT-1", campaign_id="CMP", creator_id="ST-001",
                    source_file="contract.pdf", agreed_fee=800, deadline=deadline,
                    deliverables_json=items)


def _dv(did, ctype, published=None):
    return Deliverable(deliverable_id=did, campaign_id="CMP", creator_id="ST-001",
                       content_id=did, platform="Instagram", content_type=ctype,
                       required=True, published_at=published, approval_status="approved")


def test_all_published_passes():
    ct = _contract([{"type": "Reel", "count": 2}])
    rows, excs = reconcile_deliverables([ct], [_dv("IG-1", "Reel", "2026-03-10"),
                                               _dv("IG-2", "Reel", "2026-03-11")])
    assert rows[0]["missing_count"] == 0
    assert not [e for e in excs if e.exception_type == "MISSING_DELIVERABLE"]


def test_missing_deliverable_detected():
    ct = _contract([{"type": "Reel", "count": 2}, {"type": "Stories", "count": 3}])
    rows, excs = reconcile_deliverables([ct], [_dv("IG-1", "Reel", "2026-03-10")])
    md = [e for e in excs if e.exception_type == "MISSING_DELIVERABLE"]
    assert len(md) == 1
    assert md[0].severity == "HIGH"
    assert rows[0]["missing_count"] == 4  # 1 reel + 3 stories


def test_late_deliverable_detected():
    ct = _contract([{"type": "Reel", "count": 1}], deadline="2026-03-15")
    rows, excs = reconcile_deliverables([ct], [_dv("IG-9", "Reel", "2026-03-20")])
    ld = [e for e in excs if e.exception_type == "LATE_DELIVERABLE"]
    assert len(ld) == 1
    assert ld[0].severity == "MEDIUM"


def test_type_synonyms_match():
    assert type_matches("1 Instagram Reel", "Reel")
    assert type_matches("3 Instagram Stories", "Story")
    assert not type_matches("Reel", "TikTok video")
