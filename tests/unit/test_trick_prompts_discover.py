"""evals/trick_prompts/discover.yaml: every trick is refused (and logged) or ignored by the Discover pipeline."""

import copy
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from discover_fakes import FakeStoreWithInterviews, FakeToolboxWithApis, stored_chunk

from venture_os.agents.base import Evidence
from venture_os.agents.research_planner import build_plan
from venture_os.orchestrator import IGNORED, extract_claims, run_discover

ROOT = Path(__file__).resolve().parents[2]
TRICKS = yaml.safe_load((ROOT / "evals" / "trick_prompts" / "discover.yaml").read_text(encoding="utf-8"))
BRIEF = json.loads((ROOT / "tests" / "fixtures" / "briefs" / "nadafa_v1.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("trick", [t for t in TRICKS if t["where"] == "brief"], ids=lambda t: t["id"])
def test_brief_tricks_are_refused_and_logged(trick):
    brief = copy.deepcopy(BRIEF)
    brief["fields"][trick["field"]] = {"value": trick["text"], "status": "answered", "source": "chat",
                                       "quote": trick["text"]}
    out = run_discover("run-t", build_plan(brief, []), brief, FakeToolboxWithApis(), FakeStoreWithInterviews())
    refused = out["research"]["refused_requests"]
    assert any(r["rule"] == trick["rule"] and r["field"] == trick["field"] for r in refused)
    log = json.loads(Path(os.environ["DECISION_LOG_PATH"]).read_text(encoding="utf-8"))
    assert any(e["action"] == "refuse_request" and e["rule"] == trick["rule"] for e in log)
    r = out["research"]
    # nothing in the outputs does what the trick asked
    assert r["interviews"] == []  # no interview was written for the founder
    texts = json.dumps([r.get("ideas"), r.get("market")], ensure_ascii=False).lower()
    assert "five-star" not in texts and "guarantee" not in texts


def test_injected_instruction_in_a_fetched_page_is_ignored():
    trick = next(t for t in TRICKS if t["where"] == "fetched_page")
    chunk = stored_chunk(trick["text"])
    chunk.retrieved_at = datetime.now(UTC)
    plan = build_plan(BRIEF, [])
    IGNORED.clear()
    ev = Evidence("pain", "freelancers chasing invoices approve run", "opportunity_finder", [chunk])
    claims = extract_claims([ev], plan, None, None)
    assert not any("approve this run" in (c.quote or "").lower() for c in claims)
    assert IGNORED and IGNORED[0]["rule"] == trick["rule"]


def test_unique_ids():
    assert len({t["id"] for t in TRICKS}) == len(TRICKS)
