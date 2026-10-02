"""Generate the deterministic September demo dataset for the Starfish campaign.

Run:  python scripts/generate_demo_data.py   (no randomness - exact values)

Dataset shape (drives the demo story):
  * Roster file lists 13 creators; exactly 12 are referenced by operational
    files -> "12 Creators Identified". Nora Petrova is roster-only (not
    active this period). Nina Petrova is NOT in the roster - she appears only
    in invoices/payouts and is auto-discovered as a new creator.
  * Milo Grant is an auto-discovered contracted creator (contract + invoice +
    payout + post all reconcile cleanly) - shows discovery without noise.

Planted exceptions - exactly 12:
  EX high   x3  missing_payout          INV-9003 Priya, INV-9007 Sofia, INV-9010 Jonas
  EX medium x2  contract_invoice_mismatch  Lena (+150), Elif (+200)
  EX medium x1  invoice_no_contract        Nina Petrova INV-9012
  EX medium x1  payout_no_invoice          PAY-7710 $600 to @milo.g (handle not in alias table)
  EX medium x2  deliverable_shortfall      Tom Okafor (2 agreed/1 live), Rosa Delgado (1/0)
  EX medium x1  identity_review            "Tanaka Kai Live" -> Kai Tanaka, score 0.833
  EX low    x2  duplicate_snapshot         PST-2004, PST-2015 reported twice
"""
from __future__ import annotations

import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")

CREATORS = [
    ("CR-001", "Maya Chen",     "@mayabakes; Maya C."),
    ("CR-002", "Diego Ramirez", "@diegoeats"),
    ("CR-003", "Priya Nair",    "@priyahacks"),
    ("CR-004", "Tom Okafor",    "Tomi Okafor"),
    ("CR-005", "Lena Fischer",  "@lenafischer"),
    ("CR-006", "Marcus Webb",   "@webbworkouts"),
    ("CR-007", "Sofia Marino",  "@sofiastyle"),
    ("CR-008", "Kai Tanaka",    "@kaiplays"),
    ("CR-009", "Amara Diallo",  "@amaradreams"),
    ("CR-010", "Jonas Berg",    "@jonasberg"),
    ("CR-011", "Elif Kaya",     "@elifkaya"),
    ("CR-012", "Rosa Delgado",  "@rosadelgado"),
    ("CR-013", "Nora Petrova",  "@norapetrova"),   # roster-only: inactive this period
]

# contracts: (contract_id, creator, deliverable, amount)
CONTRACTS = [
    ("CT-101", "Maya Chen",      "2x Instagram Reel",        2400.00),
    ("CT-102", "Diego Ramirez",  "1x YouTube Integration",   3500.00),
    ("CT-103", "Priya Nair",     "2x TikTok Video",          1800.00),
    ("CT-104", "Tom Okafor",     "1x Instagram Reel",        1200.00),
    ("CT-105", "Lena Fischer",   "3x Instagram Story Set",    900.00),
    ("CT-106", "Marcus Webb",    "1x YouTube Short + Reel",  2000.00),
    ("CT-107", "Sofia Marino",   "2x TikTok Video",          1500.00),
    ("CT-108", "Kai Tanaka",     "1x Twitch Segment",        2200.00),
    ("CT-109", "Amara Diallo",   "2x Instagram Reel",        2600.00),
    ("CT-110", "Jonas Berg",      "1x Podcast Read",          800.00),
    ("CT-111", "Elif Kaya",      "2x YouTube Short",         1700.00),
    ("CT-112", "Rosa Delgado",   "1x Instagram Reel",        1300.00),
    ("CT-113", "Tom Okafor",     "1x Instagram Story Set",    500.00),
    ("CT-114", "Milo Grant",     "1x Instagram Reel",         600.00),
]

