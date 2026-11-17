"""Phases 5-6 stage entry points: contract, MOCKED posting and payments, approval only from the founder."""

import os
from pathlib import Path

from venture_os import gates, payments
from venture_os.agents.demand_test import enter_signups
from venture_os.launch_stage import run_launch_stage
from venture_os.onboarding.briefs import ConfirmedBrief
from venture_os.operate_stage import run_operate_stage

BRIEF = ConfirmedBrief.from_file(Path(__file__).resolve().parents[1] / "fixtures" / "briefs" / "pharmastock_v1.json")


def _out(name):
    return (Path(os.environ["OUTPUTS_DIR"]) / name).read_text(encoding="utf-8")


def _founder(approved: set):
    def approve(brief_id, action, payload):
        digest = payments.content_hash(payload)
        if (action, digest) in approved:
            return {"approved_by": "founder", "action": action, "content_hash": digest}
        return None
    return approve


def _all_test_payloads():
    oid = f"ord_A_{BRIEF.brief_id[:8]}"
    order = payments.order_payload(BRIEF.brief_id, "MVP access (Phase 3 output)", 15.0, "USD")
    return {("create_order", payments.content_hash(order)),
            ("refund_order", payments.content_hash({"order_id": oid, "amount": 15.0, "currency": "USD"}))}


def test_launch_without_founder_approval_is_repeat_and_nothing_runs():
    import sys
    import types
    fake = types.ModuleType("venture_os.approval")
    fake.has_founder_approval = lambda *a, **k: False
    sys.modules["venture_os.approval"] = fake
    try:
        r = run_launch_stage(BRIEF.brief_id, BRIEF.version, brief=BRIEF)
    finally:
        del sys.modules["venture_os.approval"]
    assert (r.decision.phase, r.decision.gate, r.decision.outcome) == (5, "launch", "repeat")
    assert "refused" in _out("payment_test_log.md") and payments.load_state()["orders"] == {}
    assert r.files == ["phase5_step1_store_page.md", "phase5_step2_launch_posts.md", "payment_test_log.md",
                       "phase5_gate_launch.md"]
    for f in r.files:
        assert BRIEF.brief_id in _out(f)


def test_launch_with_founder_approved_test_order_is_go(monkeypatch):
    import sys
    import types
    approved = _all_test_payloads()
    fake = types.ModuleType("venture_os.approval")  # approval.py confirms only the founder's approved payloads
    fake.has_founder_approval = lambda brief_id, action, content_hash: (action, content_hash) in approved
    monkeypatch.setitem(sys.modules, "venture_os.approval", fake)
    r = run_launch_stage(BRIEF.brief_id, BRIEF.version, brief=BRIEF, approve=_founder(approved))
    assert r.decision.outcome == "go"
    log = _out("payment_test_log.md")
    assert "| 4. deliveries for order A | 1 (expected 1) |" in log and "| 5b. access after refund | False |" in log
    assert "missing payment" in log and "MOCKED" in log
    assert "(nothing posted)" in r.decision.reason


def test_operate_memo_from_logged_results_only():
    enter_signups(BRIEF.brief_id, 12, 14, test=gates.plan_demand_test(100, 14))
    r = run_operate_stage(BRIEF.brief_id, BRIEF.version)
    assert (r.decision.phase, r.decision.gate, r.decision.outcome) == (6, "operate", "stop")
    assert r.stubbed and all("integration" in s for s in r.stubbed)
    assert "12 of target 100" in _out("phase6_step1_pivot_memo.md")
