"""Phase 3 step 0: evidence contract and the build entry check."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from venture_os import evidence, gates
from venture_os.agents import build_inputs
from venture_os.decision_log import read_log
from venture_os.onboarding.briefs import ConfirmedBrief

FIX = Path(__file__).parents[1] / "fixtures" / "briefs"


def brief(name="nadafa_v1.json", **over):
    b = ConfirmedBrief.from_file(FIX / name)
    return b.model_copy(update=over) if over else b


# ---------- evidence contract ----------

def test_evidenced_items_need_a_source_url():
    with pytest.raises(ValidationError):
        evidence.Item(phase=1, kind="pain", text="x", label="evidenced")
    evidence.Item(phase=1, kind="pain", text="x", label="assumption")  # fine without a source


def test_add_and_load_assign_ids_in_order():
    a = evidence.add("b1", [evidence.Item(phase=1, text="one", label="assumption")])
    b = evidence.add("b1", [evidence.Item(phase=1, text="two", label="evidenced", sources=["https://e.org/a"])])
    assert [a[0].id, b[0].id] == ["E1", "E2"]
    assert [i.text for i in evidence.load("b1")] == ["one", "two"] and evidence.load("other") == []


# ---------- entry check ----------

def test_brief_becomes_labelled_items_and_constraints():
    inp = build_inputs.collect(brief())
    kinds = {i.kind for i in inp.items}
    assert {"idea", "pain", "customer", "supply"} <= kinds
    assert all(i.label in ("founder_stated", "inferred") for i in inp.items if i.phase == 0)
    assert inp.constraints["budget"] and inp.budget["currency"] == "EGP" and inp.lang == "ar"
    assert inp.can_start


def test_missing_phase_1_and_2_are_listed_at_the_start_not_blocking():
    inp = build_inputs.collect(brief())
    assert any("Phase 1" in m for m in inp.missing) and any("Phase 2" in m for m in inp.missing)
    assert inp.can_start


def test_phase_evidence_is_included_with_its_label():
    b = brief()
    evidence.add(b.brief_id, [evidence.Item(phase=1, kind="pain", text="Families distrust informal cleaners",
                                            label="evidenced", sources=["https://example.org/survey"])])
    inp = build_inputs.collect(b)
    ev = inp.by_label("evidenced")
    assert len(ev) == 1 and ev[0].id == "E1" and not any("Phase 1" in m for m in inp.missing)


def test_excluded_product_does_not_start():
    inp = build_inputs.collect(brief(product_check={"status": "excluded", "categories": ["physical_goods"]}))
    assert not inp.can_start and "excluded" in inp.stop_reason


def test_phase2_stop_does_not_start():
    b = brief()
    test = gates.plan_demand_test(100, 14)
    gates.record(gates.demand_gate(test, actual=12, days_elapsed=14), brief_id=b.brief_id)
    inp = build_inputs.collect(b)
    assert inp.phase2_outcome == "stop" and not inp.can_start and "demand" in inp.stop_reason


def test_run_writes_the_output_and_a_log_entry():
    b = brief("pharmastock_v1.json")
    build_inputs.run(b)
    text = (Path(os.environ["OUTPUTS_DIR"]) / "phase3_step1_build_inputs.md").read_text(encoding="utf-8")
    assert f"Brief id: `{b.brief_id}`" in text and "FOUNDER-STATED" in text and "3,000 USD" in text
    e = read_log()[-1]
    assert e["agent"] == "build_inputs" and e["outcome"] == "missing_inputs" and e["approved_by"] is None