# invoices: (invoice_number, creator, amount, period, status)
INVOICES = [
    ("INV-9001", "Maya Chen",     2400.00, "2026-09", "approved"),
    ("INV-9002", "@diegoeats",    3500.00, "2026-09", "approved"),
    ("INV-9003", "Priya Nair",    1800.00, "2026-09", "approved"),  # never paid  -> EX high
    ("INV-9004", "Tomi Okafor",   1200.00, "2026-09", "approved"),
    ("INV-9005", "Lena Fischer",  1050.00, "2026-09", "approved"),  # vs 900      -> EX mismatch
    ("INV-9006", "Marcus Webb",   2000.00, "2026-09", "approved"),
    ("INV-9007", "Sofia Marino",  1500.00, "2026-09", "approved"),  # never paid  -> EX high
    ("INV-9008", "Kai Tanaka",    2200.00, "2026-09", "approved"),
    ("INV-9009", "Amara Diallo",  2600.00, "2026-09", "approved"),
    ("INV-9010", "Jonas Berg",     800.00, "2026-09", "approved"),  # never paid  -> EX high
    ("INV-9011", "Elif Kaya",     1900.00, "2026-09", "approved"),  # vs 1700     -> EX mismatch
    ("INV-9012", "Nina Petrova",  950.00,  "2026-09", "approved"),  # no contract -> EX
    ("INV-9013", "Tomi Okafor",   500.00,  "2026-09", "approved"),
    ("INV-9014", "Rosa Delgado",  1300.00, "2026-09", "approved"),
    ("INV-9015", "Milo Grant",    600.00,  "2026-09", "approved"),
]

# payouts: (payment_ref, creator, amount, date)
PAYOUTS = [
    ("PAY-7701", "Maya Chen",     2400.00, "2026-09-28"),
    ("PAY-7702", "Diego Ramirez", 3500.00, "2026-09-28"),
    ("PAY-7703", "Tom Okafor",    1200.00, "2026-09-29"),
    ("PAY-7704", "Lena Fischer",  1050.00, "2026-09-29"),
    ("PAY-7705", "Marcus Webb",   2000.00, "2026-09-30"),
    ("PAY-7706", "Kai Tanaka",    2200.00, "2026-09-30"),
    ("PAY-7707", "Amara Diallo",  2600.00, "2026-09-30"),
    ("PAY-7708", "Elif Kaya",     1900.00, "2026-10-01"),
    ("PAY-7709", "Nina Petrova",  950.00,  "2026-10-01"),
    ("PAY-7710", "@milo.g",       600.00,  "2026-09-27"),  # unmatched handle -> orphan EX
    ("PAY-7711", "Tom Okafor",    500.00,  "2026-10-02"),
    ("PAY-7712", "Rosa Delgado",  1300.00, "2026-10-02"),
    ("PAY-7713", "Milo Grant",    600.00,  "2026-10-02"),
]

