"""Phase 3 step 3: the validator's fixed rules decide; the model review only adds warnings."""

import json
import os
from pathlib import Path

from venture_os.agents import build_inputs, mvp_planner, mvp_validator, requirements_mapper
from venture_os.agents.mvp_planner import Field
from venture_os.decision_log import read_log
from venture_os.onboarding.briefs import ConfirmedBrief

FIX = Path(__file__).parents[1] / "fixtures" / "briefs"


def setup(name="pharmastock_v1.json"):
    inp = build_inputs.collect(ConfirmedBrief.from_file(FIX / name))
    reqs = requirements_mapper.Requirements(brief_id=inp.brief_id, source="rules",
                                            items=requirements_mapper._number(requirements_mapper.from_rules(inp)))
    plan = mvp_planner.from_rules(inp, reqs, mvp_planner.choose_template(inp, reqs))
    return inp, reqs, plan


def test_rules_plan_passes():
    inp, reqs, plan = setup()
    issues, _warnings, trace = mvp_validator.check(inp, reqs, plan)
    assert issues == [] and trace and all(t.rests_on in ("FOUNDER-STATED", "INFERRED", "ASSUMPTION") for t in trace)


def test_uncovered_must_requirement_blocks():
    inp, reqs, plan = setup()
    plan = plan.model_copy(update={"screen_requirements": {},
                                   "fields": [f.model_copy(update={"requirement": None}) for f in plan.fields]})
    issues, _, _ = mvp_validator.check(inp, reqs, plan)
    assert any("(must) is not covered" in i for i in issues)


def test_unreachable_screen_and_missing_form_block():
    inp, reqs, plan = setup()
    bad = plan.model_copy(update={"screens": {"home": "Home", "orphan": "Orphan"}, "flows": [["home"]]})
    issues, _, _ = mvp_validator.check(inp, reqs, bad)
    assert any("not reachable" in i for i in issues) and any("main form" in i for i in issues)


def test_unchecked_quality_claims_block():
    inp, reqs, plan = setup("nadafa_v1.json")
    fields = plan.fields + [Field(id="f9", label="مقدمو الخدمة", type="select", options=["مُنظف مُعتمد", "مُنظف سريع"])]
    issues, _, _ = mvp_validator.check(inp, reqs, plan.model_copy(update={"fields": fields,
                                                                         "title": "Certified cleaners"}))
    assert any("certified" in i.lower() for i in issues) and any("معتمد" in i for i in issues)


def test_forbidden_field_and_payment_label():
    inp, reqs, plan = setup()
    fields = plan.fields[:3] + [Field(id="f8", label="Card number", type="text"),
                                Field(id="f9", label="Price", type="number")]
    issues, warnings, _ = mvp_validator.check(inp, reqs, plan.model_copy(update={"fields": fields}))
    assert any("must not collect" in i for i in issues) and any("MOCKED" in w for w in warnings)


def test_untraced_field_is_an_assumption_warning_not_a_block():
    inp, reqs, plan = setup()
    fields = plan.fields + [Field(id="f9", label="Shelf", type="text")]
    issues, warnings, trace = mvp_validator.check(inp, reqs, plan.model_copy(update={"fields": fields}))
    assert not issues and any("Shelf" in w and "ASSUMPTION" in w for w in warnings)
    assert any(t.element == "field: Shelf" and t.rests_on == "ASSUMPTION" for t in trace)


def test_model_review_only_adds_warnings():
    inp, reqs, plan = setup()
    rep = mvp_validator.run(inp, reqs, plan, chat_json=lambda m: json.dumps(
        {"problems": ["Sync contradicts offline use"]}), model="qwen3:4b-instruct")
    assert rep.passed and any("Model review: Sync" in w for w in rep.warnings) and rep.model_review


def test_run_writes_the_report_and_logs_pass_or_fail():
    inp, reqs, plan = setup()
    bad = plan.model_copy(update={"title": "The best stock app, guaranteed"})
    rep = mvp_validator.run(inp, reqs, bad, round_no=2)
    assert not rep.passed
    text = (Path(os.environ["OUTPUTS_DIR"]) / "phase3_step4_validation.md").read_text(encoding="utf-8")
    assert "FAILED (round 2)" in text and "Traceability" in text and "Brief id:" in text
    e = read_log()[-1]
    assert e["agent"] == "mvp_validator" and e["outcome"] == "fail" and e["round"] == 2
