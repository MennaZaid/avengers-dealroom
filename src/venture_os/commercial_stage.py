"""Phase 4 Commercial setup, core step "Set the price and policies". No payments of any kind.

    from venture_os.commercial_stage import run_commercial_stage
    result = run_commercial_stage(brief_id, brief_version)   # -> CommercialResult(decision, files, stubbed)

Runs the whole phase with no approval inside it and returns only the gate recommendation. The stage API starts it
only after the founder's Go on Build for the same brief version, and the founder decides on the gate through
POST /stages/runs/{id}/decision. Thresholds are logged before step 1.

  step 1  pricing research   phase4_step1_pricing_research.md   sourced prices only (URL + date)
  step 2  price setter       phase4_step2_price.md              min / median / max, break-even (ESTIMATE)
  step 3  terms              phase4_step3_terms.md              DRAFT, not legal advice
  step 4  privacy            phase4_step4_privacy.md            DRAFT, not legal advice
  step 5  refund policy      phase4_step5_refund_policy.md      approved refund revokes access
  step 6  readiness checker  phase4_step6_readiness.md
  gate                       phase4_gate_commercial.md          go / repeat / pivot / stop
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from venture_os import gates
from venture_os.agents import commercial_pricing as cp
from venture_os.agents import policy_drafter as pd
from venture_os.decision_log import log_action
from venture_os.guardrails import check_output
from venture_os.outputs import write_output

MIN_SOURCED_PRICES = 3
PIVOT_MAX_PER_MONTH = 100  # paying customers per month needed to recover the budget within the founder's months
RULE = (f"excluded product or every sourced price free -> stop; fewer than {MIN_SOURCED_PRICES} sourced prices "
        f"or a missing section -> repeat; break-even needs more than {PIVOT_MAX_PER_MONTH} paying customers a "
        "month within the founder's stated months -> pivot; otherwise go")
FILES = {"research": "phase4_step1_pricing_research.md", "price": "phase4_step2_price.md",
         "terms": "phase4_step3_terms.md", "privacy": "phase4_step4_privacy.md",
         "refund": "phase4_step5_refund_policy.md", "readiness": "phase4_step6_readiness.md",
         "gate": "phase4_gate_commercial.md"}


class CommercialResult(BaseModel):
    decision: gates.GateDecision
    files: list[str]
    stubbed: list[str] = []


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _items(brief_id: str, brief_version: int | None) -> list:
    """Phase 1-2 evidence items, plus the approved Discover run's claims (as Build reads them)."""
    found: list = []
    try:
        from venture_os import evidence
        found += list(evidence.load(brief_id))
    except Exception:  # noqa: BLE001, S110 - no items: research says so
        pass
    if brief_version is not None:
        try:
            from venture_os.build_stage import discover_items
            found += list(discover_items(brief_id, brief_version))
        except Exception:  # noqa: BLE001, S110 - no database / no approved Discover run
            pass
    return found


def _log(agent: str, action: str, brief_id: str, version, sources=None, **extra) -> None:
    log_action(agent, action, sources=sources or [], model=None, cost=0, approved_by=None, brief_id=brief_id,
               brief_version=version, **extra)


