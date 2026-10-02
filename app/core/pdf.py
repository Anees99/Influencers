"""PDF client report generation (fpdf2). Built-in Helvetica only, latin-1 safe."""
from __future__ import annotations

from fpdf import FPDF

from app.core.pipeline import PipelineResult

TEAL = (19, 78, 74)
LIGHT = (235, 244, 243)
RED = (185, 28, 28)
AMBER = (180, 83, 9)
GREY = (110, 110, 110)


class ReportPDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 6, "Starfish - Autumn Creator Program | Confidential", align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def _t(s: object) -> str:
    """Latin-1 safe text for core fonts."""
    return str(s).encode("latin-1", "replace").decode("latin-1")


def _table(pdf: ReportPDF, headers: list[str], rows: list[list], widths: list[float] | None = None,
           empty: str = "No records."):
    if not rows:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*GREY)
        pdf.cell(0, 6, _t(empty), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(40, 40, 40)
        return
    n = len(headers)
    if widths is None:
        widths = [(190 / n)] * n
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(*TEAL)
    pdf.set_text_color(255, 255, 255)
    for h, w in zip(headers, widths):
        pdf.cell(w, 6.5, _t(h), border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_text_color(40, 40, 40)
    pdf.set_font("Helvetica", "", 8.5)
    for i, row in enumerate(rows):
        if pdf.get_y() > 275:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(255, 255, 255)
            for h, w in zip(headers, widths):
                pdf.cell(w, 6.5, _t(h), border=1, fill=True, align="C")
            pdf.ln()
            pdf.set_text_color(40, 40, 40)
            pdf.set_font("Helvetica", "", 8.5)
        fill = i % 2 == 1
        if fill:
            pdf.set_fill_color(246, 249, 248)
        for val, w in zip(row, widths):
            txt = val if isinstance(val, str) else _t(val)
            pdf.cell(w, 6, _t(txt[:40]), border=1, fill=fill)
        pdf.ln()


def build_pdf(result: PipelineResult) -> bytes:
    pdf = ReportPDF(format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(True, margin=18)

    # ---------- Cover / executive summary ----------
    pdf.add_page()
    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 0, 210, 44, style="F")
    pdf.set_y(11)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 10, "Starfish Campaign Operations", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 13)
    pdf.cell(0, 8, "Reconciliation & Performance Report - September 2026",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(40, 40, 40)
    pdf.set_y(56)

    hi = sum(1 for e in result.exceptions if e.severity == "high")
    med = sum(1 for e in result.exceptions if e.severity == "medium")
    low = sum(1 for e in result.exceptions if e.severity == "low")
    ci_m = result.contracts_vs_invoices.summary.get("matched", 0)
    ci_n = result.contracts_vs_invoices.summary.get("creators_checked", 0)
    ip_m = result.invoices_vs_payouts.summary.get("matched", 0)
    ip_n = result.invoices_vs_payouts.summary.get("invoices", 0)

    kpis = [
        ("Creators identified", str(result.creator_count)),
        ("Creators reconciled contract vs invoice", f"{ci_m} of {ci_n}"),
        ("Invoices matched to payouts", f"{ip_m} of {ip_n}"),
        ("Deliverable checks passed", f"{len(result.deliverables.matched)}"),
        ("Open exceptions", str(len(result.exceptions))),
    ]
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Executive summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for label, value in kpis:
        pdf.set_fill_color(*LIGHT)
        pdf.cell(120, 8, _t(f"  {label}"), border=1, fill=True)
        pdf.cell(0, 8, _t(value), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, _t(
        f"Exception profile: {hi} high severity, {med} medium, {low} low. "
        "All figures in this report are produced by deterministic reconciliation "
        "rules (exact keys and tolerance thresholds). No estimated or model-generated "
        "values are included, and every exception carries evidence drawn directly "
        "from the source records."))

    # ---------- Financial reconciliation ----------
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Financial reconciliation", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Contracts vs invoices (per creator)", new_x="LMARGIN", new_y="NEXT")
    rows = result.contracts_vs_invoices.matched + \
        result.contracts_vs_invoices.summary.get("rows", [])
    _table(pdf, ["Creator", "Contracted", "Invoiced", "Variance", "State"],
           [[_t(r["name"]), f"${r['contracted_total']:,.2f}", f"${r['invoiced_total']:,.2f}",
             f"${r['variance']:+,.2f}", r["state"]] for r in rows],
           widths=[55, 32, 32, 32, 39])

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Invoices matched to payouts", new_x="LMARGIN", new_y="NEXT")
    _table(pdf, ["Invoice", "Creator", "Amount", "Payment ref", "Paid on"],
           [[r["invoice_number"], _t(r["name"]), f"${r['invoice_amount']:,.2f}",
             r["payment_ref"], r["payment_date"]]
            for r in result.invoices_vs_payouts.matched],
           widths=[30, 55, 30, 40, 35],
           empty="No paid invoices matched.")

    # ---------- Performance ----------
    if len(result.creator_summary):
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Campaign performance (deduplicated analytics)",
                 new_x="LMARGIN", new_y="NEXT")
        cs = result.creator_summary
        _table(pdf, ["Creator", "Posts", "Impressions", "Engagements", "Clicks",
                     "Conv.", "Spend", "Eng rate"],
               [[_t(r["name"]), int(r["posts"]), f'{int(r["impressions"]):,}',
                 f'{int(r["engagements"]):,}', f'{int(r.get("clicks", 0) or 0):,}',
                 int(r.get("conversions", 0) or 0),
                 f'${float(r.get("spend", 0) or 0):,.2f}',
                 f'{float(r["engagement_rate"]) * 100:.1f}%']
                for _, r in cs.iterrows()],
               widths=[42, 14, 26, 26, 20, 16, 26, 20])
        if len(result.platform_summary):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 7, "By platform", new_x="LMARGIN", new_y="NEXT")
            _table(pdf, ["Platform", "Posts", "Impressions"],
                   [[r["platform"], int(r["posts"]), f'{int(r["impressions"]):,}']
                    for _, r in result.platform_summary.iterrows()],
                   widths=[60, 30, 40])

    # ---------- Exception register ----------
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Exception register with evidence", new_x="LMARGIN", new_y="NEXT")
    if result.exceptions:
        for e in result.exceptions:
            if pdf.get_y() > 245:
                pdf.add_page()
            color = RED if e.severity == "high" else AMBER if e.severity == "medium" else GREY
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*color)
            pdf.cell(0, 6, _t(f'{e.exception_id}  [{e.severity.upper()}]  {e.category}'),
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(40, 40, 40)
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5, _t(f'{e.entity} - {e.description}'))
            pdf.set_text_color(*GREY)
            ev = "; ".join(f"{k}: {v}" for k, v in e.evidence.items())
            pdf.multi_cell(0, 5, _t("Evidence: " + (ev[:500] or "-")))
            pdf.set_text_color(40, 40, 40)
            pdf.ln(2)
    else:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 8, "No open exceptions.")

    out = pdf.output()
    return bytes(bytearray(out))
