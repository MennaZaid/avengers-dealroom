"""Phase 4 Commercial setup, core step "Set the price and policies": price hypotheses (STUBBED).

Each price point is the founder's stated price (FOUNDER), a competitor price from a Phase 1 evidence item with
its source URL and date (EVIDENCED), or ASSUMPTION. No income or revenue forecast is made. No payments of any kind.
-> outputs/phase4_step1_pricing.md, then the phase 4 pricing gate (recommends only).
"""

from __future__ import annotations

from typing import Any

from venture_os.agents import stubbed
from venture_os.agents.business_designer import _index_evidence, _is_evidenced, _load_evidence

PRICE_KINDS = {"price", "competitor_price"}


def run(brief_id: str, *, brief: Any = None, evidence_items: list | None = None):
    if brief is None:
        from venture_os.onboarding.briefs import load_brief
        brief = load_brief(brief_id)
    notes = []
    if evidence_items is None:
        evidence_items, note = _load_evidence(brief_id)
        if note:
            notes.append(note)
    ev = _index_evidence(evidence_items)

    rows = []  # (hypothesis, price, basis, source)
    stated = brief.known("business_model")
    rows.append(("H1: the founder's stated model", stated or "unknown", "FOUNDER" if stated else "UNKNOWN",
                 "brief field `business_model`"))
    sources = []
    for eid, item in ev.items():
        if item["kind"] not in PRICE_KINDS:
            continue
        if _is_evidenced(item):
            rows.append((f"Reference: {item['text']}", "as published at the source", "EVIDENCED",
                         f"{eid}: {item['url']} ({item['date']})"))
            sources.append(item["url"])
        else:
            rows.append((f"Reference: {item['text']}", "not verified", "ASSUMPTION", f"{eid}: no source URL/date"))
    rows.append(("H2: free pilot for the first waitlist users, then the stated model", "0 during the pilot",
                 "ASSUMPTION", "to test willingness to pay; not tested yet"))
    if not sources:
        notes.append("No competitor price has a source yet: Phase 1 should collect them (labelled ASSUMPTION).")

    md = stubbed.header(brief_id, "Phase 4, step 1: price hypotheses")
    md += ["| Hypothesis | Price | Basis | Source |", "|---|---|---|---|"]
    md += [f"| {stubbed.cell(h)} | {stubbed.cell(p)} | {b} | {stubbed.cell(s)} |" for h, p, b, s in rows]
    md += ["", ("These are hypotheses to test with real buyers, not forecasts. No income or sales figure is "
           "estimated. Payments are MOCKED (see payments.py); no payment provider is connected."), ""]
    md += [f"- {stubbed.cell(n)}" for n in notes]
    stubbed.write_checked(4, 1, "pricing", "\n".join(md) + "\n")
    stubbed.log_step("pricing", "price_hypotheses", brief_id, sources=sources, hypotheses=len(rows))

    if not brief.allowed:
        outcome, reason = "stop", "The product is excluded, so it cannot be priced or sold."
    elif stated or sources:
        outcome, reason = "go", "At least one price point comes from the founder or a sourced competitor price."
    else:
        outcome, reason = "repeat", "No stated price and no sourced competitor price: collect them first."
    return stubbed.record_gate(4, "pricing", outcome, reason,
                               "excluded -> stop; a founder or sourced price -> go; otherwise repeat",
                               brief_id, sources)