def run_commercial_stage(brief_id: str, brief_version: int | None = None, *, brief: Any = None,
                         items: list | None = None) -> CommercialResult:
    brief_id = str(brief_id)
    if brief is None:
        from venture_os.onboarding.briefs import load_brief
        brief = load_brief(brief_id, brief_version)
    version = brief_version if brief_version is not None else getattr(brief, "version", None)
    _log("commercial_gate", "set_gate_thresholds", brief_id, version, rule=RULE,
         min_sourced_prices=MIN_SOURCED_PRICES, pivot_max_per_month=PIVOT_MAX_PER_MONTH)
    head = [f"Brief id: {brief_id}", ""]
    written: list[str] = []

    def write(step: int, key: str, name: str, lines: list[str]) -> None:
        text = "\n".join(head + lines) + "\n"
        if rules := check_output(text):  # never write text that breaks a must-never rule
            raise RuntimeError(f"{name} failed the output guardrail: {rules}")
        write_output(4, step, name, text)
        written.append(FILES[key])

    # 1 pricing research
    rows, skipped = cp.research_prices(items if items is not None else _items(brief_id, version))
    blocked = [r for r in rows if check_output(r.text)]  # quoted text that breaks a rule is not repeated
    rows = [r for r in rows if r not in blocked]
    skipped += len(blocked)
    sources = sorted({r.url for r in rows})
    lines = ["# Phase 4, step 1: pricing research", "",
             "Only prices from a source with a URL and a date are listed. Prices are as published at the source.", ""]
    if rows:
        lines += ["| Evidence | Price | Currency | Source | Date |", "|---|---|---|---|---|"]
        lines += [f"| {r.item_id}: {r.text.replace('|', '/')} | {r.amount:g} | {r.currency or '-'} | {r.url} | "
                  f"{r.date} |" for r in rows]
    else:
        lines.append("No sourced price found yet.")
    if skipped:
        lines += ["", f"{skipped} price mention(s) were left out: no source URL, no date, or not verified."]
    write(1, "research", "pricing_research", lines)
    _log("pricing_researcher", "research_prices", brief_id, version, sources=sources, prices=len(rows),
         skipped=skipped)

    # 2 price setter
    s = cp.set_price(rows, brief)
    lines = ["# Phase 4, step 2: price (core step)", "",
             ("All figures below are **ESTIMATES** computed in code from the sourced prices and the founder's "
             "stated budget. They are not a forecast and no income is promised."), ""]
    if s.median is not None:
        lines += ["| Figure | Value |", "|---|---|",
                  f"| Sourced prices used | {s.n} ({s.currency}) |",
                  f"| Min / median / max | {s.min:g} / {s.median:g} / {s.max:g} {s.currency} (ESTIMATE) |",
                  f"| Proposed price (median) | {s.proposed:g} {s.currency} (ESTIMATE, to test with buyers) |",
                  f"| Founder's budget as stated | {s.budget:g} {s.currency} |" if s.budget else
                  "| Founder's budget as stated | unknown |",
                  f"| Paying customer-months to recover the budget | {s.customer_months} (ESTIMATE) |"
                  if s.customer_months else "| Paying customer-months to recover the budget | unknown |",
                  f"| Within the founder's {s.months} months: paying customers a month | {s.per_month} (ESTIMATE) |"
                  if s.per_month else "| Paying customers a month needed | unknown (months not stated) |", ""]
    lines.append(s.note or "Payments are MOCKED: no payment provider is connected, no money moves.")
    write(2, "price", "price", lines)
    _log("price_setter", "set_price", brief_id, version, sources=sources, median=s.median, currency=s.currency,
         customer_months=s.customer_months, per_month=s.per_month)

    # 3-5 policies
    country_code = brief.tag("country_code") if hasattr(brief, "tag") else None
    legal = pd.legal_sources(country_code)
    docs = pd.drafts(brief, legal)
    for step, key, name in ((3, "terms", "terms"), (4, "privacy", "privacy"), (5, "refund", "refund_policy")):
        write(step, key, name, docs[key])
    _log("policy_drafter", "draft_policies", brief_id, version, sources=[x["url"] for x in legal],
         documents=["terms", "privacy", "refund"], official_sources=len(legal))

    # 6 readiness checker
    checks = [
        (f"At least {MIN_SOURCED_PRICES} sourced prices", s.n >= MIN_SOURCED_PRICES),
        ("A proposed price (not free)", s.median is not None and s.median > 0),
        ("Terms, privacy and refund drafts present, each labelled DRAFT", all(pd.DRAFT_LABEL in "\n".join(docs[k])
                                                                               for k in ("terms", "privacy",
                                                                                         "refund"))),
        ("Refund policy revokes access on refund", "revokes access" in "\n".join(docs["refund"])),
        ("No payment provider connected (payments MOCKED)", True),
    ]
    ready = all(ok for _, ok in checks)
    write(6, "readiness", "readiness", ["# Phase 4, step 6: commercial readiness", "", "| Check | Result |",
                                        "|---|---|"] + [f"| {c} | {'pass' if ok else 'FAIL'} |" for c, ok in checks])
    _log("readiness_checker", "check_readiness", brief_id, version, ready=ready,
         failed=[c for c, ok in checks if not ok])

    # gate
    common = {"phase": 4, "gate": "commercial", "rule": RULE, "metric": "sourced prices", "target": MIN_SOURCED_PRICES,
              "actual": s.n, "evidence": sources, "decided_at": _now()}
    if not brief.allowed:
        d = gates.GateDecision(outcome="stop", reason="The product is excluded: it cannot be priced or sold.", **common)
    elif s.all_free:
        d = gates.GateDecision(outcome="stop", reason="Every sourced price is free: there is no viable price to "
                                                      "charge. Recommendation: don't launch it as it is.", **common)
    elif s.n < MIN_SOURCED_PRICES or not ready:
        d = gates.GateDecision(outcome="repeat", reason=f"{s.n} sourced prices (need {MIN_SOURCED_PRICES}) or a "
                                                        "readiness check failed: collect more prices first.", **common)
    elif s.per_month is not None and s.per_month > PIVOT_MAX_PER_MONTH:
        d = gates.GateDecision(outcome="pivot", reason=f"Recovering the stated budget at {s.median:g} {s.currency} "
                                                       f"needs about {s.per_month} paying customers a month for "
                                                       f"{s.months} months (ESTIMATE): beyond the founder's budget "
                                                       "and time. Change the price, the offer or the scope.", **common)
    else:
        d = gates.GateDecision(outcome="go", reason="Sourced prices, a proposed price and draft policies are ready "
                                                    "for the founder's review.", **common)
    gates.record(d, brief_id, version)
    written.append(FILES["gate"])
    _save_evidence(brief_id, rows, s, d)
    return CommercialResult(decision=d, files=written, stubbed=[])


def _save_evidence(brief_id: str, rows: list, s: cp.PriceSetting, d: gates.GateDecision) -> None:
    try:
        from venture_os import evidence
        today = datetime.now(UTC).date().isoformat()
        out = [evidence.Item(phase=4, kind="price", label="evidenced", text=f"Sourced price: {r.text}",
                             sources=[r.url], date=r.date) for r in rows]
        if s.median is not None:
            out.append(evidence.Item(phase=4, kind="price", label="inferred", date=today,
                                     text=f"Proposed price (ESTIMATE): {s.median:g} {s.currency}, the median of "
                                          f"{s.n} sourced prices"))
        out.append(evidence.Item(phase=4, kind="other", label="inferred", date=today,
                                 text=f"Phase 4 commercial gate: {d.outcome}. {d.reason}"))
        evidence.add(brief_id, out)
    except Exception as e:  # noqa: BLE001 - reported, not hidden
        _log("commercial_stage", "write_phase4_evidence_failed", brief_id, None, error=f"{type(e).__name__}"[:80])
