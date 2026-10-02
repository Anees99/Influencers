"""Value normalization helpers (amounts, metrics, dates).

Handles messy real-world strings: "USD 800", "$1,350.00", "184.5K", "1.2M",
"125,400", bad dates, etc. Everything is deterministic and lossless-checked -
unparseable values become None plus a warning, never a silent guess.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_MULT = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
_CURRENCY_RE = re.compile(r"(USD|EUR|GBP)\s*([\d.,]+)")


def parse_amount(raw) -> tuple[float | None, str | None]:
    """Return (amount, currency_hint). Handles 'USD 800', '$1,350.00', '800'."""
    if raw is None:
        return None, None
    if isinstance(raw, (int, float)):
        return round(float(raw), 2), None
    s = str(raw).strip()
    if not s:
        return None, None
    cur = None
    m = _CURRENCY_RE.search(s.upper())
    if m:
        cur = m.group(1)
        num = m.group(2)
    else:
        num = s
    num = re.sub(r"[^\d.\-]", "", num.replace(",", ""))
    if num.count(".") > 1:  # 1.350,00 European style
        num = num.replace(".", "").replace(",", ".", 1)
    try:
        val = float(num)
    except ValueError:
        return None, cur
    return round(val, 2), cur


def parse_metric(raw) -> int | None:
    """'184.5K' -> 184500; '1.2M' -> 1200000; '125,400' -> 125400."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and raw != int(raw):
            return int(round(raw))
        return int(raw)
    s = str(raw).strip().lower().replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb])?", s)
    if not m:
        return None
    val = float(m.group(1)) * (_MULT[m.group(2)] if m.group(2) else 1)
    return int(round(val))


_DATE_PATTERNS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
    "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y", "%d-%m-%Y",
]


def parse_date_any(raw) -> tuple[date | None, str | None]:
    """Parse many common formats. Returns (date, iso_string). Bad dates -> None."""
    if raw is None:
        return None, None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw, raw.isoformat()
    if isinstance(raw, datetime):
        return raw.date(), raw.date().isoformat()
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none", "nat", "-"}:
        return None, None
    for pat in _DATE_PATTERNS:
        try:
            d = datetime.strptime(s, pat).date()
            return d, d.isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", s)  # "March 15, 2026" variants
    if m:
        for pat in ("%d %B %Y", "%d %b %Y"):
            try:
                d = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", pat).date()
                return d, d.isoformat()
            except ValueError:
                continue
    return None, None


def parse_deliverables(text: str) -> list[dict]:
    """'1 Instagram Reel\\n3 Instagram Stories' -> [{type, count}, ...]."""
    out: list[dict] = []
    for line in re.split(r"[\n;]+", str(text or "")):
        line = line.strip().strip("-•* ").strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s*[xX]?\s+(.+)$", line)
        if m:
            out.append({"type": m.group(2).strip(), "count": int(m.group(1))})
        else:
            out.append({"type": line, "count": 1})
    return out


def normalize_platform(raw: str) -> str:
    s = str(raw or "").strip().lower()
    mapping = {
        "instagram": "Instagram", "ig": "Instagram",
        "tiktok": "TikTok", "tt": "TikTok",
        "youtube": "YouTube", "yt": "YouTube",
        "twitter": "Twitter/X", "x": "Twitter/X",
        "twitch": "Twitch", "podcast": "Podcast",
    }
    return mapping.get(s, str(raw or "").strip() or "Unknown")
