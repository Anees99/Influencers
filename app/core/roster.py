"""Build the canonical creator roster from all source files.

Identifies creators across contracts / invoices / payouts / analytics using
the deterministic matcher, deduplicates name variants, and records match
quality. Fully rule-based - no LLM involved.
"""
from __future__ import annotations

import pandas as pd

from app.core.matching import CreatorMatcher, normalize_name


def build_roster(
    creators_df: pd.DataFrame | None,
    sources: dict[str, pd.DataFrame],
) -> tuple[CreatorMatcher, pd.DataFrame, pd.DataFrame]:
    """Return (matcher, roster_table, match_log).

    ``sources`` maps logical file name -> DataFrame containing a ``creator``
    column. ``match_log`` records every raw string seen and how it resolved,
    which doubles as the evidence trail for creator matching.
    """
    matcher = CreatorMatcher()
    seen_ids: set[str] = set()

    # 1. Explicit roster file first (authoritative ids/names/aliases).
    if creators_df is not None:
        for _, row in creators_df.iterrows():
            cid = str(row.get("creator_id", "")).strip()
            name = str(row.get("name", "")).strip()
            if not cid or not name or cid in seen_ids:
                continue
            aliases = [
                a.strip()
                for a in str(row.get("aliases", "") or "").split(";")
                if a.strip() and a.strip().lower() != "nan"
            ]
            matcher.register(cid, name, aliases)
            seen_ids.add(cid)

    # 2. Discover every creator string used in the operational files.
    occurrences: dict[str, str] = {}  # raw string -> first source seen in
    counter = len(seen_ids)
    for src_name in sorted(sources):
        df = sources[src_name]
        if df is None or "creator" not in df.columns:
            continue
        for raw in df["creator"].dropna().astype(str):
            raw_s = raw.strip()
            if raw_s and raw_s not in occurrences:
                occurrences[raw_s] = src_name

    # 3. Resolve each discovered string; auto-register true newcomers.
    match_log: list[dict] = []
    per_creator: dict[str, list[tuple[str, float, str]]] = {}
    for raw_s in sorted(occurrences):
        cid, score, status = matcher.resolve(raw_s)
        if cid is None and status != "empty":
            key = normalize_name(raw_s)
            if key:
                counter += 1
                cid = f"C{counter:03d}"
                matcher.register(cid, raw_s.lstrip("@"))
                status, score = "new", 1.0
        if cid:
            per_creator.setdefault(cid, []).append((raw_s, score, status))
        match_log.append({
            "raw_value": raw_s,
            "creator_id": cid or "(unmatched)",
            "score": score,
            "match_status": status,
            "first_seen_in": occurrences[raw_s],
        })

    # 4. One roster row per canonical creator.
    rows = []
    for cid in matcher.known_ids():
        hits = per_creator.get(cid, [])
        variants = sorted({v for v, _, _ in hits})
        appears_in = sorted({
            src for src, df in sources.items()
            if df is not None and "creator" in df.columns
            and any(matcher.resolve(str(r))[0] == cid
                    for r in df["creator"].dropna().unique())
        })
        worst = min([s for _, s, _ in hits], default=1.0)
        statuses = {st for _, _, st in hits}
        rows.append({
            "creator_id": cid,
            "name": matcher.display[cid],
            "name_variants": "; ".join(variants) or "(roster only)",
            "appears_in": ", ".join(appears_in) or "roster only",
            "files_count": len(appears_in),
            "min_match_score": round(worst, 3),
            "needs_review": "review" in statuses,
        })
    roster = (pd.DataFrame(rows)
              .sort_values("creator_id")
              .reset_index(drop=True))
    log_df = pd.DataFrame(match_log)
    return matcher, roster, log_df
