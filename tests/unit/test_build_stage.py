"""Phase 3 end to end: no founder approval inside the stage, automatic fix rounds, one gate at the end."""

import json
import os
from pathlib import Path

from venture_os import gates
from venture_os.agents import docs_writer
from venture_os.build_stage import run_build_stage
from venture_os.decision_log import read_log
from venture_os.onboarding.briefs import ConfirmedBrief

FIX = Path(__file__).parents[1] / "fixtures" / "briefs"
OUT = lambda: Path(os.environ["OUTPUTS_DIR"])

STAGE_FILES = ["phase3_step1_build_inputs.md", "phase3_step2_requirements.md", "phase3_step3_mvp_plan.md",
               "phase3_step4_validation.md", "phase3_step5_mvp.html", "phase3_step6_test_report.md",
               "phase3_step7_user_guide.md", "phase3_step8_evidence_summary.md", "phase3_gate_build.md"]


def brief(name="pharmastock_v1.json", **over):
    b = ConfirmedBrief.from_file(FIX / name)
    return b.model_copy(update=over) if over else b


def test_full_stage_without_a_model_ends_in_go():
    b = brief()
    r = run_build_stage(b, use_browser=False)
    assert r.decision.outcome == "go" and r.template == "tracker" and r.plan_rounds == 1 and r.test_attempts == 1
    for f in STAGE_FILES:
        assert b.brief_id in (OUT() / f).read_text(encoding="utf-8"), f
    actions = [e["action"] for e in read_log()]
    assert actions == ["collect_build_inputs", "map_evidence_to_requirements", "spec_product", "plan_mvp", "validate_mvp_plan",
                       "build_mvp", "test_mvp", "write_mvp_docs", "build_gate", "run_build_stage"]
    assert all(e["approved_by"] is None for e in read_log())  # nobody approves inside the stage


def test_arabic_brief_gets_an_arabic_guide_and_rtl_app():
    run_build_stage(brief("nadafa_v1.json"), use_browser=False)
    assert "دليل المستخدم" in (OUT() / "phase3_step7_user_guide.md").read_text(encoding="utf-8")
    assert 'dir="rtl"' in (OUT() / "phase3_step5_mvp.html").read_text(encoding="utf-8")


def test_a_plan_that_keeps_failing_is_replanned_then_falls_back_to_the_fixed_plan():
    calls = {"plan": 0}

    def stubborn_model(msgs):
        sys_prompt = msgs[0]["content"]
        if "smallest digital product (an MVP)" in sys_prompt:  # the planner prompt
            calls["plan"] += 1
            return json.dumps({"title": "The best certified app", "tagline": "x", "fields": [
                {"label": "Item", "type": "text"}, {"label": "Qty", "type": "number"}]})
        return "{}"

    r = run_build_stage(brief(), chat_json=stubborn_model, model="fake", use_browser=False)
    assert calls["plan"] == 3  # first plan + 2 re-plans, each with the validator's feedback
    assert r.plan_rounds == 4 and r.decision.outcome == "go"  # the fixed plan passes
    assert [e.get("revision") for e in read_log() if e["action"] == "plan_mvp"] == [False, True, True, True]


def test_unsafe_model_copy_is_rebuilt_with_fixed_text():
    def model(msgs):
        if "short help text" in msgs[0]["content"]:
            return json.dumps({"help": {"home": "Guaranteed income for every pharmacy!"}})
        return "{}"

    # check_output() drops the bad line already in the builder, so the first test passes;
    r = run_build_stage(brief(), chat_json=model, model="fake", use_browser=False)
    assert r.test_attempts == 1 and r.decision.outcome == "go"
    assert "Guaranteed" not in (OUT() / "phase3_step5_mvp.html").read_text(encoding="utf-8")


def test_phase2_stop_stops_the_build_stage():
    b = brief()
    gates.record(gates.demand_gate(gates.plan_demand_test(100, 14), actual=12, days_elapsed=14), brief_id=b.brief_id)
    r = run_build_stage(b, use_browser=False)
    assert r.decision.outcome == "stop" and "demand" in r.decision.reason
    assert not (OUT() / "phase3_step5_mvp.html").exists()  # nothing was built


def test_excluded_product_stops():
    r = run_build_stage(brief(product_check={"status": "excluded", "categories": ["physical_goods"]}),
                        use_browser=False)
    assert r.decision.outcome == "stop"


def test_build_gate_rules():
    assert gates.build_gate(True, None, True, [], 15, 15).outcome == "go"
    assert gates.build_gate(True, None, True, [], 14, 15).outcome == "repeat"
    assert gates.build_gate(True, None, False, ["R1 not covered"], 15, 15).outcome == "repeat"
    assert gates.build_gate(False, "excluded", True, [], 0, 0).outcome == "stop"


def test_evidence_summary_never_claims_evidence_that_is_not_there():
    run_build_stage(brief(), use_browser=False)
    text = (OUT() / "phase3_step8_evidence_summary.md").read_text(encoding="utf-8")
    assert "None yet: no Phase 1-2 findings were available." in text and "To test with real users next" in text
    assert docs_writer.AGENT == "docs_writer"
