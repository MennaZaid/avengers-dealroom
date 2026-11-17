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

Stage pipeline (second half of this file): stage entry checks, stale marking and the Discover evidence gate.
- A stage starts only when the previous stage has a founder `go` (approve) or a recorded waiver FOR THE BRIEF
  VERSION the new run uses. Phase 2 (Validate) therefore refuses to start without a Discover go/waiver.
- The Discover gate's thresholds live in config/gates/discover.yaml and are logged before research starts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from venture_os.agents.schemas import Claim, Competitor, GateResult, IdeaScore
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


def build_gate(can_start: bool, stop_reason: str | None, plan_passed: bool, plan_issues: list[str],
               checks_passed: int, checks_total: int) -> GateDecision:
    """End of Phase 3: the plan must pass validation and the built MVP must pass every test.
    Can't start (excluded product, Phase 2 stop) -> stop; plan or tests still failing after the automatic fix
    rounds -> repeat; everything passes -> go. The founder then approves once for the whole stage."""
    rule = "stage could not start -> stop; plan invalid or any MVP test failing -> repeat; all pass -> go"
    common = {"phase": 3, "gate": "build", "rule": rule, "metric": "MVP tests passed", "target": checks_total,
              "actual": checks_passed, "decided_at": _now()}
    if not can_start:
        return GateDecision(outcome="stop", reason=stop_reason or "The Build stage could not start.", **common)
    if not plan_passed:
        return GateDecision(outcome="repeat", **common,
                            reason="The MVP plan still has problems after the automatic re-plans: "
                                   + "; ".join(plan_issues[:3]))
    if checks_total == 0 or checks_passed < checks_total:
        return GateDecision(outcome="repeat", **common,
                            reason=f"{checks_passed} of {checks_total} MVP tests passed. Fix the failing ones and "
                                   "build again.")
    return GateDecision(outcome="go", **common,
                        reason=f"The plan holds and all {checks_total} MVP tests passed. The founder decides whether "
                               "to move on to Phase 4.")


# ---------------------------------------------------------------- stage pipeline and the Discover gate
STAGES = ("discover", "validate", "build", "commercial", "launch", "operate")
Stage = Literal["discover", "validate", "build", "commercial", "launch", "operate"]
# Founder decisions -> gate outcomes: approve = go, revise = repeat, pivot = pivot (to a named idea or back to
# onboarding), reject = stop, waive = go despite missing interviews (reason required).
Decision = Literal["approve", "revise", "pivot", "reject", "waive"]
RunStatus = Literal["running", "awaiting_approval", "approved", "revision_requested", "pivoted", "rejected", "failed"]
DECISION_STATUS = {"approve": "approved", "revise": "revision_requested", "pivot": "pivoted", "reject": "rejected",
                   "waive": "approved"}
OUTCOME = {"approve": "go", "revise": "repeat", "pivot": "pivot", "reject": "stop", "waive": "go (waiver)"}
DECIDABLE = frozenset({"awaiting_approval", "revision_requested"})
CONFIG = Path(__file__).resolve().parents[2] / "config" / "gates" / "discover.yaml"
INTERVIEW_CHECKS = {"interviews", "interviews_past_behaviour"}


class GateRefused(Exception):
    """The entry check or a decision was refused. The message is shown to the founder."""


@dataclass(frozen=True)
class RunView:
    stage: str
    brief_version: int
    status: str


def previous_stage(stage: str, skip: Iterable[str] = ()) -> str | None:
    """The stage whose approval `stage` needs. Stages in `skip` (not built yet) are passed over, so Build can
    follow an approved Discover while Validate does not exist; the Build report says Phase 2 has not run."""
    if stage not in STAGES:
        raise GateRefused(f"unknown stage {stage!r}")
    skip = set(skip)
    i = STAGES.index(stage) - 1
    while i >= 0 and STAGES[i] in skip:
        i -= 1
    return STAGES[i] if i >= 0 else None


