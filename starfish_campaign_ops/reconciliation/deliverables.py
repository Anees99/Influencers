"""Deliverable reconciliation: contract expectations vs tracker actuals."""
from __future__ import annotations

import re
from datetime import date

from reconciliation.exceptions import make
from schemas.contract import Contract
from schemas.deliverable import Deliverable


def _d(s: str | None) -> date | None:
    if not s:
        return None
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(s))
    return date.fromisoformat(m.group(0)) if m else None


_TYPE_SYNONYMS = [
    ({"reel", "reels", "ig reel", "instagram reel"}, {"reel"}),
    ({"story", "stories", "ig story", "instagram stories"}, {"story", "stories"}),
    ({"post", "feed post", "grid post"}, {"post"}),
    ({"tiktok video", "tiktok", "tt video"}, {"tiktok"}),
    ({"youtube video", "yt video"}, {"youtube"}),
    ({"live", "takeover"}, {"live", "takeover"}),
]


def type_matches(contract_type: str, deliverable_type: str) -> bool:
    ct = str(contract_type).lower()
    dt = str(deliverable_type).lower()
    for group_c, group_d in _TYPE_SYNONYMS:
        if any(g in ct for g in group_c) and any(g in dt for g in group_d):
            return True
    return False


def reconcile_deliverables(contracts: list[Contract],
                           deliverables: list[Deliverable]) -> tuple[list[dict], list]:
    exceptions: list = []
    rows: list[dict] = []
    by_creator: dict[str | None, list[Deliverable]] = {}
    for dv in deliverables:
        by_creator.setdefault(dv.creator_id, []).append(dv)

    for ct in contracts:
        cid = ct.creator_id
        dvs = by_creator.get(cid, [])
        deadline = _d(ct.deadline)
        required_total = 0
        published_total = 0
        missing_items: list[str] = []
        late_items: list[str] = []
        used: set[str] = set()

        for item in ct.deliverables_json:
            ctype, count = item.get("type", ""), int(item.get("count", 1))
            required_total += count
            matching = [dv for dv in dvs
                        if dv.required and type_matches(ctype, dv.content_type)
                        and dv.deliverable_id not in used]
            published = [dv for dv in matching if dv.published_at]
            for dv in published[:count]:
                used.add(dv.deliverable_id)
                published_total += 1
                pd_ = _d(dv.published_at)
                if deadline and pd_ and pd_ > deadline:
                    late_items.append(f"{ctype} ({dv.deliverable_id}, {dv.published_at})")
            shortfall = count - min(count, len(published))
            for _ in range(shortfall):
                missing_items.append(ctype)

        pending_appr = sorted({dv.approval_status for dv in dvs
                               if dv.approval_status not in ("approved",)})
        row = {"creator_id": cid, "source_file": ct.source_file,
               "deadline": ct.deadline, "required": required_total,
               "published": published_total,
               "missing_count": len(missing_items), "late_count": len(late_items),
               "approval_statuses": pending_appr or ["approved"],
               "deliverable_ids": [dv.deliverable_id for dv in dvs]}
        rows.append(row)

        if missing_items:
            exceptions.append(make(
                "MISSING_DELIVERABLE",
                f"{len(missing_items)} contracted item(s) not published: "
                + ", ".join(sorted(set(missing_items))) + ".",
                creator_id=cid, expected=required_total, actual=published_total,
                evidence={"missing": missing_items, "contract_deadline": ct.deadline,
                          "tracker_rows": row["deliverable_ids"]},
                source_files=[ct.source_file] + sorted({dv.source_file for dv in dvs})))
        if late_items:
            exceptions.append(make(
                "LATE_DELIVERABLE",
                f"{len(late_items)} item(s) published after the {ct.deadline} deadline: "
                + "; ".join(late_items) + ".",
                creator_id=cid, expected=ct.deadline,
                actual=", ".join(i.split("(")[1].rstrip(")") for i in late_items),
                evidence={"late_items": late_items, "deadline": ct.deadline},
                source_files=[ct.source_file] + sorted({dv.source_file for dv in dvs})))
    return rows, exceptions
