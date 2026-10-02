"""Deterministic creator identity resolution.

Hierarchy (per spec):
  1. exact creator ID
  2. exact social handle
  3. exact email
  4. normalized exact name
  5. fuzzy name match (RapidFuzz token_set_ratio + ratio blend)
  6. AI-assisted match (optional; only *suggests*, never auto-merges)

Low-confidence results are flagged for HUMAN REVIEW, never merged silently.
"""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

from config.settings import settings
from matching.confidence import MatchDecision, decide

_NOISE = {"official", "the", "real", "its", "tv", "media", "team", "hq",
          "live", "of", "and", "for", "de", "la", "el", "le"}


def strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(ch))


def normalize_name(raw: str) -> str:
    """Canonical key: lowercase, ascii, noise tokens removed."""
    if raw is None:
        return ""
    s = strip_accents(str(raw)).lower().strip()
    if "," in s:  # "Last, First"
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) == 2:
            s = f"{parts[1]} {parts[0]}"
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    toks = [t for t in s.split() if t not in _NOISE]
    return " ".join(toks)


def normalize_handle(raw: str) -> str:
    """'@sara.ahmed ' -> 'sara ahmed'; '' for non-handles."""
    s = strip_accents(str(raw or "")).lower().strip()
    if not s.startswith("@"):
        return ""
    s = s.lstrip("@")
    s = re.sub(r"[._\-]+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s).strip()
    toks = [t for t in s.split() if t not in _NOISE]
    return " ".join(toks)


def fuzzy_score(a: str, b: str) -> float:
    """Blend of token-set and full-string ratios, 0..1."""
    if not a or not b:
        return 0.0
    ts = fuzz.token_set_ratio(a, b) / 100.0
    tr = fuzz.token_sort_ratio(a, b) / 100.0
    wr = fuzz.WRatio(a, b) / 100.0
    return round(0.45 * ts + 0.35 * tr + 0.20 * wr, 4)


class CreatorRegistry:
    def __init__(self) -> None:
        self.by_key: dict[str, str] = {}        # normalized name -> id
        self.by_handle: dict[str, str] = {}     # normalized handle -> id
        self.by_email: dict[str, str] = {}
        self.display: dict[str, str] = {}
        self.handles: dict[str, str] = {}       # id -> raw instagram handle
        self.order: list[str] = []

    # -- registration ----------------------------------------------------
    def add(self, creator_id: str, name: str, instagram_handle: str | None = None,
            tiktok_handle: str | None = None, email: str | None = None,
            aliases: list[str] | None = None) -> None:
        if creator_id not in self.display:
            self.order.append(creator_id)
        self.display[creator_id] = name
        self.by_key.setdefault(normalize_name(name), creator_id)
        for alias in aliases or []:
            k = normalize_name(alias)
            if k:
                self.by_key.setdefault(k, creator_id)
        for h in (instagram_handle, tiktok_handle):
            hk = normalize_handle(h)
            if hk:
                self.by_handle.setdefault(hk, creator_id)
        if instagram_handle:
            self.handles[creator_id] = instagram_handle
        if email:
            self.by_email[email.lower().strip()] = creator_id

    def known_ids(self) -> list[str]:
        return list(self.order)

    # -- resolution --------------------------------------------------------
    def resolve(self, raw: str) -> MatchDecision:
        """Resolve any string (name, handle, 'Name (@handle)', id) to a creator."""
        s = str(raw or "").strip()
        if not s:
            return decide(None, 0.0, "none", "empty value")

        # 1. exact creator id (e.g. "ST-004")
        if s.upper() in self.display:
            cid = s.upper()
            return decide(cid, 1.0, "id", f"exact creator id {cid}")

        # embedded handle, e.g. "Sara Ahmed (@sara.ahmed)"
        m = re.search(r"@[\w.\-]+", s)
        handle_part = m.group(0) if m else None
        name_part = re.sub(r"@[\w.\-]+", "", s).strip(" ,();") or None

        # 2. exact handle
        if handle_part:
            hk = normalize_handle(handle_part)
            if hk and hk in self.by_handle:
                cid = self.by_handle[hk]
                return decide(cid, 1.0, "handle",
                              f"exact handle {handle_part} -> {self.display[cid]}")

        # 3. exact email
        low = s.lower()
        if "@" in s and "." in s and " " not in s and low in self.by_email:
            cid = self.by_email[low]
            return decide(cid, 1.0, "email", f"exact email -> {self.display[cid]}")

        # 4. normalized exact name (of whole string and of name part)
        for cand in filter(None, [name_part, s]):
            key = normalize_name(cand)
            if key and key in self.by_key:
                cid = self.by_key[key]
                return decide(cid, 1.0, "exact_name",
                              f"normalized name '{cand}' matches {self.display[cid]}")

        # 5. fuzzy over names (handle bonus when an unknown handle is close
        #    to a known creator's own handle - e.g. "@saraahmed" vs @sara.ahmed)
        best_cid, best_score, best_reason = None, 0.0, ""
        query_keys = [normalize_name(x) for x in filter(None, [name_part, s])
                      if normalize_name(x)]
        hk = normalize_handle(handle_part) if handle_part else ""
        handle_bonus = bool(hk) and hk not in self.by_handle
        for cid in self.order:
            cand_keys = {k for k, v in self.by_key.items() if v == cid} | \
                        {normalize_name(self.display[cid])}
            for ck in {c for c in cand_keys if c}:
                for qk in query_keys:
                    sc = fuzzy_score(qk, ck)
                    reason = f"name similarity {sc:.0%} vs '{self.display[cid]}'"
                    if handle_bonus:
                        hhk = normalize_handle(self.handles.get(cid, ""))
                        if hhk:
                            hs = fuzzy_score(hk, hhk)
                            if hs >= 0.85:
                                sc = min(1.0, round(sc + 0.10, 4))
                                reason += " + handle similarity"
                    if sc > best_score:
                        best_cid, best_score, best_reason = cid, sc, reason
        if best_cid is None:
            return decide(None, 0.0, "none", "no candidate above threshold")
        if best_score >= settings.auto_accept:
            return decide(best_cid, best_score, "fuzzy", best_reason)
        if best_score >= settings.review_min:
            return decide(best_cid, best_score, "fuzzy", best_reason + " (below auto-accept)")
        return decide(None, best_score, "none",
                      f"best candidate {self.display.get(best_cid)} at {best_score:.0%} - too low")