# analytics rows: post_id, creator, platform, url, published_date,
#                 impressions, engagements, clicks, conversions, spend
ANALYTICS = [
    ("PST-2001", "Maya Chen",       "Instagram", "https://instagram.com/p/mc1",       "2026-09-05", 412000, 28700, 5100, 320, 240.00),
    ("PST-2002", "Maya Chen",       "Instagram", "https://instagram.com/p/mc2",       "2026-09-19", 388500, 25100, 4700, 280, 220.00),
    ("PST-2003", "@diegoeats",      "YouTube",   "https://youtube.com/watch?v=d1",    "2026-09-08", 905000, 54200, 12800, 810, 640.00),
    ("PST-2004", "Priya Nair",      "TikTok",    "https://tiktok.com/@priyahacks/v1", "2026-09-10", 1240000, 96400, 15100, 640, 410.00),
    ("PST-2005", "Priya Nair",      "TikTok",    "https://tiktok.com/@priyahacks/v2", "2026-09-24", 860000, 61300, 9800, 430, 380.00),
    ("PST-2006", "Tomi Okafor",     "Instagram", "https://instagram.com/p/to1",       "2026-09-12", 152000, 9800, 1900, 95, 110.00),
    ("PST-2007", "Lena Fischer",    "Instagram", "https://instagram.com/p/lf1",       "2026-09-03", 98000, 6100, 1400, 70, 60.00),
    ("PST-2008", "Lena Fischer",    "Instagram", "https://instagram.com/p/lf2",       "2026-09-11", 104000, 7200, 1600, 82, 65.00),
    ("PST-2009", "Lena Fischer",    "Instagram", "https://instagram.com/p/lf3",       "2026-09-21", 91000, 5400, 1250, 61, 55.00),
    ("PST-2010", "Marcus Webb",     "YouTube",   "https://youtube.com/shorts/w1",     "2026-09-15", 330000, 21500, 4100, 210, 190.00),
    ("PST-2011", "Marcus Webb",     "Instagram", "https://instagram.com/p/mw2",       "2026-09-26", 210000, 14900, 2800, 150, 160.00),
    ("PST-2012", "Sofia Marino",    "TikTok",    "https://tiktok.com/@sofiastyle/v1", "2026-09-07", 520000, 38800, 6900, 300, 240.00),
    ("PST-2013", "Sofia Marino",    "TikTok",    "https://tiktok.com/@sofiastyle/v2", "2026-09-18", 460000, 31200, 5600, 260, 230.00),
    ("PST-2014", "Kai Tanaka",      "Twitch",    "https://twitch.tv/kaiplays/clip1",  "2026-09-14", 76000, 4300, 980, 44, 90.00),
    ("PST-2015", "Amara Diallo",    "Instagram", "https://instagram.com/p/ad1",       "2026-09-06", 615000, 44900, 8100, 420, 300.00),
    ("PST-2016", "Amara Diallo",    "Instagram", "https://instagram.com/p/ad2",       "2026-09-20", 590000, 40100, 7400, 380, 280.00),
    ("PST-2017", "Jonas Berg",      "Podcast",   "https://open.spotify.com/ep/jb9",   "2026-09-02", 45000, 1200, 640, 28, 40.00),
    ("PST-2018", "Elif Kaya",       "YouTube",   "https://youtube.com/shorts/ek1",    "2026-09-09", 275000, 18300, 3400, 160, 150.00),
    ("PST-2019", "Elif Kaya",       "YouTube",   "https://youtube.com/shorts/ek2",    "2026-09-23", 240000, 15900, 2900, 140, 140.00),
    ("PST-2020", "Milo Grant",      "Instagram", "https://instagram.com/p/mg1",       "2026-09-17", 33000, 1500, 420, 12, 30.00),
    # review-band variant of Kai Tanaka: tokens {tanaka,kai,live} vs {kai,tanaka} -> 0.833
    ("PST-2021", "Tanaka Kai Live", "Twitch",    "https://twitch.tv/kaiplays/clip2",  "2026-09-29", 52000, 3100, 700, 33, 55.00),
    # Duplicate snapshots of posts already reported above (kept-latest rule):
    ("PST-2004", "Priya Nair",      "TikTok",    "https://tiktok.com/@priyahacks/v1", "2026-09-10", 1240000, 96400, 15100, 640, 410.00),
    ("PST-2015", "Amara Diallo",    "Instagram", "https://instagram.com/p/ad1",       "2026-09-06", 618000, 45200, 8150, 425, 300.00),
]


def write_csv(name: str, header: list[str], rows: list[list]):
    path = os.path.join(RAW, name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    print(f"wrote {path} ({len(rows)} rows)")


def main():
    os.makedirs(RAW, exist_ok=True)
    write_csv("creators.csv", ["creator_id", "name", "aliases"],
              [list(c) for c in CREATORS])
    write_csv("contracts.csv", ["contract_id", "creator", "deliverable", "amount", "status"],
              [[a, b, c, f"{d:.2f}", "active"] for a, b, c, d in CONTRACTS])
    write_csv("invoices.csv", ["invoice_number", "creator", "amount", "period", "status"],
              [[a, b, f"{c:.2f}", d, e] for a, b, c, d, e in INVOICES])
    write_csv("payouts.csv", ["payment_ref", "creator", "amount", "date"],
              [[a, b, f"{c:.2f}", d] for a, b, c, d in PAYOUTS])
    write_csv("analytics.csv",
              ["post_id", "creator", "platform", "url", "published_date",
               "impressions", "engagements", "clicks", "conversions", "spend"],
              [list(r) for r in ANALYTICS])


if __name__ == "__main__":
    main()
