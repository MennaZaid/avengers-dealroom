"""Gates: every step ends with one. Plain code, not a prompt.

A gate compares evidence with a rule that was fixed **before** the result was known and recommends one of:
go (continue), repeat (run the step again), pivot (go back and change the idea), stop (don't launch this).
The founder makes the final call through approval.py; a gate never approves anything by itself.

    from venture_os import gates
    gates.record(gates.product_gate(brief), brief_id)                     # before Discover
    gates.record(gates.evidence_gate(1, sources=urls, assumptions=3), brief_id)
    test = gates.plan_demand_test(target=100, days=14)                     # fixed BEFORE measuring
    gates.record(gates.demand_gate(test, actual=12, days_elapsed=14, source="founder"), brief_id)  # -> stop

record() writes outputs/phase<N>_gate_<name>.md (with the brief id) and a decision_log.json entry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from venture_os.decision_log import log_action
from venture_os.outputs import write_output

Outcome = Literal["go", "repeat", "pivot", "stop"]

# Fixed rules. Changing them is a code change (reviewed, in git), never an adjustment after seeing a result.
MIN_SOURCED_CLAIMS = 5
DEMAND_RULE = ((1.0, "go"), (0.5, "repeat"), (0.25, "pivot"))  # share of target reached -> outcome; else stop
DEMAND_RULE_TEXT = "target reached -> go; >= 50% -> repeat; >= 25% -> pivot; below 25% -> stop"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class GateDecision(BaseModel):
    """A gate's recommendation, with everything needed to check it later."""

    phase: int
    gate: str  # short name used in the output file: product, evidence, demand
    outcome: Outcome
    reason: str
    rule: str  # the fixed rule the outcome came from
    metric: str | None = None
    target: float | None = None
    actual: float | None = None
    evidence: list[str] = []  # source URLs the decision rests on
    mocked: bool = False  # True when the measured value is demo data, not real
    decided_at: str = ""


class DemandTest(BaseModel):
    """A demand test declared before it runs. Frozen: the target cannot be changed afterwards."""

    model_config = ConfigDict(frozen=True)

    metric: str
    target: int
    days: int
    declared_at: str


def plan_demand_test(target: int, days: int, metric: str = "waitlist sign-ups") -> DemandTest:
    """Declare the target and the time window before measuring anything."""
    if target <= 0 or days <= 0:
        raise ValueError("target and days must be positive")
    return DemandTest(metric=metric, target=target, days=days, declared_at=_now())


def product_gate(brief) -> GateDecision:
    """Before Discover: an excluded product (physical goods, financial/crypto, health or legal advice) stops here.
    `brief` is a ConfirmedBrief (onboarding/briefs.py)."""
    check = brief.product_check or {}
    status = check.get("status", "allowed")
    rule = "excluded product -> stop; otherwise go (borderline ideas go with conditions)"
    if status == "excluded":
        cats = ", ".join(check.get("categories", [])) or "excluded category"
        return GateDecision(phase=1, gate="product", outcome="stop", rule=rule, decided_at=_now(),
                            reason=f"The product is not allowed ({cats}). Only digital products are supported.")
    reason = ("Digital product: allowed." if status != "review" else
              "Allowed only if the product stays digital and gives no medical, legal or financial advice "
              f"(flagged: {', '.join(check.get('categories', []))}).")
    return GateDecision(phase=1, gate="product", outcome="go", rule=rule, reason=reason, decided_at=_now())


def evidence_gate(phase: int, sources: list[str], assumptions: int = 0,
                  min_sourced: int = MIN_SOURCED_CLAIMS) -> GateDecision:
    """After research: enough claims with a real source URL? `sources` = one URL per sourced claim.
    No sourced claim at all -> stop; fewer than `min_sourced` -> repeat; otherwise go."""
    sourced = len([u for u in sources if isinstance(u, str) and u.startswith(("http://", "https://"))])
    rule = f"0 sourced claims -> stop; fewer than {min_sourced} -> repeat; otherwise go"
    common = {"phase": phase, "gate": "evidence", "rule": rule, "metric": "sourced claims", "target": min_sourced,
                  "actual": sourced, "evidence": sorted(set(sources)), "decided_at": _now()}
    if sourced == 0:
        return GateDecision(outcome="stop", **common,
                            reason=f"No claim has a source; {assumptions} are assumptions. There is no evidence "
                                   "to continue on.")
    if sourced < min_sourced:
        return GateDecision(outcome="repeat", **common,
                            reason=f"Only {sourced} sourced claims (need {min_sourced}); {assumptions} assumptions. "
                                   "Research again before deciding.")
    return GateDecision(outcome="go", **common,
                        reason=f"{sourced} sourced claims; {assumptions} assumptions are labelled as such.")


