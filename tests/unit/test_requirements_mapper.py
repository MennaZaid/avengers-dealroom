"""Phase 3 step 1: requirements rest on cited inputs; code sets labels and caps priority."""

import json
import os
from pathlib import Path

from venture_os import evidence
from venture_os.agents import build_inputs, requirements_mapper
from venture_os.decision_log import read_log
from venture_os.onboarding.briefs import ConfirmedBrief

FIX = Path(__file__).parents[1] / "fixtures" / "briefs"


def inputs(name="nadafa_v1.json", with_phase1=False):
    b = ConfirmedBrief.from_file(FIX / name)
    if with_phase1:
        evidence.add(b.brief_id, [evidence.Item(phase=1, kind="pain", text="Working families distrust informal cleaners",
                                                label="evidenced", sources=["https://example.org/survey"])])
    return build_inputs.collect(b)


def model(reqs):
    return lambda msgs: json.dumps({"requirements": reqs})


def test_label_comes_from_the_strongest_cited_input():
    inp = inputs(with_phase1=True)
    out = requirements_mapper.from_model(inp, model([
        {"statement": "Book a vetted cleaner", "type": "feature", "priority": "must", "evidence": ["E1", "B1"]},
        {"statement": "Show cleaner profiles", "type": "feature", "priority": "must", "evidence": ["B1"]},
    ]))
    assert out[0].label == "evidenced" and out[1].label == "founder_stated"


def test_priority_is_capped_by_evidence_strength():
    inp = inputs()
    out = requirements_mapper.from_model(inp, model([
        {"statement": "Loyalty points", "type": "feature", "priority": "must", "evidence": []},
    ]))
    assert out[0].label == "assumption" and out[0].priority == "could" and out[0].capped


def test_unknown_ids_are_dropped():
    out = requirements_mapper.from_model(inputs(), model([
        {"statement": "Chat with cleaners", "type": "feature", "priority": "should", "evidence": ["E99", "X"]},
    ]))
    assert out[0].evidence == [] and out[0].label == "assumption"


def test_generated_text_that_breaks_a_must_never_rule_is_removed():
    out = requirements_mapper.from_model(inputs(), model([
        {"statement": "Tell users you will make 5,000 USD a month", "type": "feature", "priority": "must",
         "evidence": ["B1"]},
        {"statement": "Book a cleaner", "type": "feature", "priority": "must", "evidence": ["B1"]},
    ]))
    assert [r.statement for r in out] == ["Book a cleaner"]


def test_rules_fallback_without_a_model_is_arabic_for_an_arabic_brief():
    out = requirements_mapper.from_rules(inputs())
    assert len(out) >= 4 and any("MOCKED" in r.statement for r in out)
    assert any("مقدمو الخدمة" in r.statement for r in out)  # two-sided idea: supply side requirement
    assert all(r.label != "evidenced" for r in out)  # no Phase 1 evidence: nothing may claim to be evidenced


def test_run_falls_back_to_rules_when_the_model_fails():
    def broken(msgs):
        raise TimeoutError("model down")

    reqs = requirements_mapper.run(inputs("pharmastock_v1.json"), chat_json=broken, model="qwen3:4b-instruct")
    assert reqs.source == "rules" and reqs.model is None and [r.id for r in reqs.items][:2] == ["R1", "R2"]
    text = (Path(os.environ["OUTPUTS_DIR"]) / "phase3_step2_requirements.md").read_text(encoding="utf-8")
    assert "Brief id:" in text and "fixed rules" in text
    e = read_log()[-1]
    assert e["agent"] == "requirements_mapper" and e["outcome"] == "rules" and e["model"] is None


def test_run_with_a_model_numbers_musts_first():
    reqs = requirements_mapper.run(inputs(), chat_json=model([
        {"statement": "Give feedback", "type": "feature", "priority": "could", "evidence": []},
        {"statement": "Book a cleaner", "type": "feature", "priority": "must", "evidence": ["B1"]},
        {"statement": "Cleaner profiles", "type": "feature", "priority": "should", "evidence": ["B2"]},
    ]), model="qwen3:4b-instruct")
    assert reqs.source == "model" and reqs.items[0].statement == "Book a cleaner" and reqs.items[0].id == "R1"
    assert read_log()[-1]["model"] == "qwen3:4b-instruct"
