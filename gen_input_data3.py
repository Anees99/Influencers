#!/usr/bin/env python3
"""Generate a fresh demo dataset for starfish_campaign_ops/input_data3.

New campaign: "Nova Tech Ramadan Tech Campaign" (CMP-RAMTECH-26) with an
entirely different set of creators, values and dates. The structure/quirks of
the original input_data are mirrored 1:1 (duplicate invoices, mismatched fees,
pending deliverable, phantom payout rows, messy analytics row, corrupt PDF...).
"""
import csv
import json
import os
import shutil

from fpdf import FPDF
import openpyxl

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "starfish_campaign_ops", "input_data3")

CLIENT = "Nova Tech"
CAMPAIGN = "Ramadan Tech Campaign"
CAMPAIGN_FULL = f"{CLIENT} {CAMPAIGN}"
CAMPAIGN_ID = "CMP-RAMTECH-26"
CURRENCY = "USD"
DEADLINE = "March 19, 2026"
PAY_TERMS = "Net 14 days after final deliverable"
INV_DATE = "March 25, 2026"
DUE_DATE = "April 8, 2026"

# slug, full name, handle, contract fee, invoice amount, platform mix
CREATORS = [
    ("karim_fahmy",   "Karim Fahmy",    "@karim.fahmy",    1100, 1100),
    ("youssef_adel",  "Youssef Adel",   "@youssef.adel",   1500, 1675),   # invoice mismatch
    ("laila_mansour", "Laila Mansour",  "@laila.m",        850,  850),
    ("hassan_ibrahim","Hassan Ibrahim", "@hassan.ibrahim", 1250, 1250),
    ("salma_khaled",  "Salma Khaled",   "@salma.khaled",   950,  950),
    ("nour_hamdy",    "Nour Hamdy",     "@nour.hamdy",     1050, 1050),
    ("yara_sameh",    "Yara Sameh",     "@yara.sameh",     1400, 1400),
    ("ady_guergues",  "Ady Guergues",   "@ady.guergues",   780,  780),
    ("mariam_faiez",  "Mariam Faiez",   "@mariam.faiez",   1300, 1300),
    ("dina_sherif",   "Dina Sherif",    "@dina.sherif",    1150, 1150),
    ("george_bakhoum","George Bakhoum", "@george.bakhoum", 1600, 1600),
]

# content_id -> (creator idx, platform, content_type, publish_date)
CONTENTS = {
    "IG-3001": (0, "Instagram", "Reel",  "2026-03-05"),
    "IG-3002": (0, "Instagram", "Story", "2026-03-06"),
    "IG-3003": (0, "Instagram", "Story", "2026-03-07"),
    "IG-3010": (1, "Instagram", "Reel",  "2026-03-04"),
    "IG-3011": (1, "Instagram", "Story", "2026-03-05"),
    "TT-3110": (1, "TikTok",    "Video", "2026-03-07"),
    "IG-3020": (2, "Instagram", "Reel",  "2026-03-03"),
    "IG-3021": (2, "Instagram", "Story", "2026-03-04"),
    "IG-3030": (3, "Instagram", "Reel",  "2026-03-02"),
    "IG-3031": (3, "Instagram", "Story", "2026-03-03"),
    "IG-3040": (4, "Instagram", "Reel",  "2026-03-06"),
    "IG-3041": (4, "Instagram", "Story", "2026-03-07"),
    "IG-3050": (5, "Instagram", "Reel",  "2026-03-01"),
    "IG-3051": (5, "Instagram", "Story", "2026-03-02"),
    "IG-3052": (5, "Instagram", "Story", "2026-03-03"),
    "IG-3060": (6, "Instagram", "Reel",  "2026-03-04"),
    "IG-3061": (6, "Instagram", "Story", "2026-03-05"),
    "IG-3070": (7, "Instagram", "Reel",  "2026-02-28"),
    "IG-3071": (7, "Instagram", "Story", "2026-03-01"),
    "IG-3072": (7, "Instagram", "Story", "2026-03-02"),
    "IG-3073": (7, "Instagram", "Post",  "2026-03-08"),
    "IG-3080": (8, "Instagram", "Reel",  "2026-03-07"),
    "IG-3081": (8, "Instagram", "Story", "2026-03-08"),
    "IG-3082": (8, "Instagram", "Story", "2026-03-09"),
    "IG-3090": (9, "Instagram", "Reel",  "2026-03-03"),
    "IG-3091": (9, "Instagram", "Story", "2026-03-04"),
    "IG-3092": (9, "Instagram", "Story", "2026-03-05"),
    "IG-3100": (10, "Instagram", "Reel",  "2026-03-06"),
    "IG-3101": (10, "Instagram", "Story", "2026-03-07"),
    "IG-3102": (10, "Instagram", "Story", "2026-03-08"),
    "IG-3110": (10, "Instagram", "Reel",  "2026-03-13"),
    "IG-3111": (10, "Instagram", "Story", "2026-03-14"),
    "IG-3112": (10, "Instagram", "Story", "2026-03-09"),
}