def entry_check(stage: str, latest_version: int | None, runs: Iterable[RunView], skip: Iterable[str] = ()) -> None:
    """Raise GateRefused unless `stage` may start on the brief's latest version."""
    prev = previous_stage(stage, skip)
    if not latest_version:
        raise GateRefused("the brief has no confirmed version yet: confirm it in onboarding first")
    if prev is None:
        return
    approved = [r for r in runs if r.stage == prev and r.status == "approved"]
    if any(r.brief_version == latest_version for r in approved):
        return
    if approved:
        old = ", ".join(sorted({f"v{r.brief_version}" for r in approved}))
        raise GateRefused(f"{prev} was approved for brief {old}, but the brief is now v{latest_version}: "
                          f"run and approve {prev} again for v{latest_version}")
    raise GateRefused(f"{stage} needs a founder go (or waiver) on {prev} for brief v{latest_version}")


def is_stale(run_version: int, latest_version: int | None) -> bool:
    return latest_version is not None and latest_version > run_version


def apply_decision(status: str, decision: str) -> str:
    if decision not in DECISION_STATUS:
        raise GateRefused(f"unknown decision {decision!r}")
    if status not in DECIDABLE:
        raise GateRefused(f"this run is {status}; a decision is not possible")
    return DECISION_STATUS[decision]


# ---------- Discover gate ----------

def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _domain(url: str | None) -> str:
    return re.sub(r"^https?://(www\.)?([^/]+).*", r"\2", url or "")


def _idea_passes(score: IdeaScore, cfg: dict) -> tuple[bool, list[str]]:
    t = cfg["thresholds"]
    why = []
    if score.total < t["top_idea_score"]:
        why.append(f"score {score.total} < {t['top_idea_score']}")
    for c in score.criteria:
        if c.criterion in cfg["scoring"]["fit_criteria"] and c.score < t["fit_criterion_min"]:
            why.append(f"{c.criterion} {c.score} < {t['fit_criterion_min']}")
    return not why, why


