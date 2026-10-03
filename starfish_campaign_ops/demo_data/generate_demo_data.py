"""Generate the complete synthetic demo dataset for the Starfish POC.

Run from the project root:  python demo_data/generate_demo_data.py

Creates realistic PDF contracts/invoices, XLSX payouts/deliverables/brief,
CSV analytics exports (with messy K/M-formatted numbers and duplicate
snapshots), a PNG "Instagram Insights" screenshot + sidecar, and a corrupt
PDF to prove error handling. Every number here is *input data*; all report
figures are computed by the reconciliation engine, never typed in.

The dataset intentionally contains all 12 exception classes required by the
demo script (see EXCEPTION MAP below).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import fitz  # PyMuPDF
from openpyxl import Workbook
from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent
(BASE / "contracts").mkdir(exist_ok=True)
(BASE / "invoices").mkdir(exist_ok=True)
(BASE / "screenshots").mkdir(exist_ok=True)

# ---------------------------------------------------------------- roster ---
# creator_id, canonical name, instagram handle, contract fee, invoice amount,
# payout amount/status, notes -> engineered exceptions
CREATORS = [
    # id      name              handle            fee   inv   payout status
    ("ST-001", "Sara Ahmed",     "@sara.ahmed",    800,  800,  800,  "Paid"),
    ("ST-002", "Omar Ali",       "@omar.ali",      1200, 1350, 1200, "Paid"),      # PAYMENT_VARIANCE +150 & PAYOUT ok
    ("ST-003", "Lina Hassan",    "@lina.hassan",   600,  600,  0,    "Pending"),    # PAYMENT_PENDING
    ("ST-004", "Youssef Karim",  "@youssefk",      950,  850,  850,  "Paid"),      # INVOICE_UNDERBILLED -100
    ("ST-005", "Nour El-Sayed",  "@nour.elsayed",  1100, 1100, 1000, "Paid"),      # PAYOUT_VARIANCE -100
    ("ST-006", "Maya Farouk",    "@maya.farouk",   700,  700,  1400, "Paid"),      # DUPLICATE_INVOICE (double-billed)
    ("ST-007", "Hana Mostafa",   "@hana.mostafa",  900,  900,  900,  "Paid"),      # NAME_MISMATCH via "Hana M." in payouts
    ("ST-008", "Rana Khalil",    "@rana.khalil",   1500, 1500, 1500, "Paid"),
    ("ST-009", "Dina Fathy",     "@dina.fathy",    850,  850,  850,  "Paid"),
    ("ST-010", "Salma Adel",     "@salma.adel",    1250, 1250, 1250, "Paid"),
    ("ST-011", "Aya Rahman",     "@aya.rahman",    1000, 1000, 1000, "Paid"),
    ("ST-012", "Karim Nasser",   "@karim.nasser",  1300, 1300, 1300, "Paid"),      # LATE_DELIVERABLE
]

# creators whose contract requires a TikTok Video deliverable
TIKTOK_REQUIRED = {"ST-002"}

CAMPAIGN = "ABC Beauty Ramadan Skincare Campaign"
CLIENT = "ABC Beauty"
DEADLINE = "March 15, 2026"

# deliverable plan per creator: list of (content_id, platform, type, publish or None, approval)
PLAN = {
    "ST-001": [("IG-1001", "Instagram", "Reel", "2026-03-10", "approved"),
               ("IG-1002", "Instagram", "Story", "2026-03-11", "approved"),
               ("IG-1003", "Instagram", "Story", "2026-03-12", "approved")],
    "ST-002": [("IG-1010", "Instagram", "Reel", "2026-03-09", "approved"),
               ("IG-1011", "Instagram", "Story", "2026-03-10", "approved"),
               ("TT-2010", "TikTok", "Video", "2026-03-12", "approved")],
    "ST-003": [("IG-1020", "Instagram", "Reel", "2026-03-08", "approved"),
               ("IG-1021", "Instagram", "Story", "2026-03-09", "pending")],
    "ST-004": [("IG-1030", "Instagram", "Reel", "2026-03-07", "approved"),
               ("IG-1031", "Instagram", "Story", "2026-03-08", "approved")],  # 2nd Story unpublished -> MISSING_DELIVERABLE
    "ST-005": [("IG-1040", "Instagram", "Reel", "2026-03-11", "approved"),
               ("IG-1041", "Instagram", "Story", "2026-03-12", "approved")],
    "ST-006": [("IG-1050", "Instagram", "Reel", "2026-03-06", "approved"),
               ("IG-1051", "Instagram", "Story", "2026-03-07", "approved"),
               ("IG-1052", "Instagram", "Story", "2026-03-08", "approved")],
    "ST-007": [("IG-1060", "Instagram", "Reel", "2026-03-09", "approved"),
               ("IG-1061", "Instagram", "Story", "2026-03-10", "approved")],
    "ST-008": [("IG-1070", "Instagram", "Reel", "2026-03-05", "approved"),
               ("IG-1071", "Instagram", "Story", "2026-03-06", "approved"),
               ("IG-1072", "Instagram", "Story", "2026-03-07", "approved"),
               ("IG-1073", "Instagram", "Post", "2026-03-13", "approved")],
    "ST-009": [("IG-1080", "Instagram", "Reel", "2026-03-12", "approved"),
               ("IG-1081", "Instagram", "Story", "2026-03-13", "approved"),
               ("IG-1082", "Instagram", "Story", "2026-03-14", "approved")],
    "ST-010": [("IG-1090", "Instagram", "Reel", "2026-03-08", "approved"),
               ("IG-1091", "Instagram", "Story", "2026-03-09", "approved"),
               ("IG-1092", "Instagram", "Story", "2026-03-10", "approved")],
    "ST-011": [("IG-1100", "Instagram", "Reel", "2026-03-11", "approved"),
               ("IG-1101", "Instagram", "Story", "2026-03-12", "approved"),
               ("IG-1102", "Instagram", "Story", "2026-03-13", "approved")],
    "ST-012": [("IG-1110", "Instagram", "Reel", "2026-03-18", "approved"),   # LATE (> Mar 15)
               ("IG-1111", "Instagram", "Story", "2026-03-19", "approved"),  # LATE
               ("IG-1112", "Instagram", "Story", "2026-03-14", "approved")],
}

CONTRACT_DELIVERABLES_TEXT = {
    "ST-001": "1 Instagram Reel\n2 Instagram Stories",
    "ST-002": "1 Instagram Reel\n1 Instagram Story\n1 TikTok Video",
    "ST-003": "1 Instagram Reel\n1 Instagram Story",
    "ST-004": "1 Instagram Reel\n2 Instagram Stories",
    "ST-005": "1 Instagram Reel\n1 Instagram Story",
    "ST-006": "1 Instagram Reel\n2 Instagram Stories",
    "ST-007": "1 Instagram Reel\n1 Instagram Story",
    "ST-008": "1 Instagram Reel\n2 Instagram Stories\n1 Instagram Post",
    "ST-009": "1 Instagram Reel\n2 Instagram Stories",
    "ST-010": "1 Instagram Reel\n2 Instagram Stories",
    "ST-011": "1 Instagram Reel\n2 Instagram Stories",
    "ST-012": "1 Instagram Reel\n2 Instagram Stories",
}

INVOICE_NUMBERS = {cid: f"INV-{1040 + i}" for i, cid in enumerate(c[0] for c in CREATORS)}


def _pdf(text: str, path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.split("\n"):
        page.insert_text((72, y), line, fontsize=11)
        y += 17
    doc.save(path)
    doc.close()


def make_contracts() -> None:
    for cid, name, handle, fee, *_ in CREATORS:
        slug = name.lower().replace(" ", "_").replace("-", "")
        text = (
            "CREATOR AGREEMENT\n\n"
            f"Creator:\n{name}\n\n"
            f"Instagram:\n{handle}\n\n"
            f"Campaign:\n{CAMPAIGN}\n\n"
            "Deliverables:\n" + CONTRACT_DELIVERABLES_TEXT[cid] + "\n\n"
            f"Fee:\nUSD {fee}\n\n"
            f"Deadline:\n{DEADLINE}\n\n"
            "Payment Terms:\nNet 14 days after final deliverable\n"
        )
        _pdf(text, BASE / "contracts" / f"{slug}_contract.pdf")


def make_invoices() -> None:
    for cid, name, handle, fee, inv_amt, *_ in CREATORS:
        num = INVOICE_NUMBERS[cid]
        slug = name.lower().replace(" ", "_").replace("-", "")
        text = (
            "INVOICE\n\n"
            f"{num}\n\n"
            f"Creator:\n{name}\n\n"
            f"Instagram:\n{handle}\n\n"
            f"Campaign:\n{CAMPAIGN}\n\n"
            f"Amount Due:\nUSD {inv_amt}\n\n"
            "Invoice Date:\nMarch 20, 2026\n\n"
            "Due Date:\nApril 3, 2026\n\n"
            "Tax:\nUSD 0\n"
        )
        _pdf(text, BASE / "invoices" / f"{num}_{slug}.pdf")
    # DUPLICATE_INVOICE: same invoice number re-billed in a second file
    dup = (
        "INVOICE\n\n"
        f"{INVOICE_NUMBERS['ST-006']}\n\n"
        "Creator:\nMaya Farouk\n\n"
        "Instagram:\n@maya.farouk\n\n"
        f"Campaign:\n{CAMPAIGN}\n\n"
        "Amount Due:\nUSD 700\n\n"
        "Invoice Date:\nMarch 21, 2026\n\n"
        "Due Date:\nApril 4, 2026\n"
    )
    _pdf(dup, BASE / "invoices" / f"{INVOICE_NUMBERS['ST-006']}_maya_duplicate.pdf")


def make_payouts() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "payouts"
    ws.append(["payout_id", "creator_name", "invoice_number", "amount",
               "currency", "payment_date", "status"])
    rows = []
    for i, (cid, name, handle, fee, inv_amt, pay_amt, status) in enumerate(CREATORS):
        if pay_amt == 0:
            continue
        short = name.split()[0][0] + ". " + name.split()[-1] if cid == "ST-007" else name
        rows.append([f"PAY-{9001 + i}", short, INVOICE_NUMBERS[cid], pay_amt,
                     "USD", "2026-03-28", status])
    # UNKNOWN_CREATOR: a payout line for someone not on the roster
    rows.append(["PAY-9099", "Ziad Marzouk", "INV-1099", 400, "USD", "2026-03-29", "Paid"])
    # NAME_MISMATCH (LOW): short-form name that fuzzy-matches Hana Mostafa
    rows.append(["PAY-9098", "Hana M.", "INV-1046", 0, "USD", "", "Pending"])
    for r in rows:
        ws.append(r)
    wb.save(BASE / "payouts.xlsx")


def make_analytics() -> None:
    """Two export snapshots (Mar 20 & Mar 22) with messy formatted numbers."""
    def snap(content_id, views, reach, imps, likes, comments, saves, shares):
        return dict(content_id=content_id, views=views, reach=reach, impressions=imps,
                    likes=likes, comments=comments, saves=saves, shares=shares)

    s20, s22 = {}, {}
    for cid, items in PLAN.items():
        creator = next(c for c in CREATORS if c[0] == cid)
        for content_id, plat, ctype, pub, appr in items:
            if not pub or content_id == "IG-1041":   # IG-1041 => ANALYTICS_MISSING
                continue
            base_v = {"ST-001": 184500, "ST-002": 121300, "ST-003": 96400,
                      "ST-004": 78200, "ST-005": 143000, "ST-006": 88500,
                      "ST-007": 102400, "ST-008": 251000, "ST-009": 67800,
                      "ST-010": 134500, "ST-011": 91200, "ST-012": 118700}[cid]
            factor = {"Reel": 1.0, "Story": 0.35, "Post": 0.6, "Video": 0.9}[ctype]
            v = int(base_v * factor)
            s20[content_id] = snap(content_id, f"{v/1000:.1f}K", f"{int(v*0.78)/1000:.1f}K",
                                   f"{int(v*1.08):,}", f"{int(v*0.046)/1000:.1f}K",
                                   int(v * 0.0017), int(v * 0.0031), int(v * 0.0012))
            # later snapshot grows ~15%; IG-1050 duplicated verbatim in both files
            g = 1.0 if content_id == "IG-1050" else 1.15
            v2 = int(v * g)
            s22[content_id] = snap(content_id, f"{v2/1000:.1f}K", f"{int(v2*0.78)/1000:.1f}K",
                                   f"{int(v2*1.08):,}", f"{int(v2*0.046)/1000:.1f}K",
                                   int(v2 * 0.0017), int(v2 * 0.0031), int(v2 * 0.0012))

    header = ["creator_name", "handle", "content_id", "platform",
              "content_type", "publish_date", "captured_at", "views", "reach",
              "impressions", "likes", "comments", "saves", "shares", "watch_time"]

    def write(path: Path, snaps: dict, captured: str):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            for cid, items in PLAN.items():
                creator = next(c for c in CREATORS if c[0] == cid)
                for content_id, plat, ctype, pub, appr in items:
                    if content_id not in snaps:
                        continue
                    m = snaps[content_id]
                    w.writerow([creator[1], creator[2], content_id, plat, ctype,
                                pub, captured, m["views"], m["reach"], m["impressions"],
                                m["likes"], m["comments"], m["saves"], m["shares"],
                                round(float(str(m["views"]).replace("K", "")) * 3.2, 1)])

    write(BASE / "analytics_export_1.csv", s20, "2026-03-20")
    write(BASE / "analytics_export_2.csv", s22, "2026-03-22")
    # LOW-CONFIDENCE MATCH source: an export using a messy display name/handle
    with open(BASE / "analytics_extra_messy.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerow(["Tanaka Kai Live", "@tanaka_kai_official", "IG-1120", "Instagram",
                    "Reel", "2026-03-12", "2026-03-22", "45.2K", "36.1K", "49,000",
                    "2.1K", 74, 120, 41, 144.6])
    # note: this file uses handle column name 'handle' consistent with exports


def make_deliverables() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "deliverables"
    ws.append(["deliverable_id", "creator", "content_id", "platform",
               "content_type", "required", "published_at", "approval_status"])
    n = 0
    for cid, items in PLAN.items():
        creator = next(c for c in CREATORS if c[0] == cid)
        for content_id, plat, ctype, pub, appr in items:
            n += 1
            # required-but-unpublished rows stay in the tracker (blank
            # published_at) so MISSING_DELIVERABLE can be detected.
            ws.append([f"DV-{n:04d}", creator[1], content_id, plat, ctype,
                       "TRUE", pub or "", appr])
    wb.save(BASE / "deliverables.xlsx")


def make_brief() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "brief"
    ws.append(["field", "value"])
    ws.append(["client_name", CLIENT])
    ws.append(["campaign_name", "Ramadan Skincare Campaign"])
    ws.append(["campaign_id", "CMP-RAMADAN-26"])
    ws.append(["start_date", "2026-02-25"])
    ws.append(["end_date", "2026-03-20"])
    ws.append(["currency", "USD"])
    ws.append(["platforms", "Instagram,TikTok"])
    wb.save(BASE / "campaign_brief.xlsx")


def make_screenshot() -> None:
    img = Image.new("RGB", (640, 420), "#ffffff")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 640, 60], fill="#f0f0f0")
    d.text((20, 20), "Instagram Insights  -  IG-1060  (Reel)", fill="#111", font_size=20)
    rows = [("Views", "118,300"), ("Reach", "92,100"), ("Likes", "5,410"),
            ("Comments", "201"), ("Saves", "388"), ("Shares", "144")]
    y = 90
    for k, v in rows:
        d.text((30, y), k, fill="#333", font_size=18)
        d.text((300, y), v, fill="#000", font_size=18)
        y += 50
    img.save(BASE / "screenshots" / "ig_insights_hana.png")
    sidecar = {
        "content_id": "IG-1060", "creator": "Hana Mostafa", "handle": "@hana.mostafa",
        "platform": "Instagram", "content_type": "Reel", "publish_date": "2026-03-09",
        "captured_at": "2026-03-22", "confidence": 0.72,
        "metrics": {"views": "118,300", "reach": "92,100", "likes": "5,410",
                    "comments": "201", "saves": "388", "shares": "144"},
    }
    (BASE / "screenshots" / "ig_insights_hana.json").write_text(json.dumps(sidecar, indent=2))


def make_corrupt_file() -> None:
    (BASE / "corrupt_contract.pdf").write_bytes(b"%PDF-1.4\nthis is not a real pdf body\n%%EOF")


if __name__ == "__main__":
    make_contracts()
    make_invoices()
    make_payouts()
    make_analytics()
    make_deliverables()
    make_brief()
    make_screenshot()
    make_corrupt_file()
    print("Demo data generated under", BASE)
