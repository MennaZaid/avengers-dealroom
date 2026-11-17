"""Gate smoke tests: every outcome, thresholds fixed before the result, the organizers' STOP example,
and that a gate only recommends (it never records a founder approval)."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from venture_os import gates
from venture_os.decision_log import REQUIRED_KEYS, read_log
from venture_os.onboarding.briefs import ConfirmedBrief

URLS = [f"https://example.org/report-{i}" for i in range(6)]


# ---------- demand gate ----------

def test_organizers_example_12_of_100_in_14_days_is_stop():
    test = gates.plan_demand_test(target=100, days=14)
    d = gates.demand_gate(test, actual=12, days_elapsed=14)
    assert d.outcome == "stop" and "don't launch" in d.reason and d.target == 100 and d.actual == 12


@pytest.mark.parametrize("actual,outcome", [(100, "go"), (140, "go"), (60, "repeat"), (50, "repeat"),
                                            (30, "pivot"), (25, "pivot"), (24, "stop"), (0, "stop")])
def test_demand_outcomes_follow_the_fixed_rule(actual, outcome):
    test = gates.plan_demand_test(target=100, days=14)
    assert gates.demand_gate(test, actual=actual, days_elapsed=14).outcome == outcome


def test_running_test_is_not_judged_early():
    test = gates.plan_demand_test(target=100, days=14)
    assert gates.demand_gate(test, actual=12, days_elapsed=5).outcome == "repeat"
    assert gates.demand_gate(test, actual=100, days_elapsed=5).outcome == "go"  # target reached early


def test_target_cannot_be_changed_after_it_is_declared():
    test = gates.plan_demand_test(target=100, days=14)
    with pytest.raises(ValidationError):
        test.target = 10
    assert test.declared_at in gates.demand_gate(test, actual=12, days_elapsed=14).rule


def test_actual_must_come_from_the_founder_or_be_labelled_mocked():
    test = gates.plan_demand_test(target=100, days=14)
    with pytest.raises(ValueError):
        gates.demand_gate(test, actual=12, days_elapsed=14, source="generated")
    d = gates.demand_gate(test, actual=12, days_elapsed=14, source="mocked")
    assert d.mocked and "MOCKED" in gates.to_markdown(d)


def test_bad_inputs_are_rejected():
    with pytest.raises(ValueError):
        gates.plan_demand_test(target=0, days=14)
    with pytest.raises(ValueError):
        gates.demand_gate(gates.plan_demand_test(10, 7), actual=-1, days_elapsed=7)


# ---------- evidence gate ----------

@pytest.mark.parametrize("n,outcome", [(0, "stop"), (3, "repeat"), (5, "go"), (6, "go")])
def test_evidence_outcomes(n, outcome):
    assert gates.evidence_gate(1, sources=URLS[:n], assumptions=2).outcome == outcome


def test_only_real_urls_count_as_sources():
    d = gates.evidence_gate(1, sources=["ASSUMPTION", "", "www.no-scheme.com", URLS[0]])
    assert d.actual == 1 and d.outcome == "repeat"


# ---------- product gate ----------

def _brief(status, categories=()):
    return ConfirmedBrief(brief_id="b1", version=1, fields={}, tags={},
                          product_check={"status": status, "categories": list(categories)})


def test_excluded_product_stops_before_discover():
    d = gates.product_gate(_brief("excluded", ["physical_goods"]))
    assert d.outcome == "stop" and "physical_goods" in d.reason


def test_borderline_product_goes_with_conditions():
    d = gates.product_gate(_brief("review", ["health"]))
    assert d.outcome == "go" and "no medical" in d.reason


def test_product_gate_on_a_saved_brief():
    path = Path(__file__).parents[1] / "fixtures" / "briefs" / "nadafa_v1.json"
    assert gates.product_gate(ConfirmedBrief.from_file(path)).outcome == "go"


# ---------- record: outputs + decision log ----------

def test_record_writes_the_gate_output_and_a_log_entry():
    test = gates.plan_demand_test(target=100, days=14)
    gates.record(gates.demand_gate(test, actual=12, days_elapsed=14), brief_id="brief-123", brief_version=2)
    out = Path(os.environ["OUTPUTS_DIR"]) / "phase2_gate_demand.md"
    text = out.read_text(encoding="utf-8")
    assert "Brief id: `brief-123`" in text and "STOP" in text and "fixed before the result" in text
    entry = read_log()[-1]
    assert all(k in entry for k in REQUIRED_KEYS)
    assert entry["agent"] == "gate" and entry["action"] == "demand_gate" and entry["outcome"] == "stop"
    assert entry["brief_id"] == "brief-123" and entry["brief_version"] == 2


def test_a_gate_never_records_a_founder_approval():
    gates.record(gates.evidence_gate(1, sources=URLS), brief_id="b")
    gates.record(gates.product_gate(_brief("allowed")), brief_id="b")
    assert all(e["approved_by"] is None for e in read_log())


def test_output_names_follow_the_convention():
    gates.record(gates.evidence_gate(1, sources=URLS[:2]), brief_id="b")
    gates.record(gates.product_gate(_brief("allowed")), brief_id="b")
    names = sorted(p.name for p in Path(os.environ["OUTPUTS_DIR"]).iterdir())
    assert names == ["phase1_gate_evidence.md", "phase1_gate_product.md"]
