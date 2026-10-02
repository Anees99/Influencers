"""Deterministic creator-name matching engine.

No LLM involved: normalization + token overlap + optional alias table,
scored with a transparent weighted formula and thresholds.
"""
from __future__ import annotations

import re
import unicodedata

# Suffixes / noise tokens that carry no identity information.
_NOISE_TOKENS = {
    "official", "the", "real", "its", "tv", "media", "team", "hq",
    "creations", "creative", "studio", "studios", "co", "llc", "ltd", "inc",
}

_STOPWORDS = {"of", "and", "for", "de", "la", "el", "le"}


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def normalize_name(raw: str) -> str:
    """Canonical key used for exact matching across files."""
    if raw is None:
        return ""
    s = strip_accents(str(raw)).lower().strip()
    # Handle "Last, First" style.
    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) == 2:
            s = parts[1] + " " + parts[0]
    # Keep alphanumerics plus single spaces.
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    toks = [t for t in s.split() if t not in _NOISE_TOKENS and t not in _STOPWORDS]
    return " ".join(toks)


def tokenize(name: str) -> set[str]:
    return {t for t in name.split() if t}


def handle_to_name(handle: str) -> str:
    """@miss_baker -> miss baker (underscores become spaces)."""
    s = strip_accents(str(handle or "")).lower()
    s = s.lstrip("@").strip()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    toks = [t for t in s.split() if t not in _NOISE_TOKENS and t not in _STOPWORDS]
    return " ".join(toks)


def match_score(a: str, b: str) -> float:
    """Weighted score in [0, 1] between two normalized names."""
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    jaccard = len(inter) / len(ta | tb)
    containment = len(inter) / min(len(ta), len(tb))
    # Exact full-key equality is handled by caller; blend the rest.
    return 0.5 * jaccard + 0.5 * containment


AUTO_ACCEPT = 0.85
REVIEW_MIN = 0.55


class CreatorMatcher:
    """Matches raw name/handle strings to canonical creators.

    Resolution order (fully deterministic):
      1. explicit alias table (exact normalized hit)
      2. exact normalized key match
      3. fuzzy score >= AUTO_ACCEPT  -> auto-linked
      4. REVIEW_MIN <= score < AUTO_ACCEPT -> flagged for review
      5. otherwise -> unmatched
    """

    def __init__(self) -> None:
        self.canonical: dict[str, str] = {}   # normalized key -> creator_id
        self.display: dict[str, str] = {}     # creator_id -> display name
        self._id_order: list[str] = []

    def register(self, creator_id: str, name: str, aliases: list[str] | None = None) -> None:
        key = normalize_name(name)
        if creator_id not in self.display:
            self._id_order.append(creator_id)
        self.canonical[key] = creator_id
        self.display[creator_id] = name
        for alias in aliases or []:
            self.canonical[normalize_name(alias)] = creator_id

    def known_ids(self) -> list[str]:
        return list(self._id_order)

    def resolve(self, raw: str) -> tuple[str | None, float, str]:
        """Return (creator_id | None, score, status)."""
        key = normalize_name(handle_to_name(raw))
        if not key:
            return None, 0.0, "empty"
        if key in self.canonical:
            return self.canonical[key], 1.0, "exact"
        best_id, best_score = None, 0.0
        for cand_key, cand_id in self.canonical.items():
            s = match_score(key, cand_key)
            if s > best_score or (s == best_score and cand_id < (best_id or "")):
                best_id, best_score = cand_id, s
        if best_score >= AUTO_ACCEPT:
            return best_id, round(best_score, 3), "fuzzy"
        if best_score >= REVIEW_MIN:
            return best_id, round(best_score, 3), "review"
        return None, round(best_score, 3), "unmatched"
