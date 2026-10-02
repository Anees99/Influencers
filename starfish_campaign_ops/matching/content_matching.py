"""Content (deliverable <-> analytics) matching.

Hierarchy:
  1. exact content_id
  2. platform + creator + content id
  3. creator + content type + publish-date proximity
  4. fuzzy title/URL match (token overlap on slug)

Every match stores confidence + method for auditability.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz


@dataclass(frozen=True)
class ContentMatch:
    deliverable_id: str | None
    score: float
    method: str
    reason: str


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(s))
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _slug(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split())


def match_content(
    content_id: str | None,
    platform: str,
    creator_id: str | None,
    content_type: str,
    publish_date: str | None,
    candidates: list[dict],
) -> ContentMatch:
    """candidates: deliverable dicts with keys deliverable_id, content_id,
    platform, creator_id, content_type, published_at."""
    # 1 & 2: exact content id (optionally scoped by platform+creator)
    for c in candidates:
        if content_id and str(c.get("content_id") or "") == str(content_id):
            same_scope = ((not c.get("platform") or c["platform"] == platform)
                          and (c.get("creator_id") is None or c.get("creator_id") == creator_id))
            if same_scope:
                return ContentMatch(c["deliverable_id"], 1.0, "content_id",
                                    f"exact content id {content_id}")
            return ContentMatch(c["deliverable_id"], 0.9, "content_id_weak",
                                f"content id {content_id} but platform/creator differ")

    pd_ = _parse_date(publish_date)
    # 3: creator + type + date proximity
    best: ContentMatch | None = None
    for c in candidates:
        if c.get("creator_id") != creator_id or c.get("content_id"):
            continue  # only unclaimed rows need proximity
        ctype_ok = _slug(c.get("content_type", "")) and (
            _slug(content_type) in _slug(c["content_type"])
            or _slug(c["content_type"]) in _slug(content_type)
            or fuzz.token_set_ratio(_slug(content_type), _slug(c["content_type"])) >= 85)
        if not ctype_ok:
            continue
        cd = _parse_date(c.get("published_at"))
        if pd_ and cd:
            delta = abs((pd_ - cd).days)
            if delta <= 3:
                sc = round(0.95 - delta * 0.03, 3)
                cand = ContentMatch(c["deliverable_id"], sc, "type_date",
                                    f"same creator+type, published {delta} day(s) apart")
                if best is None or cand.score > best.score:
                    best = cand
    if best:
        return best

    # 4: fuzzy on any remaining creator row
    for c in candidates:
        if c.get("creator_id") == creator_id and not c.get("content_id"):
            return ContentMatch(c["deliverable_id"], 0.6, "fuzzy_creator",
                                "only shared creator; no id/type/date evidence")
    return ContentMatch(None, 0.0, "none", "no candidate deliverable row")
