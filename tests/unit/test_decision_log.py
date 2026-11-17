"""decision_log.json from a Discover run: every entry has the required keys with the right types."""

import json
import os
from pathlib import Path

from discover_fakes import FakeStoreWithInterviews, FakeToolboxWithApis

from venture_os.agents.research_planner import build_plan
from venture_os.decision_log import log_actions
from venture_os.orchestrator import run_discover

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"


def test_every_entry_has_the_required_keys_and_types():
    brief = json.loads((FIX / "nadafa_v1.json").read_text(encoding="utf-8"))
    run_discover("run-log", build_plan(brief, []), brief, FakeToolboxWithApis(), FakeStoreWithInterviews())
    log = json.loads(Path(os.environ["DECISION_LOG_PATH"]).read_text(encoding="utf-8"))
    assert len(log) > 20
    for e in log:
        assert isinstance(e["timestamp"], str) and e["timestamp"].endswith("Z")
        assert isinstance(e["agent"], str) and e["agent"]
        assert isinstance(e["action"], str) and e["action"]
        assert isinstance(e["sources"], list) and all(s.startswith(("https://", "http://")) for s in e["sources"])
        assert e["model"] is None or isinstance(e["model"], str)
        assert isinstance(e["cost"], int | float)
        assert e["approved_by"] in (None, "founder")
    agents = {e["agent"] for e in log}
    assert {"gate", "brief_analyzer", "opportunity_finder", "idea_scorer", "market_definer", "interview_designer",
            "research_critic"} <= agents
    assert any(e["action"] == "evaluate_discover_gate" and e.get("outcome") for e in log)
    assert all(e["approved_by"] is None for e in log)  # no agent approves anything


def test_batch_logging_refuses_a_non_founder_approver():
    import pytest
    with pytest.raises(ValueError):
        log_actions([{"agent": "opportunity_finder", "action": "approve", "approved_by": "model"}])
