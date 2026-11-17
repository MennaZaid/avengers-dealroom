"""Sale to cash (MOCKED): approval required, payment triggers delivery once, refund revokes, reconcile flags gaps."""

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

from venture_os import delivery, payments, reconcile, refunds
from venture_os.decision_log import read_log

BRIEF = "dae357fc-d04e-49ad-a518-6309a79c75d7"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def founder(monkeypatch):
    """A stand-in for approval.py: the founder approved exactly the hashes in `approved`."""
    approved = set()
    fake = types.ModuleType("venture_os.approval")
    fake.has_founder_approval = lambda brief_id, action, content_hash: (brief_id, action, content_hash) in approved
    fake.record_founder_approval = lambda brief_id, action, content_hash: approved.add((brief_id, action, content_hash))
    monkeypatch.setitem(sys.modules, "venture_os.approval", fake)

    def approve(brief_id, action, payload):
        digest = payments.content_hash(payload)
        fake.record_founder_approval(brief_id=brief_id, action=action, content_hash=digest)
        return {"approved_by": "founder", "action": action, "content_hash": digest}
    return approve


def _order(approve, oid="ord_1"):
    payload = payments.order_payload(BRIEF, "MVP", 15.0, "USD")
    return payments.create_order(BRIEF, "MVP", 15.0, "USD", approve(BRIEF, "create_order", payload), order_id=oid)


def test_modules_are_labelled_mocked():
    for m in (payments, delivery, refunds, reconcile):
        assert m.__doc__.startswith("MOCKED:"), m.__name__


def test_nothing_runs_without_approval(founder):
    with pytest.raises(PermissionError):
        payments.create_order(BRIEF, "MVP", 15.0, "USD", None)
    forged = {"approved_by": "founder", "action": "create_order",
              "content_hash": payments.content_hash(payments.order_payload(BRIEF, "MVP", 15.0, "USD"))}
    with pytest.raises(PermissionError):  # a dict the founder never approved in approval.py
        payments.create_order(BRIEF, "MVP", 15.0, "USD", forged)
    with pytest.raises(PermissionError):  # approved 15 USD, tries 150 USD
        payments.create_order(BRIEF, "MVP", 150.0, "USD", founder(BRIEF, "create_order",
                                                                  payments.order_payload(BRIEF, "MVP", 15.0, "USD")))
    assert payments.load_state()["orders"] == {}


def test_without_approval_module_everything_is_refused(monkeypatch):
    monkeypatch.setitem(sys.modules, "venture_os.approval", None)
    payload = payments.order_payload(BRIEF, "MVP", 15.0, "USD")
    with pytest.raises(PermissionError, match="approval.py"):
        payments.create_order(BRIEF, "MVP", 15.0, "USD", {"approved_by": "founder", "action": "create_order",
                                                         "content_hash": payments.content_hash(payload)})


def test_double_payment_event_delivers_once(founder):
    _order(founder)
    payments.payment_event("ord_1", "evt_1")
    payments.payment_event("ord_1", "evt_1")
    delivery.deliver("ord_1")  # a direct retry is also a no-op
    assert sum(1 for e in read_log() if e["action"] == "grant_access") == 1
    assert delivery.has_access("ord_1")
    assert delivery.payments.load_state()["grants"]["ord_1"]["target"] == delivery.PLACEHOLDER


def test_delivery_needs_a_payment(founder):
    _order(founder)
    with pytest.raises(PermissionError):
        delivery.deliver("ord_1")
    assert not delivery.has_access("ord_1")


def test_refund_revokes_access_and_needs_approval(founder):
    _order(founder)
    payments.payment_event("ord_1", "evt_1")
    with pytest.raises(PermissionError):
        refunds.refund("ord_1", None)
    refunds.refund("ord_1", founder(BRIEF, "refund_order", {"order_id": "ord_1", "amount": 15.0, "currency": "USD"}))
    assert not delivery.has_access("ord_1")
    assert payments.load_state()["orders"]["ord_1"]["status"] == "refunded"


def test_reconcile_flags_missing_payment(founder):
    _order(founder, "ord_1")
    payments.payment_event("ord_1", "evt_1")
    _order(founder, "ord_2")
    report = reconcile.reconcile()
    assert [i["order_id"] for i in report["issues"]] == ["ord_2"]
    assert "missing payment" in report["issues"][0]["issue"]
    assert report["fees_total"] == 0 and report["payouts_total"] == 0


def test_every_action_is_logged_without_model_or_cost(founder):
    _order(founder)
    payments.payment_event("ord_1", "evt_1")
    entries = [e for e in read_log() if e["agent"] in ("payments", "delivery", "refunds", "reconcile")]
    assert entries and all(e["model"] is None and e["cost"] == 0 and e["mocked"] for e in entries)


def test_payment_test_script_writes_log_from_a_real_run(founder):
    spec = importlib.util.spec_from_file_location("payment_test", ROOT / "scripts" / "payment_test.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    steps = script.run_scenario(BRIEF, founder)
    path = Path(script.write_log(BRIEF, steps))
    md = path.read_text(encoding="utf-8")
    assert path == Path(os.environ["OUTPUTS_DIR"]) / "payment_test_log.md"
    assert md.startswith(f"Brief id: {BRIEF}") and "MOCKED" in md
    assert "| 4. deliveries for order A | 1 (expected 1) |" in md
    assert "| 5b. access after refund | False |" in md
    assert "ord_B: missing payment" in md
