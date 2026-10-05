"""Client-ready PDF campaign report (ReportLab).

Every figure is recomputed from the SQLite database through reporting.metrics;
the narrative comes from reporting.narrative (deterministic template, optionally
rephrased by AI - numbers are never altered by the LLM).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from reporting import metrics
from reporting.narrative import build_narrative

ACCENT = colors.HexColor("#1F6FB2")
LIGHT = colors.HexColor("#EAF1F8")
GREY = colors.HexColor("#555555")


def _fmt(v, money=False):
    if v is None or v == "":
        return "-"
    if money:
        return f"${v:,.0f}" if float(v) == int(float(v)) else f"${float(v):,.2f}"
    if isinstance(v, (int, float)):
        return f"{v:,.2f}" if isinstance(v, float) and v < 100 else f"{v:,.0f}"
    return str(v)


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontSize=22, textColor=ACCENT),
        "sub": ParagraphStyle("s", parent=ss["Normal"], fontSize=11, textColor=GREY,
                              alignment=1),
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontSize=14,
                             textColor=ACCENT, spaceBefore=14, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.5,
                             textColor=colors.black, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=ss["Normal"], fontSize=9.5, leading=13),
        "small": ParagraphStyle("sm", parent=ss["Normal"], fontSize=8,
                                 textColor=GREY, leading=10),
    }


def _table(data, col_widths=None, header=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]
    t.setStyle(TableStyle(style))
    return t


def generate_pdf(conn: sqlite3.Connection, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    st = _styles()
    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title="Starfish Campaign Report")
    story: list = []

    camp = conn.execute("SELECT * FROM campaigns LIMIT 1").fetchone()
    client = camp["client_name"] if camp else "Client"
    cname = camp["campaign_name"] if camp else "Campaign"
    t = metrics.campaign_totals(conn)
    nar = build_narrative(conn)

    # ------------------------------------------------------------ cover
    story.append(Spacer(1, 60 * mm))
    story.append(Paragraph("STARFISH CAMPAIGN OPERATIONS", st["title"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"{client} &mdash; {cname}", st["sub"]))
    story.append(Spacer(1, 2 * mm))
    story.append(HRFlowable(width="60%", color=ACCENT, thickness=1.2))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Reconciled Campaign Performance &amp; Operations Report",
                           st["sub"]))
    story.append(Paragraph("Prepared by Starfish Agency Operations Automation",
                           st["sub"]))
    story.append(PageBreak())

    # ------------------------------------------------------ overview
    story.append(Paragraph("1. Campaign Overview", st["h1"]))
    story.append(Paragraph(nar["executive_summary"], st["body"]))
    ov = [["Metric", "Value"],
          ["Creators", _fmt(t["creators"])],
          ["Content pieces tracked (latest snapshots)", _fmt(t["content_count"])],
          ["Deliverables required / published",
           f"{t['deliverables_required']} / {t['deliverables_published']}"],
          ["Currency", camp["currency"] if camp else "USD"]]
    story.append(Spacer(1, 3 * mm))
    story.append(_table(ov, [95 * mm, 65 * mm]))

    # ---------------------------------------------------- performance
    story.append(Paragraph("2. Performance Summary", st["h1"]))
    perf_tot = [["Views", "Reach", "Impressions", "Engagements", "Engagement Rate"],
                [_fmt(t["views"]), _fmt(t["reach"]), _fmt(t["impressions"]),
                 _fmt(t["engagements"]),
                 f"{t['engagement_rate_pct']}%" if t["engagement_rate_pct"] else "n/a"]]
    story.append(_table(perf_tot, [32 * mm, 32 * mm, 32 * mm, 32 * mm, 32 * mm]))
    story.append(Paragraph(
        "Engagements = likes + comments + saves + shares. Engagement rate = "
        "engagements / reach. Figures use the latest analytics snapshot per content "
        "piece; duplicate exports are not double-counted.", st["small"]))

    story.append(Paragraph("3. Creator Performance", st["h1"]))
    rows = [["Creator", "Posts", "Views", "Reach", "Engagements", "ER %"]]
    for p in metrics.creator_performance(conn):
        rows.append([p["creator"], _fmt(p["content_count"]), _fmt(p["views"]),
                     _fmt(p["reach"]), _fmt(p["engagements"]),
                     f"{p['engagement_rate_pct']}" if p["engagement_rate_pct"] else "-"])
    story.append(_table(rows, [45 * mm, 18 * mm, 27 * mm, 27 * mm, 28 * mm, 17 * mm]))

    story.append(Paragraph("4. Content Performance", st["h1"]))
    cp = metrics.content_performance(conn)
    rows = [["Content", "Creator", "Type", "Published", "Views", "Reach", "Eng.", "ER %"]]
    for c in sorted(cp, key=lambda x: -(x["views"] or 0))[:20]:
        rows.append([c["content_id"], c["creator"], c["content_type"],
                     c["publish_date"] or "-", _fmt(c["views"]), _fmt(c["reach"]),
                     _fmt(c["engagements"]),
                     f"{c['engagement_rate_pct']}" if c["engagement_rate_pct"] else "-"])
    story.append(_table(rows, [22 * mm, 32 * mm, 20 * mm, 22 * mm, 21 * mm, 21 * mm,
                               17 * mm, 15 * mm]))
    if len(cp) > 20:
        story.append(Paragraph(f"...and {len(cp) - 20} more items (full list in Excel export).",
                               st["small"]))

    story.append(PageBreak())

    # -------------------------------------------------- deliverables
    story.append(Paragraph("5. Deliverable Reconciliation", st["h1"]))
    rows = [["Creator", "Required", "Published", "Missing", "Late", "Approval"]]
    for d in metrics.deliverable_table(conn):
        rows.append([d["creator"], _fmt(d["required"]), _fmt(d["published"]),
                     _fmt(d["missing"]), _fmt(d["late"]),
                     d["approval_statuses"] or "-"])
    story.append(_table(rows, [45 * mm, 22 * mm, 22 * mm, 20 * mm, 18 * mm, 33 * mm]))

    # ---------------------------------------------------- financials
    story.append(Paragraph("6. Financial Summary", st["h1"]))
    fin_head = [["Item", "Amount"],
                ["Contracted fees", _fmt(t["contracted_fees"], money=True)],
                ["Invoiced", _fmt(t["invoiced"], money=True)],
                ["Paid", _fmt(t["paid"], money=True)],
                ["Outstanding", _fmt(t["outstanding"], money=True)]]
    story.append(_table(fin_head, [95 * mm, 65 * mm]))
    story.append(Spacer(1, 3 * mm))
    rows = [["Creator", "Contract", "Invoice", "Payout", "Variance", "Status"]]
    for f in metrics.financial_table(conn):
        rows.append([f["creator"], _fmt(f["contract_fee"], money=True),
                     _fmt(f["invoice"], money=True), _fmt(f["payout"], money=True),
                     _fmt(f["variance"], money=True), f["status"]])
    tbl = _table(rows, [38 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm, 36 * mm])
    story.append(tbl)

    # --------------------------------------------------- exceptions
    story.append(Paragraph("7. Exceptions Queue", st["h1"]))
    ex_rows = conn.execute(
        "SELECT e.*, c.canonical_name FROM exceptions e "
        "LEFT JOIN creators c ON c.creator_id = e.creator_id "
        "ORDER BY CASE e.severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END"
    ).fetchall()
    open_ex = [e for e in ex_rows if e["status"] in ("OPEN", "IN_REVIEW")]
    rows = [["Severity", "Type", "Creator", "Detail", "Status"]]
    for e in open_ex:
        rows.append([e["severity"], e["exception_type"],
                     e["canonical_name"] or "(unmatched)",
                     Paragraph(e["description"], st["small"]), e["status"]])
    if rows.__len__() == 1:
        rows.append(["-", "-", "-", "No open exceptions.", "-"])
    story.append(_table(rows, [20 * mm, 32 * mm, 30 * mm, 68 * mm, 20 * mm]))

    # ----------------------------------------------- findings & recs
    story.append(Paragraph("8. Key Findings", st["h1"]))
    for o in nar["key_observations"]:
        story.append(Paragraph(f"&bull;&nbsp; {o}", st["body"]))
    story.append(Paragraph("Operational Observations", st["h2"]))
    for o in nar["operational_observations"]:
        story.append(Paragraph(f"&bull;&nbsp; {o}", st["body"]))

    story.append(Paragraph("9. Recommendations", st["h1"]))
    for i, r in enumerate(nar["recommendations"], 1):
        story.append(Paragraph(f"{i}.&nbsp; {r}", st["body"]))

    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#CCCCCC")))
    story.append(Paragraph(
        "All figures in this report are computed directly from reconciled source "
        "files (contracts, invoices, payouts, deliverables and analytics exports). "
        "Narrative sections may be AI-assisted but never alter numeric values. "
        f"Report narrative source: {nar.get('source', 'deterministic template')}.",
        st["small"]))

    doc.build(story)
    return path
