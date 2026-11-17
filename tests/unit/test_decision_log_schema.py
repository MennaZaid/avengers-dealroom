"""decision_log.json chokepoint: every append is schema-checked and a bad entry raises."""

import json
from pathlib import Path

import pytest

from venture_os.decision_log import log_action, log_actions, read_log, validate_entry

REPO_LOG = Path(__file__).resolve().parents[2] / "decision_log.json"


def test_a_good_entry_is_appended_with_the_five_keys():
    e = log_action("researcher", "search", sources=["https://example.org"], model=None, cost=0)
    assert {"timestamp", "agent", "action", "sources", "model", "cost", "approved_by"} <= e.keys()
    assert read_log()[-1] == e


@pytest.mark.parametrize("kw, why", [
    ({"sources": "https://example.org"}, "sources"), ({"sources": [1]}, "sources"), ({"model": 3}, "model"),
    ({"cost": -1}, "cost"), ({"cost": "free"}, "cost"), ({"approved_by": "agent"}, "approved_by")])
def test_bad_entries_raise_and_are_not_written(kw, why):
    with pytest.raises((ValueError, TypeError)):
        log_action("researcher", "search", **kw)
    assert read_log() == []


def test_gate_decisions_need_an_outcome():
    with pytest.raises(ValueError, match="outcome"):
        log_action("gate", "evidence_gate", sources=[], model=None, cost=0, approved_by=None)
    log_action("gate", "evidence_gate", sources=[], model=None, cost=0, approved_by=None, outcome="stop")
    log_action("gate", "set_gate_thresholds", sources=[], model=None, cost=0, approved_by=None)  # a setting
    with pytest.raises(ValueError):
        log_actions([{"agent": "gate", "action": "discover_gate_decision"}])


def test_the_committed_log_stays_valid():
    for e in json.loads(REPO_LOG.read_text(encoding="utf-8")):
        validate_entry(e)