def demand_gate(test: DemandTest, actual: int, days_elapsed: int,
                source: Literal["founder", "mocked"] = "founder") -> GateDecision:
    """After a demand test (e.g. a landing-page waitlist). The target comes from the test declared beforehand.
    `actual` is entered by the founder, or labelled mocked in a demo; it is never generated."""
    if source not in ("founder", "mocked"):
        raise ValueError('actual must come from the founder or be labelled "mocked"')
    if actual < 0 or days_elapsed < 0:
        raise ValueError("actual and days_elapsed cannot be negative")
    share = actual / test.target
    common = {"phase": 2, "gate": "demand", "rule": f"{DEMAND_RULE_TEXT} (declared {test.declared_at})",
                  "metric": test.metric, "target": test.target, "actual": actual, "mocked": source == "mocked",
                  "decided_at": _now()}
    if days_elapsed < test.days and share < 1.0:
        return GateDecision(outcome="repeat", **common,
                            reason=f"The test is still running (day {days_elapsed} of {test.days}): "
                                   f"{actual} of {test.target} so far. Decide after day {test.days}.")
    outcome: Outcome = next((o for limit, o in DEMAND_RULE if share >= limit), "stop")
    pct = round(share * 100)
    reasons = {
        "go": f"{actual} {test.metric} in {days_elapsed} days, target {test.target}: target reached ({pct}%).",
        "repeat": f"{actual} of {test.target} ({pct}%): some demand, below target. Improve the offer and run the "
                  "test again.",
        "pivot": f"{actual} of {test.target} ({pct}%): weak demand. Go back and change the customer, problem or "
                 "offer.",
        "stop": f"{actual} of {test.target} ({pct}%) in {days_elapsed} days: the evidence does not support "
                "launching this idea. Recommendation: don't launch it as it is.",
    }
    return GateDecision(outcome=outcome, reason=reasons[outcome], **common)


_OUTCOME_TEXT = {"go": "GO: continue", "repeat": "REPEAT: run this step again", "pivot": "PIVOT: go back and change",
                 "stop": "STOP: don't launch this"}


def to_markdown(d: GateDecision, brief_id: str | None = None) -> str:
    lines = [f"# Phase {d.phase} gate: {d.gate}", ""]
    if brief_id:
        lines += [f"Brief id: `{brief_id}`", ""]
    lines += [f"**Recommendation:** {_OUTCOME_TEXT[d.outcome]}", "", f"**Why:** {d.reason}", "",
              f"**Rule (fixed before the result):** {d.rule}", ""]
    if d.metric:
        lines += ["| Metric | Target | Actual |", "|---|---|---|",
                  f"| {d.metric} | {d.target:g} | {d.actual:g}{' (MOCKED demo data)' if d.mocked else ''} |", ""]
    if d.evidence:
        lines += ["**Evidence:**", ""] + [f"- {u}" for u in d.evidence] + [""]
    lines += [(f"Decided at {d.decided_at}. This is a recommendation: the founder approves, repeats, pivots or stops "
              "in the app, and that decision is logged separately.")]
    return "\n".join(lines) + "\n"


def record(d: GateDecision, brief_id: str | None = None, brief_version: int | None = None) -> GateDecision:
    """Write outputs/phase<N>_gate_<gate>.md and a decision_log.json entry. Returns the decision."""
    write_output(d.phase, None, d.gate, to_markdown(d, brief_id), gate=True)
    extra = {k: v for k, v in (("brief_id", brief_id), ("brief_version", brief_version)) if v is not None}
    log_action("gate", f"{d.gate}_gate", sources=d.evidence, model=None, cost=0, approved_by=None,
               outcome=d.outcome, phase=d.phase, metric=d.metric, target=d.target, actual=d.actual,
               mocked=d.mocked, **extra)
    return d
