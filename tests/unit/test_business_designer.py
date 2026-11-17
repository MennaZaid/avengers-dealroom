"""Lean Canvas (Phase 2): rule fallback, evidence ids checked, unknowns kept, no income promises. No model, no network."""

import json
import os
from pathlib import Path

import pytest

from venture_os.agents import business_designer as bd
from venture_os.decision_log import read_log
from venture_os.guardrails import check_output
from venture_os.onboarding.briefs import ConfirmedBrief

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"
EVIDENCE = [
    {"id": "E1", "phase": 1, "kind": "pain", "text": "Pharmacies report stock-outs of common medicines",
     "label": "evidenced", "sources": ["https://example.org/survey"], "date": "2026-11-17", "quote": "stock-outs"},
    {"id": "E2", "phase": 1, "kind": "competitor_price", "text": "A wholesaler app is free for pharmacies",
     "label": "evidenced", "sources": [], "date": None},  # claims a source but has none
    {"id": "E3", "phase": 1, "kind": "customer", "text": "Owners do their own ordering", "label": "assumption"},
]


def _brief(name: str) -> ConfirmedBrief:
    return ConfirmedBrief.from_file(FIXTURES / name)


def _output() -> str:
    return (Path(os.environ["OUTPUTS_DIR"]) / "phase2_step1_lean_canvas.md").read_text(encoding="utf-8")


def _entries(canvas, basis):
    return [e for es in canvas.boxes.values() for e in es if e.basis == basis]


@pytest.mark.parametrize("fixture", ["nadafa_v1.json", "pharmastock_v1.json"])
def test_rule_fallback_on_fixture_briefs(fixture):
    brief = _brief(fixture)
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=[], chat=None)

    assert set(canvas.boxes) == set(bd.BOXES) and all(canvas.boxes.values())
    assert canvas.built_by == "rules" and canvas.model is None
    for e in _entries(canvas, "FOUNDER"):  # founder entries quote a known brief field
        assert brief.known(e.field) and brief.known(e.field) in e.text
    assert not _entries(canvas, "EVIDENCED")  # no evidence -> nothing is presented as evidenced
    assert canvas.riskiest_assumption

    md = _output()
    assert md.startswith(f"Brief id: {brief.brief_id}")
    assert "| Box | Entry | Basis | Source |" in md
    assert "rules only" in md and check_output(md) == []
    entry = [e for e in read_log() if e["action"] == "design_lean_canvas"][-1]
    assert entry["agent"] == "business_designer" and entry["model"] is None and entry["cost"] == 0
    assert entry["approved_by"] is None and entry["brief_id"] == brief.brief_id


def test_unknown_brief_field_stays_unknown():
    brief = _brief("pharmastock_v1.json")
    brief.fields["problem"] = {"value": None, "status": "unknown"}
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=[], chat=None)
    problem = [e for e in canvas.boxes["problem"] if e.field == "problem"]
    assert [(e.text, e.basis) for e in problem] == [("unknown", "UNKNOWN")]
    assert "| Problem | unknown | UNKNOWN | brief field `problem` is unknown |" in _output()


def test_model_suggestion_never_hides_an_unknown_field():
    brief = _brief("pharmastock_v1.json")
    brief.fields["target_customer"] = {"value": None, "status": "unknown"}
    reply = {"entries": [{"box": "customer_segments", "text": "Chain pharmacies", "evidence_id": None}]}
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=[], chat=lambda m: json.dumps(reply))
    seg = {(e.text, e.basis) for e in canvas.boxes["customer_segments"]}
    assert ("unknown", "UNKNOWN") in seg and ("Chain pharmacies", "ASSUMPTION") in seg


def test_evidence_items_need_url_and_date():
    brief = _brief("pharmastock_v1.json")
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=EVIDENCE, chat=None)
    by_id = {e.evidence_id: e for e in _entries(canvas, "EVIDENCED") + _entries(canvas, "ASSUMPTION")
             if e.evidence_id}
    assert by_id["E1"].basis == "EVIDENCED" and by_id["E1"].url == "https://example.org/survey"
    assert by_id["E2"].basis == "ASSUMPTION"  # labelled evidenced but no URL/date
    assert by_id["E3"].basis == "ASSUMPTION"
    assert "https://example.org/survey (2026-11-17)" in _output()


def test_model_fake_evidence_id_is_relabelled_assumption():
    brief = _brief("pharmastock_v1.json")
    reply = {"entries": [
        {"box": "problem", "text": "Stock-outs lose sales every week", "evidence_id": "E1"},
        {"box": "channels", "text": "Pharmacy association newsletter", "evidence_id": "E99"},
        {"box": "revenue_streams", "text": "Free tier for one store", "evidence_id": "E2"},
    ], "riskiest_assumption": "Owner-pharmacists will try a new stock app"}
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=EVIDENCE, chat=lambda m: json.dumps(reply))

    model = {e.text: e for es in canvas.boxes.values() for e in es if e.by != "rules"}
    assert model["Stock-outs lose sales every week"].basis == "EVIDENCED"
    fake = model["Pharmacy association newsletter"]
    assert fake.basis == "ASSUMPTION" and "E99" in fake.note and "does not exist" in fake.note
    assert model["Free tier for one store"].basis == "ASSUMPTION"  # E2 exists but has no source
    assert canvas.riskiest_assumption == "Owner-pharmacists will try a new stock app"


@pytest.mark.parametrize("text", [
    "Guaranteed income from day one",
    "You will make 5,000 USD per month",
    "Expected monthly revenue of 20,000 EGP",
    "Earn up to $3000 with subscriptions",
])
def test_income_promise_from_model_never_reaches_the_output(text):
    brief = _brief("pharmastock_v1.json")
    reply = {"entries": [{"box": "revenue_streams", "text": text, "evidence_id": None}],
             "riskiest_assumption": "You will earn $500 a week"}
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=[], chat=lambda m: json.dumps(reply))
    md = _output()
    assert text not in md and "$500" not in md
    assert check_output(md) == []
    assert len(canvas.dropped) == 2


def test_model_echo_of_founder_words_is_not_duplicated():
    brief = _brief("pharmastock_v1.json")
    echo = brief.known("problem")
    reply = {"entries": [{"box": "problem", "text": echo, "evidence_id": None},
                         {"box": "revenue_streams", "text": "Monthly subscription, 15 USD per pharmacy."}]}
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=[], chat=lambda m: json.dumps(reply))
    assert [e.basis for e in canvas.boxes["problem"] if e.text == echo] == ["FOUNDER"]
    assert all(e.by == "rules" for e in canvas.boxes["revenue_streams"])


def test_bad_json_is_retried_once_then_rules():
    calls = []

    def chat(messages):
        calls.append(messages)
        return "not json"

    brief = _brief("nadafa_v1.json")
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=[], chat=chat)
    assert len(calls) == 2  # first try + one retry
    assert canvas.built_by == "rules"
    assert "after one retry" in _output()


def test_injected_text_in_brief_is_sent_as_data_only():
    brief = _brief("pharmastock_v1.json")
    seen = {}

    def chat(messages):
        seen["system"], seen["user"] = messages[0]["content"], messages[1]["content"]
        return json.dumps({"entries": []})

    bd.run(brief.brief_id, brief=brief, evidence_items=[], chat=chat)
    assert seen["user"].startswith("<untrusted>") and seen["user"].endswith("</untrusted>")
    assert "Small independent pharmacies" not in seen["system"]
