"""Demand gate (Phase 2): founder-entered count only; 12/100 -> stop/pivot; 100/100 -> go; none -> repeat; evidence."""

import os
import sys
import types
from pathlib import Path

import pytest

from venture_os import gates
from venture_os.agents import demand_test as dt
from venture_os.decision_log import read_log

BRIEF = "dae357fc-d04e-49ad-a518-6309a79c75d7"


@pytest.fixture
def store(monkeypatch):
    """A stand-in for Menna's evidence module (contract: evidence.add(brief_id, [evidence.Item(...)]))."""
    added = []
    fake = types.ModuleType("venture_os.evidence")
    fake.Item = lambda **kw: kw
    fake.add = lambda brief_id, items: added.extend((brief_id, i) for i in items)
    monkeypatch.setitem(sys.modules, "venture_os.evidence", fake)
    return added


def _gate_file():
    return (Path(os.environ["OUTPUTS_DIR"]) / "phase2_gate_demand.md").read_text(encoding="utf-8")


def _test():
    return gates.plan_demand_test(target=100, days=14)


def test_12_of_100_recommends_stop_or_pivot_without_spin(store):
    d = dt.enter_signups(BRIEF, 12, 14, test=_test(), riskiest_assumption="Pharmacists want a stock app")
    assert d.outcome in ("stop", "pivot")
    md = _gate_file()
    assert md.startswith("# Phase 2 gate: demand") and f"Brief id: `{BRIEF}`" in md
    assert "12 of 100" in md and "founder-reported, not verified" in md
    for spin in ("promising", "great start", "strong interest", "success"):
        assert spin not in md.lower()
    founder = next(e for e in read_log() if e["action"] == "enter_signup_count")
    assert founder["source"] == "founder" and founder["approved_by"] == "founder"


def test_100_of_100_is_go(store):
    assert dt.enter_signups(BRIEF, 100, 14, test=_test()).outcome == "go"


def test_no_count_is_repeat_and_no_number_is_made_up(store):
    d = dt.enter_signups(BRIEF, None, 14, test=_test())
    assert d.outcome == "repeat" and d.actual is None
    assert "has not been measured" in _gate_file()
    assert not [e for e in read_log() if e["action"] == "enter_signup_count"]
    assert [i["kind"] for _, i in store] == ["demand_gate"]  # no demand_result without a real count


@pytest.mark.parametrize("bad", [12.5, -1, True, "12"])
def test_count_must_be_a_real_whole_number(store, bad):
    with pytest.raises(ValueError):
        dt.enter_signups(BRIEF, bad, 14, test=_test())


def test_evidence_items_have_the_right_labels(store):
    dt.enter_signups(BRIEF, 12, 14, test=_test(), riskiest_assumption="Pharmacists want a stock app")
    items = {i["kind"]: i for b, i in store if b == BRIEF}
    assert items["riskiest_assumption"]["label"] == "assumption"
    assert items["demand_result"]["label"] == "founder_stated" and "12 of 100" in items["demand_result"]["text"]
    assert items["demand_gate"]["label"] == "inferred" and items["demand_gate"]["text"].split(".")[0].endswith(
        ("stop", "pivot"))
    assert read_log()[-1]["written"] is True


def test_missing_evidence_module_is_reported_not_hidden(monkeypatch):
    monkeypatch.setitem(sys.modules, "venture_os.evidence", None)  # import fails
    d = dt.enter_signups(BRIEF, 12, 14, test=_test())
    assert d.outcome in ("stop", "pivot")
    entry = read_log()[-1]
    assert entry["action"] == "write_phase2_evidence" and entry["written"] is False and entry["error"]


def test_uses_the_test_declared_by_the_landing_page_step(store):
    from venture_os.agents import business_designer as bd
    from venture_os.agents import landing_page as lp
    from venture_os.onboarding.briefs import ConfirmedBrief
    brief = ConfirmedBrief.from_file(Path(__file__).resolve().parents[1] / "fixtures" / "briefs" /
                                     "pharmastock_v1.json")
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=[], chat=None)
    draft = lp.run(brief.brief_id, canvas, brief=brief, chat=None)
    d = dt.enter_signups(brief.brief_id, 12, 14)  # CLI path: test + riskiest assumption read from outputs/
    assert d.target == 100 and draft.demand_test["declared_at"] in d.rule
    assert any(i["kind"] == "riskiest_assumption" for _, i in store)
    with pytest.raises(ValueError):
        dt.enter_signups("another-brief", 12, 14)