def evaluate_discover(product_group: str, product_label: str, claims: list[Claim], competitors: list[Competitor],
                      scores: list[IdeaScore], interviews: list[dict], cfg: dict | None = None) -> GateResult:
    """interviews: [{"counts": bool, "past_behaviour": bool, "describes_problem": bool}] from founder notes."""
    cfg = cfg or load_config()
    t, stop = cfg["thresholds"], cfg["stop_rules"]
    pain = [c for c in claims if c.type == "fact" and c.topic in ("pain", "customer_pain") and "stale" not in c.flags
            and "quote_not_found" not in c.flags]
    domains = {_domain(c.url) for c in pain}
    paid = [c for c in competitors if c.price_claim_id and c.pricing_model not in ("free", None, "unknown")]
    free = [c for c in competitors if c.pricing_model == "free"]
    by_id = {s.idea_id: s for s in scores}
    top = max(scores, key=lambda s: s.total) if scores else None
    top_ok, _top_why = _idea_passes(top, cfg) if top else (False, ["no idea scored"])
    n_int = len(interviews)
    n_past = sum(1 for i in interviews if i.get("past_behaviour") and i.get("describes_problem", True))
    checks = [
        {"check": "product_type", "target": "digital, not excluded", "actual": product_label,
         "passed": product_group == "digital_product"},
        {"check": "problem_fact_claims", "target": f">= {t['problem_fact_claims']}", "actual": len(pain),
         "passed": len(pain) >= t["problem_fact_claims"]},
        {"check": "problem_source_domains", "target": f">= {t['problem_source_domains']}", "actual": len(domains),
         "passed": len(domains) >= t["problem_source_domains"]},
        {"check": "priced_competitors", "target": f">= {t['priced_competitors']} with a sourced paid price",
         "actual": len(paid), "passed": len(paid) >= t["priced_competitors"]},
        {"check": "top_idea", "target": f"score >= {t['top_idea_score']}, every fit >= {t['fit_criterion_min']}",
         "actual": f"{top.idea_id} {top.total}" if top else "none", "passed": top_ok},
        {"check": "interviews", "target": f">= {t['interviews']} founder-entered", "actual": n_int,
         "passed": n_int >= t["interviews"]},
        {"check": "interviews_past_behaviour", "target": f">= {t['interviews_past_behaviour']} past behaviour",
         "actual": n_past, "passed": n_past >= t["interviews_past_behaviour"]},
    ]
    reasons, collect, pivot_to = [], [], None
    if not competitors:
        reasons.append("warning: 0 competitors or substitutes found - not a pass (people may not pay for this, "
                       "or the search missed them)")

    def fit_fails(s: IdeaScore) -> bool:
        return any(c.criterion in ("budget_fit", "time_fit") and c.score < t["fit_criterion_min"]
                   for c in s.criteria)
    start = by_id.get("I0")
    alternatives = [s for s in scores if s.idea_id != "I0"]

    if product_group == "excluded":
        outcome = "stop"
        reasons.insert(0, f"excluded product ({product_label}): this system only builds digital products")
    elif len(pain) < stop["min_problem_claims_to_continue"]:
        outcome = "stop"
        reasons.insert(0, "no sourced evidence that anyone has this problem: don't build on assumptions")
    elif scores and all(fit_fails(s) for s in scores):
        outcome = "stop"
        reasons.insert(0, "founder fit fails: no idea can be built within the stated budget and time")
    elif len(free) >= stop["saturated_competitors"] and top and next(
            (c.score for c in top.criteria if c.criterion == "competition"), 5) <= 1.5:
        outcome = "stop"
        reasons.insert(0, f"saturated: {len(free)} free alternatives and nothing that differentiates")
    else:
        start_ok = _idea_passes(start, cfg)[0] if start else False
        passing_alt = next((s for s in sorted(alternatives, key=lambda s: -s.total) if _idea_passes(s, cfg)[0]),
                           None)
        if not start_ok and passing_alt:
            outcome, pivot_to = "pivot", passing_alt.idea_id
            reasons.insert(0, f"the starting idea fails ({', '.join(_idea_passes(start, cfg)[1]) if start else 'not scored'})"
                              f" but alternative {passing_alt.idea_id} passes (score {passing_alt.total})")
        elif all(c["passed"] for c in checks):
            outcome = "go"
            reasons.insert(0, "every threshold set before the run passed")
        else:
            outcome = "repeat"
    failed = [c for c in checks if not c["passed"]]
    hints = {"product_type": "answer the clarifying question about the product type",
             "problem_fact_claims": "more quotes from people describing the problem (forums, reviews, Q&A)",
             "problem_source_domains": "quotes from more different sites",
             "priced_competitors": "competitors' published prices (pricing pages, store listings)",
             "top_idea": "a stronger idea, or more evidence for the scores marked ASSUMPTION",
             "interviews": f"{max(0, t['interviews'] - n_int)} more Mom Test interviews entered by the founder",
             "interviews_past_behaviour": "interviews where the person describes the problem from a real past event"}
    collect = [f"{c['check']}: {hints[c['check']]} (now {c['actual']}, target {c['target']})" for c in failed]
    if outcome == "repeat":
        reasons.insert(0, "evidence is thin but not negative: collect what is listed, then run again")
    return GateResult(recommendation=outcome, reasons=reasons, checks=checks, thresholds=t, pivot_to=pivot_to,
                      collect_next=collect)


def can_waive(gate: dict) -> tuple[bool, str]:
    """The founder may waive only a `repeat` whose only failing checks are the interview checks."""
    if gate.get("recommendation") != "repeat":
        return False, "a waiver only applies to a 'repeat' recommendation"
    failing = {c["check"] for c in gate.get("checks", []) if not c["passed"]}
    if not failing or not failing <= INTERVIEW_CHECKS:
        return False, f"other checks fail too ({', '.join(sorted(failing - INTERVIEW_CHECKS))}): no waiver"
    return True, ""
