"""Founder gates: plain-code entry checks, decisions and stale marking (no database)."""

import pytest

from venture_os.gates import GateRefused, RunView, apply_decision, entry_check, is_stale


def test_discover_needs_a_confirmed_brief():
    with pytest.raises(GateRefused, match="no confirmed version"):
        entry_check("discover", None, [])
    entry_check("discover", 1, [])  # no error


def test_next_stage_refused_without_approval():
    with pytest.raises(GateRefused, match="needs a founder go"):
        entry_check("validate", 1, [])
    for status in ("running", "awaiting_approval", "revision_requested", "rejected", "failed"):
        with pytest.raises(GateRefused):
            entry_check("validate", 1, [RunView("discover", 1, status)])
    entry_check("validate", 1, [RunView("discover", 1, "approved")])


def test_approval_of_another_stage_does_not_count():
    with pytest.raises(GateRefused):
        entry_check("build", 1, [RunView("discover", 1, "approved")])


def test_approval_of_old_brief_version_does_not_unlock():
    runs = [RunView("discover", 1, "approved")]
    with pytest.raises(GateRefused, match="approved for brief v1, but the brief is now v2"):
        entry_check("validate", 2, runs)
    entry_check("validate", 2, runs + [RunView("discover", 2, "approved")])


def test_unknown_stage():
    with pytest.raises(GateRefused):
        entry_check("marketing", 1, [])


def test_revise_then_approve():
    status = apply_decision("awaiting_approval", "revise")
    assert status == "revision_requested"
    assert apply_decision(status, "approve") == "approved"


def test_final_states_take_no_decision():
    for status in ("approved", "rejected", "running", "failed"):
        with pytest.raises(GateRefused):
            apply_decision(status, "approve")


def test_stale():
    assert is_stale(1, 2)
    assert not is_stale(2, 2)
    assert not is_stale(1, None)
