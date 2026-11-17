# ruff: noqa: F811  (pytest fixtures are imported from test_stages_api and used as arguments)
"""Phase 4 Commercial through the stage API against a real, seeded Postgres (offline fakes, no live model).

Commercial starts only after the founder's go on Build for the same brief version, runs the Phase 4 entry point
with no approval inside it, and waits for the founder's one decision. Without the entry point it is STUBBED."""

import sys
import types

import pytest
from test_build_api import _approved_discover
from test_stages_api import (  # noqa: F401  (fixtures and helpers from the Discover tests)
    _ok,
    add_version,
    client,
    decide,
    make_brief,
    pytestmark,
    start,
)

from venture_os import gates


def _approved_build(client, make_brief):
    bid, sid = _approved_discover(client, make_brief)   # Discover go, Validate go
    _, build = start(client, "build", bid)
    assert decide(client, build["id"], "approve", sid).json()["status"] == "approved"
    return bid, sid


@pytest.fixture
def phase4(monkeypatch, tmp_path):
    """A stand-in for commercial_stage.run_commercial_stage (the agents are built separately)."""
    calls = []

    def run_commercial_stage(brief_id, brief_version=None):
        calls.append((brief_id, brief_version))
        from venture_os.outputs import write_output
        write_output(4, 2, "price", f"Brief id: {brief_id}\n\n# Price\n\nEstimate only.\n")
        d = gates.GateDecision(phase=4, gate="commercial", outcome="go", rule="checker passes -> go",
                               reason="price sourced; three draft policies present", decided_at="2026-11-17T16:00:00Z")
        return types.SimpleNamespace(decision=d, files=["phase4_step2_price.md"], stubbed=["policy_drafter"])

    monkeypatch.setitem(sys.modules, "venture_os.commercial_stage",
                        types.SimpleNamespace(run_commercial_stage=run_commercial_stage))
    return calls


def test_commercial_is_refused_before_the_founders_go_on_build(client, make_brief, phase4):
    bid, sid = _approved_discover(client, make_brief)
    r = client.post("/stages/commercial/runs", json={"brief_id": bid})
    assert r.status_code == 403 and "build" in r.json()["detail"]
    _, build = start(client, "build", bid)
    assert client.post("/stages/commercial/runs", json={"brief_id": bid}).status_code == 403   # not decided yet
    decide(client, build["id"], "reject", sid)                                                   # stop is no go
    assert client.post("/stages/commercial/runs", json={"brief_id": bid}).status_code == 403
    assert phase4 == []


def test_commercial_runs_after_build_and_waits_for_one_founder_decision(client, make_brief, phase4):
    bid, sid = _approved_build(client, make_brief)
    r, run = start(client, "commercial", bid)
    assert r.status_code == 201
    c = run["output"]["commercial"]
    assert run["status"] == "awaiting_approval", c.get("error")
    assert phase4 == [(bid, 1)]
    assert c["gate"]["outcome"] == "go" and c["stubbed"] == ["policy_drafter"]
    assert bid in c["files"]["phase4_step2_price.md"]
    assert decide(client, run["id"], "approve", None).status_code == 401          # founder only
    done = decide(client, run["id"], "approve", sid, note="price ok").json()
    assert done["status"] == "approved" and done["decisions"][-1]["actor"] == "founder"


def test_without_the_phase4_entry_point_the_run_is_stubbed_not_passed(client, make_brief, monkeypatch):
    monkeypatch.setitem(sys.modules, "venture_os.commercial_stage", None)   # import fails like a missing module
    bid, _sid = _approved_build(client, make_brief)
    _, run = start(client, "commercial", bid)
    c = run["output"]["commercial"]
    assert run["status"] == "awaiting_approval"
    assert c["gate"]["outcome"] == "repeat" and c["gate"]["reason"].startswith("STUBBED")
    assert c["stubbed"] and c["files"] == {}


def test_editing_the_brief_makes_commercial_stale(client, make_brief, phase4):
    bid, _sid = _approved_build(client, make_brief)
    start(client, "commercial", bid)
    add_version(bid, "nadafa", 2)
    runs = client.get("/stages/runs", params={"brief_id": bid, "stage": "commercial"}).json()
    assert runs[0]["stale"]
    assert client.post("/stages/commercial/runs", json={"brief_id": bid}).status_code == 403