# creator index -> deliverables text for the contract
CONTRACT_DELIVERABLES = {
    0: ["1 Instagram Reel", "2 Instagram Stories"],
    1: ["1 Instagram Reel", "1 Instagram Story", "1 TikTok Video"],
    2: ["1 Instagram Reel", "1 Instagram Story"],
    3: ["1 Instagram Reel", "2 Instagram Stories"],
    4: ["1 Instagram Reel", "1 Instagram Story"],
    5: ["1 Instagram Reel", "2 Instagram Stories"],
    6: ["1 Instagram Reel", "1 Instagram Story"],
    7: ["1 Instagram Reel", "2 Instagram Stories", "1 Instagram Post"],
    8: ["1 Instagram Reel", "2 Instagram Stories"],
    9: ["1 Instagram Reel", "2 Instagram Stories"],
    10: ["2 Instagram Reels", "3 Instagram Stories"],
}

# per-creator base views used to derive all engagement metrics
BASE_VIEWS = {0: 96.0, 1: 143.0, 2: 61.0, 3: 118.0, 4: 87.0, 5: 154.0,
              6: 79.0, 7: 131.0, 8: 68.0, 9: 109.0, 10: 195.0}


def fmt_k(x):
    """Format thousands value like '165.3K'."""
    return f"{x:.1f}K"


def build_rows(captured_at, growth):
    """Return analytics rows for one capture date; growth scales the numbers."""
    rows = []
    story_cache = {}
    for cid, (ci, platform, ctype, pub) in sorted(CONTENTS.items()):
        if ctype == "Story":
            # stories of the same creator share identical stats (like original data)
            if ci not in story_cache:
                story_cache[ci] = BASE_VIEWS[ci] * 0.35
            v = story_cache[ci]
        elif ctype == "Post":
            v = BASE_VIEWS[ci] * 0.91
        else:
            v = BASE_VIEWS[ci]
        v *= growth
        reach = v * 0.78
        imps = int(v * 1000 * 1.08)
        likes = v * 0.046
        comments = max(1, round(v * 1.7))
        saves = max(1, round(v * 3.1))
        shares = max(1, round(v * 1.2))
        watch = v * 3.2
        name = CREATORS[ci][1]
        handle = CREATORS[ci][2]
        rows.append([name, handle, cid, platform, ctype, pub, captured_at,
                     fmt_k(v), fmt_k(reach), f"{imps:,}", fmt_k(likes),
                     str(comments), str(saves), str(shares), f"{watch:.1f}"])
    return rows


HEADER = ["creator_name", "handle", "content_id", "platform", "content_type",
          "publish_date", "captured_at", "views", "reach", "impressions",
          "likes", "comments", "saves", "shares", "watch_time"]


