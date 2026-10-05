"""End-to-end pipeline: load -> match -> reconcile -> aggregate -> exceptions.

Deterministic orchestration only; no LLM anywhere in the matching path.
"""
from __future__ import annotations

import pandas as pd

from app.core.matching import CreatorMatcher
from app.core.reconcile import (
    aggregate_analytics,
    reconcile_contracts_invoices,
    reconcile_deliverables,
    reconcile_invoices_payouts,
)
from app.core.roster import build_roster
from app.models import ExceptionItem, ReconResult


class PipelineResult:
    def __init__(self) -> None:
        self.matcher: CreatorMatcher | None = None
        self.roster: pd.DataFrame = pd.DataFrame()
        self.match_log: pd.DataFrame = pd.DataFrame()
        self.contracts_vs_invoices: ReconResult = ReconResult()
        self.invoices_vs_payouts: ReconResult = ReconResult()
        self.deliverables: ReconResult = ReconResult()
        self.analytics_deduped: pd.DataFrame = pd.DataFrame()
        self.creator_summary: pd.DataFrame = pd.DataFrame()
        self.platform_summary: pd.DataFrame = pd.DataFrame()
        self.duplicate_exceptions: list[ExceptionItem] = []
        self.identity_exceptions: list[ExceptionItem] = []
        self.exceptions: list[ExceptionItem] = []
        self.inputs: dict[str, pd.DataFrame] = {}
        self.warnings: list[str] = []

    @property
    def creator_count(self) -> int:
        return len(self.roster)


def run_pipeline(files: dict[str, pd.DataFrame]) -> PipelineResult:
    """``files`` maps logical source -> cleaned DataFrame (from loader)."""
    out = PipelineResult()
    contracts = files.get("contracts")
    invoices = files.get("invoices")
    payouts = files.get("payouts")
    analytics = files.get("analytics")
    creators = files.get("creators")

    for name in sorted(files):
        df = files[name]
        out.inputs[name] = df
        if df is not None and df.empty:
            out.warnings.append(f"{name}: file loaded but contains 0 rows.")

    missing_core = [n for n, df in (("contracts", contracts), ("invoices", invoices))
                    if df is None or df.empty]
    if missing_core:
        raise ValueError(
            "Cannot reconcile without at least these inputs: " + ", ".join(missing_core)
        )

    matcher, roster, log = build_roster(
        creators,
        {"contracts": contracts, "invoices": invoices,
         "payouts": payouts, "analytics": analytics},
    )
    out.matcher = matcher
    out.roster = roster
    out.match_log = log

    # Low-confidence identity matches become review exceptions.
    review_rows = log[log["match_status"] == "review"] if len(log) else pd.DataFrame()
    for _, r in review_rows.iterrows():
        out.identity_exceptions.append(ExceptionItem(
            exception_id="", severity="medium", category="identity_review",
            entity=f'"{r["raw_value"]}" ({r["first_seen_in"]})',
            description=(f"Name matched to {matcher.display.get(r['creator_id'], '?')} "
                         f"with low confidence score {r['score']}; verify identity."),
            evidence={"raw_value": r["raw_value"],
                      "proposed_creator_id": r["creator_id"],
                      "score": r["score"],
                      "file": r["first_seen_in"]},
        ))

    out.contracts_vs_invoices = reconcile_contracts_invoices(contracts, invoices, matcher)
    if payouts is not None and not payouts.empty:
        out.invoices_vs_payouts = reconcile_invoices_payouts(invoices, payouts, matcher)
    else:
        out.warnings.append("No payout file supplied - invoice/payment reconciliation skipped.")

    if analytics is not None and not analytics.empty:
        out.deliverables = reconcile_deliverables(contracts, analytics, matcher)
        deduped, summary, dup_excs = aggregate_analytics(analytics, matcher)
        out.analytics_deduped = deduped
        out.creator_summary = summary
        if "platform" in deduped.columns:
            plat = (deduped
                    .assign(impressions=pd.to_numeric(deduped["impressions"], errors="coerce").fillna(0))
                    .groupby("platform", dropna=False)
                    .agg(posts=("post_id", "count"), impressions=("impressions", "sum"))
                    .reset_index())
            out.platform_summary = plat
        out.duplicate_exceptions = dup_excs
    else:
        out.warnings.append("No analytics file supplied - deliverable & performance checks skipped.")

    collected: list[ExceptionItem] = []
    collected.extend(out.identity_exceptions)
    for section in (out.contracts_vs_invoices, out.invoices_vs_payouts, out.deliverables):
        collected.extend(section.exceptions)
    collected.extend(out.duplicate_exceptions)
    collected.sort(key=lambda e: ({"high": 0, "medium": 1, "low": 2}[e.severity],
                                  e.category, e.entity))
    for n, exc in enumerate(collected, start=1):
        exc.exception_id = f"EX-{n:03d}"
    out.exceptions = collected
    return out
