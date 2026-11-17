# ruff: noqa: F811  (pytest fixtures are imported from test_stages_api and used as arguments)
"""Phase 2 Validate through the stage API against a real, seeded Postgres (offline fakes, no live model).

Order: Discover approved -> Validate (Lean Canvas -> demand test declared -> landing draft MOCKED) -> the
founder's sign-up count -> demand gate -> the founder's decision -> Build may start."""

import json
import os
from pathlib import Path

from test_stages_api import (  # noqa: F401  (fixtures and helpers from the Discover tests)
    _ok,
    client,
    decide,
    make_brief,
    pytestmark,
    start,
)


def _discover_approved(client, make_brief):
    bid, sid = make_brief("nadafa")
    _, run = start(client, "discover", bid)
    assert decide(client, run["id"], "approve", sid).json()["status"] == "approved"
    return bid, sid


def _signups(client, run_id, sid, **body):
    return client.post(f"/stages/runs/{run_id}/signups", json=body, headers={"X-Founder-Session": sid} if sid else {})


def _log():
    return json.loads(Path(os.environ["DECISION_LOG_PATH"]).read_text(encoding="utf-8"))


def test_validate_is_refused_before_discover_is_approved(client, make_brief):
    bid, sid = make_brief("nadafa")
    assert client.post("/stages/validate/runs", json={"brief_id": bid}).status_code == 403
    _, run = start(client, "discover", bid)          # Discover done but not approved yet
    r = client.post("/stages/validate/runs", json={"brief_id": bid})
    assert r.status_code == 403 and "discover" in r.json()["detail"]
    decide(client, run["id"], "reject", sid)          # stop is not a go either
    assert client.post("/stages/validate/runs", json={"brief_id": bid}).status_code == 403


def test_validate_declares_the_test_before_the_draft_and_waits_for_the_founder(client, make_brief):
    bid, _sid = _discover_approved(client, make_brief)
    r, run = start(client, "validate", bid)
    assert r.status_code == 201
    v = run["output"]["validate"]
    assert v["status"] == "awaiting_signups", v.get("error")
    assert run["status"] == "running"                 # no decision is possible before a count exists
    assert v["demand_test"]["target"] == 100 and v["demand_test"]["days"] == 14
    assert v["draft"]["publishing"] == "MOCKED" and "phase2_step1_lean_canvas.md" in v["files"]
    assert "ASSUMPTION" in v["canvas_md"] and "gate" not in v
    steps = [e for e in _log() if e.get("brief_id") == bid and e["agent"] in ("business_designer", "landing_page")]
    actions = [e["action"] for e in steps]
    assert "plan_demand_test" in actions and all(e["approved_by"] is None for e in steps)
    canvas_at = next(i for i, e in enumerate(steps) if e["agent"] == "business_designer")
    test_at = actions.index("plan_demand_test")
    later = [i for i, e in enumerate(steps) if e["agent"] == "landing_page" and e["action"] != "plan_demand_test"]
    assert canvas_at < test_at and all(i > test_at for i in later)   # canvas -> test declared -> draft


def test_build_is_refused_until_validate_is_approved(client, make_brief):
    bid, sid = _discover_approved(client, make_brief)
    r = client.post("/stages/build/runs", json={"brief_id": bid})
    assert r.status_code == 403 and "validate" in r.json()["detail"]
    _, run = start(client, "validate", bid)
    assert client.post("/stages/build/runs", json={"brief_id": bid}).status_code == 403   # not decided yet
    assert decide(client, run["id"], "approve", sid).status_code == 409                  # no count, no decision
    _signups(client, run["id"], sid, actual=100, days_elapsed=14)
    assert client.post("/stages/build/runs", json={"brief_id": bid}).status_code == 403   # gated, not approved
    assert decide(client, run["id"], "approve", sid).json()["status"] == "approved"
    r = client.post("/stages/build/runs", json={"brief_id": bid})
    assert r.status_code == 201, r.text


def test_12_of_100_signups_recommends_stop_and_the_founder_decides(client, make_brief):
    bid, sid = _discover_approved(client, make_brief)
    _, run = start(client, "validate", bid)
    r = _signups(client, run["id"], sid, actual=12, days_elapsed=14)
    assert r.status_code == 200, r.text
    out = r.json()
    v = out["output"]["validate"]
    g = v["gate"]
    assert out["status"] == "awaiting_approval" and g["outcome"] == "stop"
    assert (g["target"], g["actual"]) == (100, 12) and "founder-reported" in g["reason"]
    assert v["signups"]["source"] == "founder" and "phase2_gate_demand.md" in v["files"]
    done = decide(client, run["id"], "reject", sid, note="12 of 100: not enough demand").json()
    assert done["status"] == "rejected" and done["decisions"][-1]["actor"] == "founder"
    count = [e for e in _log() if e["action"] == "enter_signup_count" and e.get("brief_id") == bid]
    assert count and count[-1]["actual"] == 12 and count[-1]["source"] == "founder"
    assert client.post("/stages/build/runs", json={"brief_id": bid}).status_code == 403   # stop: no Build


def test_signups_endpoint_rejects_bad_input(client, make_brief):
    bid, sid = _discover_approved(client, make_brief)
    _, run = start(client, "validate", bid)
    rid = run["id"]
    assert _signups(client, rid, None, actual=12, days_elapsed=14).status_code == 401       # founder only
    for bad in ({"actual": -1, "days_elapsed": 14}, {"actual": 12, "days_elapsed": -3}, {"days_elapsed": 14},
                {"actual": 12}, {"actual": "12", "days_elapsed": 14}, {"actual": 12.5, "days_elapsed": 14},
                {"actual": None, "days_elapsed": 14}):
        assert _signups(client, rid, sid, **bad).status_code == 422, bad
    discover = client.get("/stages/runs", params={"brief_id": bid, "stage": "discover"}).json()[0]
    assert _signups(client, discover["id"], sid, actual=12, days_elapsed=14).status_code == 409  # not Validate
    assert client.get(f"/stages/runs/{rid}").json()["output"]["validate"].get("gate") is None  # nothing recorded
