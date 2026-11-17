"""MOCKED: refunds. No money is returned or moved; the order is marked refunded and access is revoked.

A refund is never decided by the system: refund() requires the founder's approval of this exact refund
(order id and amount), confirmed by approval.py. Refunding twice is a logged no-op.
"""

from __future__ import annotations

from venture_os import delivery, payments


def refund(order_id: str, approval: dict | None, reason: str = "requested by buyer") -> dict:
    state = payments.load_state()
    order = state["orders"].get(order_id)
    if order is None:
        raise KeyError(f"unknown order {order_id}")
    payload = {"order_id": order_id, "amount": order["price"], "currency": order["currency"]}
    payments.require_founder_approval(order["brief_id"], "refund_order", payload, approval)
    with payments._lock:
        state = payments.load_state()
        if order_id in state["refunds"]:
            payments.log("refunds", "refund_duplicate_noop", order_id=order_id, brief_id=order["brief_id"])
            return state["refunds"][order_id]
        record = {"order_id": order_id, "amount": order["price"], "currency": order["currency"], "reason": reason,
                  "refunded_at": payments.now(), "mocked": True}
        state["refunds"][order_id] = record
        state["orders"][order_id]["status"] = "refunded"
        payments.save_state(state)
    payments.log("refunds", "refund_order", approved_by="founder", order_id=order_id, brief_id=order["brief_id"],
                 amount=order["price"], currency=order["currency"])
    delivery.revoke(order_id, "refunded")
    return record
