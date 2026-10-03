"""Reconciliation engine - deterministic orchestration.

FILES -> INGESTION -> EXTRACTION -> NORMALIZATION -> ENTITY MATCHING ->
RECONCILIATION -> EXCEPTION QUEUE.

The LLM is never consulted for any numeric decision in this module. Optional
AI assistance (ambiguous matching suggestions, narrative phrasing) happens in
the ai/ package and only ever annotates results produced here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import settings
from ingestion.router import FileResult, process_file
from matching.content_matching import match_content
from matching.creator_matching import CreatorRegistry
from reconciliation.analytics import engagement_rate, latest_snapshots, reconcile_analytics
from reconciliation.deliverables import reconcile_deliverables
from reconciliation.exceptions import make, reset_counter
from reconciliation.financial import reconcile_financials
from schemas.campaign import Campaign
from schemas.creator import Creator


@dataclass
class PendingMatch:
    """A record identity string that could not be confidently resolved."""
    raw_value: str
    source_file: str
    record_kind: str          # contract | invoice | payout | deliverable | analytics
    record_id: str
    suggested_id: str | None  # best fuzzy candidate (not applied)
    score: float
    reason: str


@dataclass
class PipelineResult:
    campaign: Campaign | None = None
    creators: dict[str, Creator] = field(default_factory=dict)
    contracts: list = field(default_factory=list)
    invoices: list = field(default_factory=list)
    payouts: list = field(default_factory=list)
    deliverables: list = field(default_factory=list)
    analytics: list = field(default_factory=list)
    exceptions: list = field(default_factory=list)
    pending_matches: list[PendingMatch] = field(default_factory=list)
    brief: dict | None = None
    financial_rows: list[dict] = field(default_factory=list)
    deliverable_rows: list[dict] = field(default_factory=list)
    content_metrics: list[dict] = field(default_factory=list)
    creator_metrics: list[dict] = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    file_results: list[FileResult] = field(default_factory=list)
    steps_done: list[str] = field(default_factory=list)

    def creator_name(self, cid: str | None) -> str:
        if cid is None:
            return "(unmatched)"
        c = self.creators.get(cid)
        return c.canonical_name if c else cid


# ------------------------------------------------------------------ helpers

def _extracted(obj, key="creator_name", default=None):
    try:
        return obj.__dict__.get("_extracted", {}).get(key, default)
    except AttributeError:
        return default


class ReconciliationEngine:
    def __init__(self, campaign: Campaign | None = None):
        self.campaign = campaign
        self.registry = CreatorRegistry()
        self.result = PipelineResult(campaign=campaign)

    # ---------------------------------------------------------- ingestion
    def ingest(self, files: list[tuple[str, bytes, str]],
               sidecars: dict[str, dict] | None = None) -> "ReconciliationEngine":
        """files: [(filename, blob, category)]; auto-guesses category when blank.

        Screenshots may carry their (filename, payload) tuple in `sidecars`;
        when absent we look for a same-named .json next to the file on disk.
        """
        sidecars = dict(sidecars or {})
        cid = self.campaign.campaign_id if self.campaign else ""
        # process campaign brief first so its metadata is available to the UI
        order = {"Campaign Brief": 0}
        files = sorted(files, key=lambda f: order.get(f[2], 1))
        from ingestion.router import guess_category
        for filename, blob, category in files:
            cat = category or guess_category(filename, "") or "Contract"
            if cat == "Screenshot" and filename not in sidecars:
                stem = Path(filename).stem.lower()
                demo_dir = settings.demo_data_dir / "screenshots"
                if demo_dir.is_dir():
                    for cand in demo_dir.glob("*.json"):
                        if cand.stem.lower() == stem:
                            sidecars[filename] = json.loads(cand.read_text())
                            break
            fr = process_file(filename, blob, cat, campaign_id=cid,
                              sidecar=sidecars.get(filename))
            self.result.file_results.append(fr)
            if fr.brief is not None:
                self.result.brief = fr.brief
            self.result.contracts.extend(fr.contracts)
            self.result.invoices.extend(fr.invoices)
            self.result.payouts.extend(fr.payouts)
            self.result.deliverables.extend(fr.deliverables)
            self.result.analytics.extend(fr.analytics)
        self.result.steps_done.append("Ingestion + extraction complete")
        return self

    # ------------------------------------------------------- normalization
    def normalize_creators(self, roster: list[Creator]) -> "ReconciliationEngine":
        for cr in roster:
            self.registry.add(cr.creator_id, cr.canonical_name,
                              instagram_handle=cr.instagram_handle,
                              tiktok_handle=cr.tiktok_handle, email=cr.email)
            self.result.creators[cr.creator_id] = cr
        self.result.steps_done.append(f"{len(roster)} creators normalized")
        return self

    def _bind(self, obj, kind: str) -> None:
        """Resolve an extracted identity string onto the record via registry."""
        raw = _extracted(obj) or ""
        handle = _extracted(obj, "handle")
        query = f"{raw} {handle}".strip() if (raw and handle) else (raw or handle or "")
        dec = self.registry.resolve(query)
        obj.match_confidence = dec.score
        obj.match_method = dec.method
        obj.match_reason = dec.reason
        record_id = (getattr(obj, "contract_id", None) or getattr(obj, "invoice_id", None)
                     or getattr(obj, "deliverable_id", None)
                     or getattr(obj, "analytics_id", "?"))
        if dec.creator_id and not dec.needs_review:
            obj.creator_id = dec.creator_id
            return
        # unresolved or low-confidence -> queue for HUMAN REVIEW (never silent merge)
        self.result.pending_matches.append(PendingMatch(
            raw_value=query or "(blank)", source_file=obj.source_file,
            record_kind=kind, record_id=record_id,
            suggested_id=dec.creator_id, score=dec.score, reason=dec.reason))
        if dec.creator_id:      # ambiguous but a candidate exists: attach w/ review flag
            obj.creator_id = dec.creator_id
        else:                   # no candidate at all
            obj.creator_id = None

    def match_entities(self) -> "ReconciliationEngine":
        for ct in self.result.contracts:
            self._bind(ct, "contract")
        for iv in self.result.invoices:
            self._bind(iv, "invoice")
        for py in self.result.payouts:
            # identity resolution order: the name in the payment feed first,
            # then fall back to the invoice number (exact financial link).
            py_decision = self.registry.resolve(py.creator_raw or "")
            if not py_decision.creator_id and py.invoice_number:
                inv_match = next((iv for iv in self.result.invoices
                                  if iv.invoice_number == py.invoice_number), None)
                if inv_match is not None and getattr(inv_match, "creator_id", None):
                    py.creator_id = inv_match.creator_id
                    py.match_confidence = 1.0
                    py.match_method = "invoice_number"
                    py.match_reason = f"payout references {py.invoice_number}"
                    continue
            py.match_confidence = py_decision.score
            py.match_method = py_decision.method
            py.match_reason = py_decision.reason
            if py_decision.creator_id and not py_decision.needs_review:
                py.creator_id = py_decision.creator_id
            else:
                self.result.pending_matches.append(PendingMatch(
                    raw_value=py.creator_raw or "(blank)", source_file=py.source_file,
                    record_kind="payout", record_id=py.payout_id,
                    suggested_id=py_decision.creator_id, score=py_decision.score,
                    reason=py_decision.reason))
                py.creator_id = py_decision.creator_id if py_decision.creator_id else None
        for dv in self.result.deliverables:
            self._bind(dv, "deliverable")
        for ar in self.result.analytics:
            q = f"{ar.creator_raw} {ar.handle_raw or ''}".strip()
            dec = self.registry.resolve(q)
            if dec.creator_id and not dec.needs_review:
                ar.creator_id = dec.creator_id
            elif dec.creator_id:
                ar.creator_id = dec.creator_id
                self.result.pending_matches.append(PendingMatch(
                    raw_value=q, source_file=ar.source_file, record_kind="analytics",
                    record_id=ar.analytics_id, suggested_id=dec.creator_id,
                    score=dec.score, reason=dec.reason))
            else:
                ar.creator_id = None
                if q:
                    self.result.pending_matches.append(PendingMatch(
                        raw_value=q, source_file=ar.source_file, record_kind="analytics",
                        record_id=ar.analytics_id, suggested_id=None,
                        score=dec.score, reason=dec.reason))
        self.result.steps_done.append("Entity matching complete")
        return self

    def apply_approved_match(self, pending_index: int, creator_id: str) -> bool:
        """Human-review approve: bind the record now (never done silently)."""
        if not (0 <= pending_index < len(self.result.pending_matches)):
            return False
        pm = self.result.pending_matches[pending_index]
        tables = {"contract": self.result.contracts, "invoice": self.result.invoices,
                  "payout": self.result.payouts, "deliverable": self.result.deliverables,
                  "analytics": self.result.analytics}
        for obj in tables.get(pm.record_kind, []):
            oid = (getattr(obj, "contract_id", None) or getattr(obj, "invoice_id", None)
                   or getattr(obj, "payout_id", None) or getattr(obj, "deliverable_id", None)
                   or getattr(obj, "analytics_id", None))
            if oid == pm.record_id:
                obj.creator_id = creator_id
                obj.match_method = "human_review"
                obj.match_confidence = 1.0
                obj.match_reason = f"approved by operator ({pm.raw_value})"
                pm.resolved = True
                return True
        return False

    # ---------------------------------------------------- content matching
    def match_content_rows(self) -> "ReconciliationEngine":
        deliv_dicts = [{"deliverable_id": d.deliverable_id, "content_id": d.content_id,
                        "platform": d.platform, "creator_id": d.creator_id,
                        "content_type": d.content_type, "published_at": d.published_at}
                       for d in self.result.deliverables]
        claimed: set[str] = set()
        for ar in self.result.analytics:
            free = [c for c in deliv_dicts if c["deliverable_id"] not in claimed]
            m = match_content(ar.content_id, ar.platform, ar.creator_id,
                              ar.content_type, ar.publish_date, free)
            ar.confidence = min(ar.confidence, m.score) if m.method != "none" else ar.confidence
            if m.deliverable_id:
                claimed.add(m.deliverable_id)
        self.result.steps_done.append("Content matching complete")
        return self

    # ------------------------------------------------------ reconciliation
    def reconcile(self) -> "ReconciliationEngine":
        ex: list = []

        # unknown creators / low-confidence matches from the matching stage
        for pm in self.result.pending_matches:
            if pm.suggested_id is None:
                ex.append(make(
                    "UNKNOWN_CREATOR",
                    f"'{pm.raw_value}' in {pm.source_file} does not match any known creator.",
                    expected="known creator", actual=pm.raw_value,
                    evidence={"record": pm.record_id, "kind": pm.record_kind,
                              "best_score": pm.score, "reason": pm.reason},
                    source_files=[pm.source_file]))
            else:
                name = self.result.creators[pm.suggested_id].canonical_name \
                    if pm.suggested_id in self.result.creators else pm.suggested_id
                # short-form/alias names that fuzzy-match well are a LOW
                # housekeeping flag; genuinely ambiguous identities go to
                # human review at MEDIUM severity.
                etype = "NAME_MISMATCH" if pm.score >= 0.80 else "MATCH_REVIEW"
                ex.append(make(
                    etype,
                    f"'{pm.raw_value}' tentatively linked to {name} at "
                    f"{pm.score:.0%} confidence - awaiting human review.",
                    creator_id=pm.suggested_id,
                    expected=">= auto-accept threshold", actual=f"{pm.score:.0%}",
                    evidence={"record": pm.record_id, "kind": pm.record_kind,
                              "suggested": name, "reason": pm.reason},
                    source_files=[pm.source_file]))

        fin_rows, fin_ex = reconcile_financials(
            self.result.contracts, self.result.invoices, self.result.payouts)
        ex.extend(fin_ex)
        self.result.financial_rows = fin_rows

        del_rows, del_ex = reconcile_deliverables(
            self.result.contracts, self.result.deliverables)
        ex.extend(del_ex)
        self.result.deliverable_rows = del_rows

        latest = latest_snapshots([a for a in self.result.analytics
                                   if not a.needs_verification])
        deliv_by_content = {d.content_id: {"creator_id": d.creator_id,
                                           "platform": d.platform,
                                           "content_type": d.content_type,
                                           "published_at": d.published_at,
                                           "source_file": d.source_file}
                            for d in self.result.deliverables if d.content_id}
        ana_ex, _ = reconcile_analytics(self.result.analytics, deliv_by_content)
        ex.extend(ana_ex)

        # per-content metrics (latest snapshot only - no double counting)
        content_rows = []
        for cid, r in sorted(latest.items()):
            eng = sum((getattr(r, f) or 0) for f in
                      ("likes", "comments", "saves", "shares"))
            er = round(eng / r.reach * 100, 2) if r.reach else None
            content_rows.append({
                "content_id": cid, "creator_id": r.creator_id,
                "creator": self.result.creator_name(r.creator_id),
                "platform": r.platform, "content_type": r.content_type,
                "publish_date": r.publish_date, "views": r.views, "reach": r.reach,
                "impressions": r.impressions, "likes": r.likes, "comments": r.comments,
                "saves": r.saves, "shares": r.shares, "engagements": eng,
                "engagement_rate_pct": er, "source_file": r.source_file,
                "captured_at": r.captured_at, "source_type": r.source_type})
        self.result.content_metrics = content_rows

        # per-creator performance rollup
        agg: dict[str | None, dict] = {}
        for row in content_rows:
            a = agg.setdefault(row["creator_id"], {
                "creator_id": row["creator_id"], "creator": row["creator"],
                "content_count": 0, "views": 0, "reach": 0, "impressions": 0,
                "likes": 0, "comments": 0, "saves": 0, "shares": 0, "engagements": 0})
            a["content_count"] += 1
            for k in ("views", "reach", "impressions", "likes", "comments",
                      "saves", "shares"):
                a[k] += row[k] or 0
        for a in agg.values():
            a["engagements"] = a["likes"] + a["comments"] + a["saves"] + a["shares"]
            a["engagement_rate_pct"] = (round(a["engagements"] / a["reach"] * 100, 2)
                                        if a["reach"] else None)
        self.result.creator_metrics = sorted(agg.values(),
                                             key=lambda x: -(x["views"] or 0))

        # totals for dashboard/reports
        tot_reach = sum(r["reach"] or 0 for r in content_rows)
        tot_eng = sum(r["engagements"] for r in content_rows)
        contracted = round(sum((f["contract_fee"] or 0) for f in fin_rows), 2)
        invoiced = round(sum(f["invoiced"] for f in fin_rows), 2)
        paid = round(sum(f["paid"] for f in fin_rows), 2)
        self.result.totals = {
            "creators": len(self.result.creators),
            "contracts": len(self.result.contracts),
            "invoices": len(self.result.invoices),
            "payouts": len(self.result.payouts),
            "deliverables_required": sum(d["required"] for d in del_rows),
            "deliverables_published": sum(d["published"] for d in del_rows),
            "content_count": len(content_rows),
            "views": sum(r["views"] or 0 for r in content_rows),
            "reach": tot_reach,
            "impressions": sum(r["impressions"] or 0 for r in content_rows),
            "engagements": tot_eng,
            "engagement_rate_pct": (round(tot_eng / tot_reach * 100, 2) if tot_reach else None),
            "contracted_fees": contracted,
            "invoiced": invoiced,
            "paid": paid,
            "outstanding": round(invoiced - paid, 2),
            "open_exceptions": sum(1 for e in ex if e.status == "OPEN"),
        }
        self.result.exceptions = ex
        self.result.steps_done.append(
            f"Reconciliation complete - {len(ex)} exceptions found")
        return self

    def run_full(self, files: list[tuple[str, bytes, str]], roster: list[Creator],
                 campaign: Campaign, sidecars: dict[str, dict] | None = None
                 ) -> PipelineResult:
        self.campaign = campaign
        self.result.campaign = campaign
        self.ingest(files)
        self.normalize_creators(roster)
        self.match_entities()
        self.match_content_rows()
        self.reconcile()
        return self.result


def build_result(files: list[tuple[str, bytes, str]], roster: list[Creator],
                 campaign: Campaign, sidecars: dict[str, dict] | None = None
                 ) -> PipelineResult:
    reset_counter()
    return ReconciliationEngine(campaign).run_full(files, roster, campaign, sidecars)
