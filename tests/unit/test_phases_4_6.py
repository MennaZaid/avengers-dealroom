"""Phases 5-6 (STUBBED): labelled outputs, no banned phrases, gates need approval. Phase 4: test_commercial_stage."""

import os
import sys
import types
from pathlib import Path

import pytest

from venture_os import gates
from venture_os.agents import landing_page, launch, operator, stubbed
from venture_os.agents.demand_test import enter_signups
from venture_os.decision_log import read_log
from venture_os.onboarding.briefs import ConfirmedBrief

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"
FILES = ["phase5_step1_store_page.md", "phase5_step2_launch_posts.md", "phase6_step1_pivot_memo.md"]


def _brief(name="pharmastock_v1.json"):
    return ConfirmedBrief.from_file(FIXTURES / name)


def _out(name):
    return (Path(os.environ["OUTPUTS_DIR"]) / name).read_text(encoding="utf-8")


def _run_all(brief):
    return [launch.run(brief.brief_id, brief=brief), operator.run(brief.brief_id)]


@pytest.mark.parametrize("fixture", ["pharmastock_v1.json", "nadafa_v1.json"])
def test_outputs_are_labelled_stubbed_and_clean(fixture):
    brief = _brief(fixture)
    _run_all(brief)
    for name in FILES:
        md = _out(name)
        assert md.startswith(f"Brief id: {brief.brief_id}\n\n**STUBBED:**"), name
        assert landing_page.banned(md) is None, name
    for phase, gate in ((5, "launch"), (6, "operate")):
        assert (Path(os.environ["OUTPUTS_DIR"]) / f"phase{phase}_gate_{gate}.md").is_file()
    agents = {e["agent"] for e in read_log()}
    assert {"launch", "operator", "gate"} <= agents


def test_launch_links_delivery_and_posting_needs_approval():
    brief = _brief()
    launch.run(brief.brief_id, brief=brief)
    assert "src/venture_os/delivery.py" in _out("phase5_step1_store_page.md")
    with pytest.raises(PermissionError):
        launch.post(brief.brief_id, launch.posts("a", "b", "c")[0], None)
    assert not [e for e in read_log() if e["action"] == "post (MOCKED)"]


def test_memo_uses_only_logged_results():
    brief = _brief()
    operator.run(brief.brief_id)
    assert "no data yet" in _out("phase6_step1_pivot_memo.md")

    enter_signups(brief.brief_id, 12, 14, test=gates.plan_demand_test(100, 14))
    d = operator.run(brief.brief_id)
    md = _out("phase6_step1_pivot_memo.md")
    assert "12 of target 100" in md and d.outcome == "stop"
    assert "Support requests (STUBBED" in md and "no data yet" in md


def test_gates_do_not_pass_without_founder_approval(monkeypatch):
    brief = _brief()
    decisions = _run_all(brief)
    for d in decisions:
        with pytest.raises(PermissionError):
            stubbed.pass_gate(brief.brief_id, d, None)
    approval = {"approved_by": "founder", "action": "pass_phase5_gate", "content_hash": stubbed.decision_hash(
        decisions[0])}
    with pytest.raises(PermissionError, match="approval.py"):  # a dict alone is not enough
        stubbed.pass_gate(brief.brief_id, decisions[0], approval)

    fake = types.ModuleType("venture_os.approval")
    fake.has_founder_approval = lambda brief_id, action, content_hash: content_hash == approval["content_hash"]
    monkeypatch.setitem(sys.modules, "venture_os.approval", fake)
    assert stubbed.pass_gate(brief.brief_id, decisions[0], approval) is True
    assert read_log()[-1]["approved_by"] == "founder"
