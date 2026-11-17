# ruff: noqa: F811  (pytest fixtures are imported from test_stages_api and used as arguments)
"""Phase 1 -> Phase 3 through the stage API against a real, seeded Postgres (offline web fakes).

Build starts only after the founder approved Discover for the same brief version; Discover's claims arrive as
evidence; the stage runs with no approval inside it and ends waiting for the founder's one decision."""

import json
import os
from pathlib import Path

from test_stages_api import (  # noqa: F401  (fixtures and helpers from the Discover tests)
    _ok,
    add_version,
    client,
    decide,
    make_brief,
    pytestmark,
    start,
)


def _approved_discover(client, make_brief):
    """Discover approved, then Validate: canvas + declared test + draft, the founder's count, the founder's go."""
    bid, sid = make_brief("nadafa")
    _, run = start(client, "discover", bid)
    assert decide(client, run["id"], "approve", sid).json()["status"] == "approved"
    _, val = start(client, "validate", bid)
    r = client.post(f"/stages/runs/{val['id']}/signups", json={"actual": 140, "days_elapsed": 14},
                    headers={"X-Founder-Session": sid})
    assert r.status_code == 200, r.text
    assert decide(client, val["id"], "approve", sid).json()["status"] == "approved"
    return bid, sid


def test_build_needs_an_approved_discover(client, make_brief):
    bid, _sid = make_brief("nadafa")
    r = client.post("/stages/build/runs", json={"brief_id": bid})
    assert r.status_code == 403 and "validate" in r.json()["detail"]


def test_build_runs_after_discover_and_waits_for_one_founder_decision(client, make_brief):
    bid, sid = _approved_discover(client, make_brief)
    r, run = start(client, "build", bid)
    assert r.status_code == 201 and r.json()["status"] == "running"
    build = run["output"]["build"]
    assert run["status"] == "awaiting_approval", build.get("error")
    assert build["gate"]["outcome"] == "go" and build["template"] == "booking"
    assert "phase3_step5_mvp.html" in build["files"] and bid in build["files"]["phase3_step5_mvp.html"]

    # Discover's sourced claims reach Phase 3 as evidence (D1, D2, ... in the build inputs)
    inputs_md = build["files"]["phase3_step1_build_inputs.md"]
    assert "| D1 | 1 |" in inputs_md and "No Phase 1 (Discover) findings" not in inputs_md

    # nobody approved anything inside the stage; the founder's one decision closes it
    log = json.loads(Path(os.environ["DECISION_LOG_PATH"]).read_text(encoding="utf-8"))
    stage_steps = [e for e in log if e.get("brief_id") == bid and e["agent"] in (
        "build_inputs", "requirements_mapper", "mvp_planner", "mvp_validator", "mvp_builder", "mvp_tester",
        "docs_writer", "build_stage")]
    assert stage_steps and all(e["approved_by"] is None for e in stage_steps)
    assert decide(client, run["id"], "approve", None).status_code == 401  # founder only
    done = decide(client, run["id"], "approve", sid).json()
    assert done["status"] == "approved" and done["decisions"][-1]["actor"] == "founder"


def test_editing_the_brief_makes_build_stale_and_needs_discover_again(client, make_brief):
    bid, _sid = _approved_discover(client, make_brief)
    start(client, "build", bid)
    add_version(bid, "nadafa", 2)
    runs = client.get("/stages/runs", params={"brief_id": bid, "stage": "build"}).json()
    assert runs[0]["stale"]
    assert client.post("/stages/build/runs", json={"brief_id": bid}).status_code == 403
