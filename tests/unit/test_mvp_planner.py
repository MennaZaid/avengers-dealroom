"""Phase 3 step 2: the MVP planner picks a template by rules and checks every value the model gives."""

import json
import os
from pathlib import Path

from venture_os.agents import build_inputs, mvp_planner, requirements_mapper
from venture_os.decision_log import read_log
from venture_os.onboarding.briefs import ConfirmedBrief

FIX = Path(__file__).parents[1] / "fixtures" / "briefs"


def setup(name):
    inp = build_inputs.collect(ConfirmedBrief.from_file(FIX / name))
    reqs = requirements_mapper.Requirements(brief_id=inp.brief_id, source="rules",
                                            items=requirements_mapper._number(requirements_mapper.from_rules(inp)))
    return inp, reqs


def model(answer):
    return lambda msgs: json.dumps(answer)


def test_template_is_chosen_by_rules():
    assert mvp_planner.choose_template(*setup("nadafa_v1.json")) == "booking"  # cleaner booking app
    assert mvp_planner.choose_template(*setup("pharmastock_v1.json")) == "tracker"  # stock tracking


def test_rules_plan_is_complete_and_in_the_brief_language():
    inp, reqs = setup("nadafa_v1.json")
    plan = mvp_planner.from_rules(inp, reqs, "booking")
    assert plan.lang == "ar" and plan.screens["add"] == "احجز" and len(plan.fields) >= 3
    assert all(s in plan.screens for flow in plan.flows for s in flow)


def test_model_values_are_checked():
    inp, reqs = setup("pharmastock_v1.json")
    plan = mvp_planner.from_model(inp, reqs, "tracker", model({
        "title": "PharmaStock", "tagline": "Never run out of fast-moving medicines", "item_name": "stock entry",
        "fields": [{"label": "Medicine", "type": "text", "required": True, "requirement": "R1"},
                   {"label": "Quantity", "type": "number", "requirement": "R1"},
                   {"label": "Customer card number", "type": "text"},           # forbidden field
                   {"label": "Patient review", "type": "textarea"},             # forbidden field
                   {"label": "Unit", "type": "select", "options": ["box"]},     # select needs 2+ options -> text
                   {"label": "Expiry", "type": "weird", "requirement": "R99"}],  # bad type/requirement
        "screen_requirements": {"home": ["R1", "R42"], "nope": ["R1"]},
        "out_of_scope": ["Ordering from wholesalers"], "assumptions": ["Owners update stock daily"]}))
    labels = [f.label for f in plan.fields]
    assert labels == ["Medicine", "Quantity", "Unit", "Expiry"]
    assert plan.fields[2].type == "text" and plan.fields[3].type == "text" and plan.fields[3].requirement is None
    assert plan.screen_requirements == {"home": ["R1"]} and plan.source == "model"


def test_unusable_model_answer_falls_back_to_rules():
    inp, reqs = setup("pharmastock_v1.json")
    plan = mvp_planner.run(inp, reqs, chat_json=model({"title": "x", "fields": []}), model="qwen3:4b-instruct")
    assert plan.source == "rules" and plan.model is None and plan.template == "tracker"


def test_no_title_with_an_income_promise():
    inp, reqs = setup("pharmastock_v1.json")
    assert mvp_planner.from_model(inp, reqs, "tracker", model({
        "title": "Guaranteed income for pharmacies", "tagline": "you will make 10k a month",
        "fields": [{"label": "A", "type": "text"}, {"label": "B", "type": "text"}]})) is None


def test_validator_feedback_reaches_the_model():
    inp, reqs = setup("pharmastock_v1.json")
    seen = {}

    def spy(msgs):
        seen["user"] = msgs[1]["content"]
        return "{}"

    mvp_planner.run(inp, reqs, chat_json=spy, feedback=["R2 is not covered by any screen"])
    assert "R2 is not covered by any screen" in seen["user"]


def test_run_writes_the_plan_and_a_log_entry():
    inp, reqs = setup("nadafa_v1.json")
    mvp_planner.run(inp, reqs, chat_json=None)
    text = (Path(os.environ["OUTPUTS_DIR"]) / "phase3_step3_mvp_plan.md").read_text(encoding="utf-8")
    assert "Brief id:" in text and "booking" in text and "Fits the founder's constraints" in text
    assert read_log()[-1]["agent"] == "mvp_planner"
