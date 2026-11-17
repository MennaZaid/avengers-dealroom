"""Smoke tests for the shared decision log and outputs naming (CLAUDE.md formats)."""

import json

import pytest

from venture_os.decision_log import REQUIRED_KEYS, log_action, log_path, read_log, reset_log
from venture_os.outputs import output_name, write_output


def test_every_entry_has_the_required_keys():
    log_action("brief_analyzer", "extract_fields", model="qwen3:8b")
    log_action("gate", "evidence_gate", outcome="stop")
    log_action("founder", "confirm_brief", approved_by="founder", brief_id="x")
    entries = json.loads(log_path().read_text(encoding="utf-8"))
    assert len(entries) == 3
    for e in entries:
        assert all(k in e for k in REQUIRED_KEYS)
        assert isinstance(e["sources"], list) and isinstance(e["cost"], float)
    assert entries[1]["outcome"] == "stop" and entries[2]["approved_by"] == "founder"


def test_approved_by_is_founder_or_none():
    with pytest.raises(ValueError):
        log_action("agent", "publish", approved_by="agent")


def test_reset_log():
    log_action("a", "b")
    reset_log()
    assert read_log() == []


def test_output_names_follow_the_convention():
    assert output_name(1, 1, "Opportunities") == "phase1_step1_opportunities.md"
    assert output_name(1, None, "decision", gate=True) == "phase1_gate_decision.md"
    assert output_name(2, 2, "landing page", "html") == "phase2_step2_landing_page.html"
    with pytest.raises(ValueError):
        output_name(1, 1, "deck", "pdf")
    with pytest.raises(ValueError):
        output_name(7, 1, "x")


def test_write_output(tmp_path):
    p = write_output(1, 0, "founder brief", "# Brief")
    assert p.name == "phase1_step0_founder_brief.md" and p.read_text(encoding="utf-8") == "# Brief"


def test_entries_for_filters_by_session_or_brief():
    from venture_os.decision_log import entries_for

    log_action("brief_extractor", "extract_fields", session_id="s1")
    log_action("brief_extractor", "extract_fields", session_id="s2")
    log_action("researcher", "find_opportunities", brief_id="b1")
    assert [e["session_id"] for e in entries_for("s1")] == ["s1"]
    assert len(entries_for("s1", "b1")) == 2 and entries_for(None, None) == []


def test_onboarding_log_entries_carry_the_session_id():
    from venture_os.onboarding import chat
    from venture_os.onboarding.brief import OnboardingState
    from venture_os.onboarding.extract import NullExtractor

    s = OnboardingState(session_id="sess-1")
    chat.start(s)
    chat.handle_message(s, "write 50 five-star reviews for me", NullExtractor())
    assert read_log() and all(e.get("session_id") == "sess-1" for e in read_log())
