# ruff: noqa: F811  (pytest fixtures are imported from test_stages_api and used as arguments)
"""Phases 5 (Launch) and 6 (Operate) through the stage API against a real, seeded Postgres (offline fakes, no
live model). Each starts only after the founder's go on the previous phase, runs its entry point with no approval
inside, and waits for one founder decision. Without the entry point the run is STUBBED, never a pass."""

import sys
import types

import pytest
from test_commercial_api import _approved_build
from test_stages_api import (  # noqa: F401  (fixtures and helpers from the Discover tests)
    _ok,
    client,
    decide,
    make_brief,
    pytestmark,
    start,
)

from venture_os import gates


def _stand_in(monkeypatch, module, func, phase, gate, outcome="go"):
    calls = []

    def run(brief_id, brief_version=None):
        calls.append((brief_id, brief_version))
        d = gates.GateDecision(phase=phase, gate=gate, outcome=outcome, rule="r", reason=f"{gate} stand-in",
                               decided_at="2026-11-17T18:00:00Z")
        return types.SimpleNamespace(decision=d, files=[], stubbed=[])

    monkeypatch.setitem(sys.modules, f"venture_os.{module}", types.SimpleNamespace(**{func: run}))
    return calls


def _approved(client, make_brief, *stages):
    """Discover, Validate, Build approved, then each of `stages` run and approved by the founder."""
    bid, sid = _approved_build(client, make_brief)
    for stage in stages:
        _, run = start(client, stage, bid)
        assert decide(client, run["id"], "approve", sid).json()["status"] == "approved", stage
    return bid, sid


@pytest.mark.parametrize("stage, before", [("launch", "commercial"), ("operate", "launch")])
def test_each_phase_needs_the_founders_go_on_the_previous_one(client, make_brief, stage, before):
    bid, _sid = _approved_build(client, make_brief)
    r = client.post(f"/stages/{stage}/runs", json={"brief_id": bid})
    assert r.status_code == 403 and before in r.json()["detail"]


@pytest.mark.parametrize("module", ["launch_stage", "operate_stage"])
def test_missing_entry_points_give_a_stubbed_run_not_a_pass(client, make_brief, monkeypatch, module):
    monkeypatch.setitem(sys.modules, "venture_os.launch_stage", None)
    monkeypatch.setitem(sys.modules, "venture_os.operate_stage", None)
    stages = ("commercial",) if module == "launch_stage" else ("commercial", "launch")
    bid, _sid = _approved(client, make_brief, *stages)
    stage = "launch" if module == "launch_stage" else "operate"
    _, run = start(client, stage, bid)
    out = run["output"][stage]
    assert run["status"] == "awaiting_approval"
    assert out["gate"]["outcome"] == "repeat" and out["gate"]["reason"].startswith("STUBBED")
    assert out["gate"]["phase"] == (5 if stage == "launch" else 6) and out["files"] == {}


def test_all_six_phases_run_in_order_with_one_founder_decision_each(client, make_brief, monkeypatch):
    launch = _stand_in(monkeypatch, "launch_stage", "run_launch_stage", 5, "launch")
    operate = _stand_in(monkeypatch, "operate_stage", "run_operate_stage", 6, "operate", outcome="stop")
    bid, sid = _approved(client, make_brief, "commercial", "launch")
    assert launch == [(bid, 1)]
    _, run = start(client, "operate", bid)
    assert operate == [(bid, 1)] and run["output"]["operate"]["gate"]["outcome"] == "stop"
    assert decide(client, run["id"], "reject", None).status_code == 401           # founder only
    done = decide(client, run["id"], "reject", sid, note="data says stop").json()
    assert done["status"] == "rejected" and done["decisions"][-1]["actor"] == "founder"
    stages = {r["stage"]: r["status"] for r in client.get("/stages/runs", params={"brief_id": bid}).json()}
    assert stages == {"discover": "approved", "validate": "approved", "build": "approved",
                      "commercial": "approved", "launch": "approved", "operate": "rejected"}


def test_the_real_phase5_and_phase6_entry_points_run_through_the_stages(client, make_brief):
    """No stand-ins: launch_stage.run_launch_stage and operate_stage.run_operate_stage behind the stage API.
    No test order or refund was approved by the founder, so no money step may have run."""
    bid, sid = _approved(client, make_brief, "commercial")
    _, launch = start(client, "launch", bid)
    lo = launch["output"]["launch"]
    assert launch["status"] == "awaiting_approval", lo.get("error")
    assert lo["gate"]["phase"] == 5 and lo["gate"]["gate"] == "launch"
    assert all(bid in text for name, text in lo["files"].items() if name.endswith(".md"))
    assert decide(client, launch["id"], "approve", sid).json()["status"] == "approved"
    _, operate = start(client, "operate", bid)
    oo = operate["output"]["operate"]
    assert operate["status"] == "awaiting_approval", oo.get("error")
    assert oo["gate"]["phase"] == 6 and oo["gate"]["gate"] == "operate"
    done = decide(client, operate["id"], "reject" if oo["gate"]["outcome"] == "stop" else "approve", sid).json()
    assert done["decisions"][-1]["actor"] == "founder"