def write_csv(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)


def one_per_line_pdf(path, title_lines, lines):
    """Render like the original CRM exports: every field on its own line."""
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    for t in title_lines:
        pdf.cell(0, 12, t, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("helvetica", "", 12)
    for ln in lines:
        pdf.cell(0, 9, ln, new_x="LMARGIN", new_y="NEXT")
    pdf.output(path)


def two_col_pdf(path, title, pairs):
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 14, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("helvetica", "", 12)
    for label, value in pairs:
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(55, 9, label + ":")
        pdf.set_font("helvetica", "", 12)
        pdf.multi_cell(0, 9, value)
        pdf.ln(1)
    pdf.output(path)


def main():
    os.makedirs(BASE, exist_ok=True)
    for sub in ("contracts", "invoices", "screenshots"):
        os.makedirs(os.path.join(BASE, sub), exist_ok=True)

    # ---------------- CSVs ----------------
    write_csv(os.path.join(BASE, "analytics_export_1.csv"), build_rows("2026-03-20", 1.0))
    write_csv(os.path.join(BASE, "analytics_export_2.csv"), build_rows("2026-03-22", 1.18))

    messy_path = os.path.join(BASE, "analytics_extra_messy.csv")
    with open(messy_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerow(["Ziad Haddad Live", "@ziad.haddad.official", "IG-3120",
                    "Instagram", "Reel", "2026-03-05", "2026-03-22",
                    "47.9K", "36.2K", "51,700", "2.1K", "74", "121", "39", "151.8"])

    # ---------------- campaign brief ----------------
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "brief"
    ws.append(["field", "value"])
    for k, v in [("client_name", CLIENT), ("campaign_name", CAMPAIGN),
                 ("campaign_id", CAMPAIGN_ID), ("start_date", "2026-02-20"),
                 ("end_date", "2026-03-19"), ("currency", CURRENCY),
                 ("platforms", "Instagram,TikTok")]:
        ws.append([k, v])
    wb.save(os.path.join(BASE, "campaign_brief.xlsx"))

    # ---------------- deliverables ----------------
    pending_ids = {"IG-3021"}  # Laila Mansour's story stays pending
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "deliverables"
    ws.append(["deliverable_id", "creator", "content_id", "platform",
               "content_type", "required", "published_at", "approval_status"])
    n = 0
    for cid, (ci, platform, ctype, pub) in sorted(CONTENTS.items()):
        n += 1
        status = "pending" if cid in pending_ids else "approved"
        ws.append([f"DV-{n:04d}", CREATORS[ci][1], cid, platform, ctype,
                   True, pub, status])
    wb.save(os.path.join(BASE, "deliverables.xlsx"))

    # ---------------- payouts ----------------
    inv_nums = {i: 3100 + i for i in range(len(CREATORS))}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "payouts"
    ws.append(["payout_id", "creator_name", "invoice_number", "amount",
               "currency", "payment_date", "status"])
    pay_n = 9300
    for i, c in enumerate(CREATORS):
        if i == 3:  # Hassan Ibrahim missing from payouts sheet (like Lina before)
            continue
        pay_n += 1
        name = c[1]
        if i == 7:  # Ady Guergues paid under a nickname
            name = "A. Guergues"
        ws.append([f"PAY-{pay_n}", name, f"INV-{inv_nums[i]}", c[3],
                   CURRENCY, "2026-03-28", "Paid"])
    ws.append(["PAY-9399", "Toni Bassil", "INV-3199", 600, CURRENCY,
               "2026-03-30", "Paid"])
    ws.append(["PAY-9398", "Ady G.", "INV-3107", 0, None, None, "Pending"])
    wb.save(os.path.join(BASE, "payouts.xlsx"))

    # ---------------- contracts ----------------
    for i, (slug, name, handle, fee, _) in enumerate(CREATORS):
        lines = [f"Creator: {name}", f"Instagram: {handle}", f"Campaign: {CAMPAIGN_FULL}",
                 "Deliverables:"] + CONTRACT_DELIVERABLES[i] + [
                 f"Fee: USD {fee}", f"Deadline: {DEADLINE}", f"Payment Terms: {PAY_TERMS}"]
        one_per_line_pdf(os.path.join(BASE, "contracts", f"{slug}_contract.pdf"),
                         ["CREATOR AGREEMENT"], lines)

    # corrupt/unreadable contract placeholder (copy of original quirk)
    shutil.copyfile(os.path.join(os.path.dirname(BASE), "input_data2", "corrupt_contract.pdf"),
                    os.path.join(BASE, "corrupt_contract.pdf"))

    # ---------------- invoices ----------------
    for i, (slug, name, handle, fee, amt) in enumerate(CREATORS):
        num = inv_nums[i]
        pairs = [("Creator", name), ("Instagram", handle), ("Campaign", CAMPAIGN_FULL),
                 ("Amount Due", f"USD {amt}"), ("Invoice Date", INV_DATE),
                 ("Due Date", DUE_DATE), ("Tax", "USD 0")]
        lines = [f"Invoice No: INV-{num}"] + [f"{k}: {v}" for k, v in pairs]
        one_per_line_pdf(os.path.join(BASE, "invoices", f"INV-{num}_{slug}.pdf"),
                         ["INVOICE"], lines)
        if i == 8:  # Mariam Faiez duplicate invoice, missing Tax line
            dup = pairs[:-1]
            dup[4] = ("Invoice Date", "March 26, 2026")
            dup[5] = ("Due Date", "April 9, 2026")
            dlines = [f"Invoice No: INV-{num}"] + [f"{k}: {v}" for k, v in dup]
            one_per_line_pdf(os.path.join(BASE, "invoices", f"INV-{num}_mariam_duplicate.pdf"),
                             ["INVOICE"], dlines)

    # ---------------- screenshot pair ----------------
    reel = CONTENTS["IG-3060"]
    ci = reel[0]
    shot = {
        "content_id": "IG-2060",
        "creator": CREATORS[ci][1],
        "handle": CREATORS[ci][2],
        "platform": "Instagram",
        "content_type": "Reel",
        "publish_date": reel[3],
        "captured_at": "2026-03-22",
        "confidence": 0.74,
        "metrics": {"views": "88,600", "reach": "69,100", "likes": "4,070",
                    "comments": "163", "saves": "274", "shares": "102"},
    }
    with open(os.path.join(BASE, "screenshots", "ig_insights_yara.json"), "w") as fh:
        json.dump(shot, fh, indent=2)

    png = FPDF(format="A4")
    png.set_auto_page_break(False)
    png.add_page()
    png.set_font("helvetica", "B", 18)
    png.cell(0, 14, "Instagram Insights", new_x="LMARGIN", new_y="NEXT")
    png.ln(4)
    png.set_font("helvetica", "", 12)
    png.multi_cell(0, 8, f"Reel by {CREATORS[ci][2]} - posted {reel[3]}")
    png.ln(3)
    for k, v in shot["metrics"].items():
        png.set_font("helvetica", "B", 12)
        png.cell(60, 8, k.capitalize() + ":")
        png.set_font("helvetica", "", 12)
        png.cell(0, 8, v, new_x="LMARGIN", new_y="NEXT")
    png.set_font("helvetica", "I", 10)
    png.ln(4)
    png.cell(0, 8, "Captured 2026-03-22 - screenshot export", new_x="LMARGIN", new_y="NEXT")
    png.output(os.path.join(BASE, "screenshots", "ig_insights_yara.png"))

    print("generated files:")
    for root, _, files in os.walk(BASE):
        for f in sorted(files):
            print(os.path.relpath(os.path.join(root, f), BASE))


if __name__ == "__main__":
    main()
