"""The Discover gate (plain code): thresholds logged before research; go / repeat / pivot / stop on fixtures;
Phase 2 refused without a founder go or waiver; a model cannot write an approval."""

import json
import os
from pathlib import Path

import pytest
from discover_fakes import FakeStoreWithInterviews, FakeToolboxWithApis

from venture_os import approval
from venture_os.agents.research_planner import build_plan
from venture_os.agents.schemas import Claim, Competitor, CriterionScore, IdeaScore
from venture_os.gates import GateRefused, RunView, can_waive, entry_check, evaluate_discover, load_config
from venture_os.orchestrator import run_discover

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"
FITS = ("skill_fit", "budget_fit", "time_fit", "values_fit")


def pain(n: int, domains: int) -> list[Claim]:
    return [Claim(id=f"C{i}", type="fact", topic="pain", text="q", quote="I lost a client last month",
                  url=f"https://site{i % domains}.example.org/p{i}", retrieved_at="2026-11-17T00:00:00")
            for i in range(n)]


def comps(paid: int, free: int = 0) -> list[Competitor]:
    return ([Competitor(name=f"P{i}", url=f"https://p{i}.example.org", price="$9", pricing_model="paid",
                        price_claim_id=f"X{i}") for i in range(paid)] +
            [Competitor(name=f"F{i}", url=f"https://f{i}.example.org", price="Free", pricing_model="free",
                        price_claim_id=f"Y{i}") for i in range(free)])


def score(idea_id: str, total: float, fit: float = 4, competition: float = 3) -> IdeaScore:
    crit = [CriterionScore(criterion=c, score=fit) for c in FITS]
    crit.append(CriterionScore(criterion="competition", score=competition))
    return IdeaScore(idea_id=idea_id, criteria=crit, total=total, proposed_by="rules")


def interviews(n: int, past: int) -> list[dict]:
    return [{"counts": True, "past_behaviour": i < past, "describes_problem": True} for i in range(n)]


def gate(**kw):
    args = {"product_group": "digital_product", "product_label": "saas", "claims": pain(6, 3),
            "competitors": comps(2), "scores": [score("I0", 3.6)], "interviews": interviews(5, 3)}
    args.update(kw)
    return evaluate_discover(**args)


def test_strong_evidence_gives_go():
    g = gate()
    assert g.recommendation == "go" and all(c["passed"] for c in g.checks)


def test_thin_evidence_gives_repeat_and_says_what_to_collect():
    g = gate(claims=pain(3, 2), interviews=[])
    assert g.recommendation == "repeat"
    assert any("interviews" in x for x in g.collect_next) and any("problem_fact_claims" in x for x in g.collect_next)


def test_alternative_that_passes_gives_pivot_to_it():
    g = gate(scores=[score("I0", 2.4, fit=1), score("I1", 3.4), score("I2", 2.0)])
    assert g.recommendation == "pivot" and g.pivot_to == "I1"


def test_weak_evidence_gives_stop():
    assert gate(claims=[], competitors=[]).recommendation == "stop"  # no sourced pain at all
    assert gate(product_group="excluded", product_label="physical_goods").recommendation == "stop"
    no_fit = [score("I0", 3.5, fit=1), score("I1", 3.2, fit=1)]  # nothing buildable in the budget/time
    assert gate(scores=no_fit).recommendation == "stop"
    saturated = gate(competitors=comps(0, free=9), scores=[score("I0", 3.2, competition=1)])
    assert saturated.recommendation == "stop" and "saturated" in saturated.reasons[0]


def test_zero_competitors_is_a_warning_not_a_pass():
    g = gate(competitors=[])
    assert g.recommendation != "go" and any("0 competitors" in r for r in g.reasons)


def test_thresholds_come_from_config_written_in_advance():
    cfg = load_config()
    g = gate()
    assert g.thresholds == cfg["thresholds"]
    assert cfg["thresholds"]["interviews"] == 5 and cfg["thresholds"]["problem_source_domains"] == 3


def test_thresholds_are_logged_before_any_research():
    brief = json.loads((FIX / "nadafa_v1.json").read_text(encoding="utf-8"))
    run_discover("run-g", build_plan(brief, []), brief, FakeToolboxWithApis(), FakeStoreWithInterviews())
    log = json.loads(Path(os.environ["DECISION_LOG_PATH"]).read_text(encoding="utf-8"))
    actions = [e["action"] for e in log]
    first_research = min(i for i, a in enumerate(actions) if a in ("search", "api_call", "fetch", "registry_source"))
    assert actions[0] == "set_gate_thresholds" and actions.index("set_gate_thresholds") < first_research
    assert log[0]["thresholds"]["problem_fact_claims"] == 5


def test_weak_brief_run_recommends_stop():
    brief = json.loads((FIX / "nadafa_v1.json").read_text(encoding="utf-8"))
    out = run_discover("run-w", build_plan(brief, []), brief, FakeToolboxWithApis(weak=True),
                       FakeStoreWithInterviews())
    assert out["research"]["gate"]["recommendation"] == "stop"


def test_phase_2_refused_without_a_founder_go_or_waiver():
    with pytest.raises(GateRefused, match="founder go"):
        entry_check("validate", 1, [RunView("discover", 1, "awaiting_approval")])
    with pytest.raises(GateRefused):
        entry_check("validate", 1, [RunView("discover", 1, "revision_requested")])
    entry_check("validate", 1, [RunView("discover", 1, "approved")])  # go or waive both set "approved"


def test_the_model_cannot_write_an_approval():
    run = {"id": "r", "status": "awaiting_approval", "stage": "discover", "brief_version": 1, "output": {}}
    for actor in ("model", "opportunity_finder", "research_critic", ""):
        with pytest.raises(PermissionError):
            approval.record_decision(None, run, "approve", "", actor=actor)


def test_waiver_only_for_missing_interviews():
    only_interviews = gate(interviews=[]).model_dump()
    assert only_interviews["recommendation"] == "repeat" and can_waive(only_interviews)[0]
    more_missing = gate(interviews=[], claims=pain(2, 1)).model_dump()
    assert not can_waive(more_missing)[0]
    assert not can_waive(gate().model_dump())[0]  # nothing to waive on a go
