#!/usr/bin/env python3
"""Generate a fresh demo dataset for starfish_campaign_ops/input_data2.

New campaign: "XYZ Fitness Summer Fitness Campaign" (CMP-SUMFIT-26) with an
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
                    "starfish_campaign_ops", "input_data2")

CLIENT = "XYZ Fitness"
CAMPAIGN = "Summer Fitness Campaign"
CAMPAIGN_FULL = f"{CLIENT} {CAMPAIGN}"
CAMPAIGN_ID = "CMP-SUMFIT-26"
CURRENCY = "USD"
DEADLINE = "July 15, 2026"
PAY_TERMS = "Net 14 days after final deliverable"
INV_DATE = "July 20, 2026"
DUE_DATE = "August 3, 2026"

# slug, full name, handle, contract fee, invoice amount, platform mix
CREATORS = [
    ("menna_samir",   "Menna Samir",    "@menna.samir",   900,  900),
    ("tarek_yousef",  "Tarek Yousef",   "@tarek.yousef",  1400, 1550),   # invoice mismatch
    ("freddy_morgan", "Freddie Morgan", "@freddie.m",     700,  700),
    ("peter_butros",  "Peter Butros",   "@peter.b",       1000, 1000),
    ("salah_abdalla", "Salah Abdalla",  "@salah.abdalla", 1200, 1200),
    ("nina_boulos",   "Nina Boulos",    "@nina.boulos",   800,  800),
    ("mario_nabeel",  "Mario Nabeel",   "@mario.nabeel",  1600, 1600),
    ("bassem_farid",  "Bassem Farid",   "@bassem.farid",  950,  950),
    ("sandy_girgis",  "Sandy Girgis",   "@sandy.girgis",  1350, 1350),
    ("reem_helmy",    "Reem Helmy",     "@reem.helmy",    1100, 1100),
    ("hany_soliman",  "Hany Soliman",   "@hany.soliman",  1450, 1450),
]

# content_id -> (creator idx, platform, content_type, publish_date)
CONTENTS = {
    "IG-2001": (0, "Instagram", "Reel",  "2026-07-10"),
    "IG-2002": (0, "Instagram", "Story", "2026-07-11"),
    "IG-2003": (0, "Instagram", "Story", "2026-07-12"),
    "IG-2010": (1, "Instagram", "Reel",  "2026-07-09"),
    "IG-2011": (1, "Instagram", "Story", "2026-07-10"),
    "TT-2110": (1, "TikTok",    "Video", "2026-07-12"),
    "IG-2020": (2, "Instagram", "Reel",  "2026-07-08"),
    "IG-2021": (2, "Instagram", "Story", "2026-07-09"),
    "IG-2030": (3, "Instagram", "Reel",  "2026-07-07"),
    "IG-2031": (3, "Instagram", "Story", "2026-07-08"),
    "IG-2040": (4, "Instagram", "Reel",  "2026-07-11"),
    "IG-2041": (4, "Instagram", "Story", "2026-07-12"),
    "IG-2050": (5, "Instagram", "Reel",  "2026-07-06"),
    "IG-2051": (5, "Instagram", "Story", "2026-07-07"),
    "IG-2052": (5, "Instagram", "Story", "2026-07-08"),
    "IG-2060": (6, "Instagram", "Reel",  "2026-07-09"),
    "IG-2061": (6, "Instagram", "Story", "2026-07-10"),
    "IG-2070": (7, "Instagram", "Reel",  "2026-07-05"),
    "IG-2071": (7, "Instagram", "Story", "2026-07-06"),
    "IG-2072": (7, "Instagram", "Story", "2026-07-07"),
    "IG-2073": (7, "Instagram", "Post",  "2026-07-13"),
    "IG-2080": (8, "Instagram", "Reel",  "2026-07-12"),
    "IG-2081": (8, "Instagram", "Story", "2026-07-13"),
    "IG-2082": (8, "Instagram", "Story", "2026-07-14"),
    "IG-2090": (9, "Instagram", "Reel",  "2026-07-08"),
    "IG-2091": (9, "Instagram", "Story", "2026-07-09"),
    "IG-2092": (9, "Instagram", "Story", "2026-07-10"),
    "IG-2100": (10, "Instagram", "Reel",  "2026-07-11"),
    "IG-2101": (10, "Instagram", "Story", "2026-07-12"),
    "IG-2102": (10, "Instagram", "Story", "2026-07-13"),
    "IG-2110": (10, "Instagram", "Reel",  "2026-07-18"),
    "IG-2111": (10, "Instagram", "Story", "2026-07-19"),
    "IG-2112": (10, "Instagram", "Story", "2026-07-14"),
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
BASE_VIEWS = {0: 165.0, 1: 118.0, 2: 84.0, 3: 132.0, 4: 95.0, 5: 71.0,
              6: 232.0, 7: 62.0, 8: 148.0, 9: 88.0, 10: 105.0}


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
    write_csv(os.path.join(BASE, "analytics_export_1.csv"), build_rows("2026-07-20", 1.0))
    write_csv(os.path.join(BASE, "analytics_export_2.csv"), build_rows("2026-07-22", 1.15))

    messy_path = os.path.join(BASE, "analytics_extra_messy.csv")
    with open(messy_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerow(["Liam O'Connor Live", "@liam_oconnor_official", "IG-2120",
                    "Instagram", "Reel", "2026-07-12", "2026-07-22",
                    "52.3K", "41.8K", "56,900", "2.4K", "88", "139", "47", "167.4"])

    # ---------------- campaign brief ----------------
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "brief"
    ws.append(["field", "value"])
    for k, v in [("client_name", CLIENT), ("campaign_name", CAMPAIGN),
                 ("campaign_id", CAMPAIGN_ID), ("start_date", "2026-06-25"),
                 ("end_date", "2026-07-20"), ("currency", CURRENCY),
                 ("platforms", "Instagram,TikTok")]:
        ws.append([k, v])
    wb.save(os.path.join(BASE, "campaign_brief.xlsx"))

    # ---------------- deliverables ----------------
    pending_ids = {"IG-2021"}  # Freddie Morgan's story stays pending
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
    inv_nums = {i: 2040 + i for i in range(len(CREATORS))}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "payouts"
    ws.append(["payout_id", "creator_name", "invoice_number", "amount",
               "currency", "payment_date", "status"])
    pay_n = 9100
    for i, c in enumerate(CREATORS):
        if i == 2:  # Peter Butros missing from payouts sheet (like Lina before)
            continue
        pay_n += 1
        name = c[1]
        if i == 6:  # Mario Nabeel paid under a nickname
            name = "M. Nabeel"
        ws.append([f"PAY-{pay_n}", name, f"INV-{inv_nums[i]}", c[3],
                   CURRENCY, "2026-07-28", "Paid"])
    ws.append(["PAY-9199", "Farid Hamed", "INV-2099", 500, CURRENCY,
               "2026-07-29", "Paid"])
    ws.append(["PAY-9198", "Mario N.", "INV-2046", 0, None, None, "Pending"])
    wb.save(os.path.join(BASE, "payouts.xlsx"))

    # ---------------- contracts ----------------
    for i, (slug, name, handle, fee, _) in enumerate(CREATORS):
        two_col_pdf(
            os.path.join(BASE, "contracts", f"{slug}_contract.pdf"),
            "CREATOR AGREEMENT",
            [("Creator", name), ("Instagram", handle), ("Campaign", CAMPAIGN_FULL),
             ("Deliverables", "\n".join(CONTRACT_DELIVERABLES[i])),
             ("Fee", f"USD {fee}"), ("Deadline", DEADLINE),
             ("Payment Terms", PAY_TERMS)])

    # corrupt/unreadable contract placeholder (copy of original quirk)
    shutil.copyfile(os.path.join(os.path.dirname(BASE), "input_data", "corrupt_contract.pdf"),
                    os.path.join(BASE, "corrupt_contract.pdf"))

    # ---------------- invoices ----------------
    for i, (slug, name, handle, fee, amt) in enumerate(CREATORS):
        num = inv_nums[i]
        pairs = [("Creator", name), ("Instagram", handle), ("Campaign", CAMPAIGN_FULL),
                 ("Amount Due", f"USD {amt}"), ("Invoice Date", INV_DATE),
                 ("Due Date", DUE_DATE), ("Tax", "USD 0")]
        two_col_pdf(os.path.join(BASE, "invoices", f"INV-{num}_{slug}.pdf"),
                    f"INVOICE\n{num}", pairs)
        if i == 8:  # Sandy Girgis duplicate invoice, missing Tax line
            dup = pairs[:-1]
            dup[4] = ("Invoice Date", "July 21, 2026")
            dup[5] = ("Due Date", "August 4, 2026")
            two_col_pdf(os.path.join(BASE, "invoices", f"INV-{num}_sandy_duplicate.pdf"),
                        f"INVOICE\n{num}", dup)

    # ---------------- screenshot pair ----------------
    reel = CONTENTS["IG-2060"]
    ci = reel[0]
    shot = {
        "content_id": "IG-2060",
        "creator": CREATORS[ci][1],
        "handle": CREATORS[ci][2],
        "platform": "Instagram",
        "content_type": "Reel",
        "publish_date": reel[3],
        "captured_at": "2026-07-22",
        "confidence": 0.74,
        "metrics": {"views": "124,900", "reach": "97,400", "likes": "5,720",
                    "comments": "212", "saves": "386", "shares": "149"},
    }
    with open(os.path.join(BASE, "screenshots", "ig_insights_mario.json"), "w") as fh:
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
    png.cell(0, 8, "Captured 2026-07-22 - screenshot export", new_x="LMARGIN", new_y="NEXT")
    png.output(os.path.join(BASE, "screenshots", "ig_insights_mario.png"))

    print("generated files:")
    for root, _, files in os.walk(BASE):
        for f in sorted(files):
            print(os.path.relpath(os.path.join(root, f), BASE))


if __name__ == "__main__":
    main()
