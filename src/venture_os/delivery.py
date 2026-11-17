"""MOCKED: automatic delivery of the product to a buyer after a (mock) payment. Nothing is emailed or sent.

deliver(order_id) grants access to the Phase 3 MVP (outputs/phase3_step5_mvp.html, or a placeholder if Phase 3
has not produced it yet). Idempotency key = order id: a second call for the same order is a logged no-op, so a
repeated payment event never delivers twice. Delivery happens only for an order with a succeeded payment.
A refund revokes the grant (revoke), and has_access() then returns False.
"""

from __future__ import annotations

import hashlib

from venture_os import payments
from venture_os.outputs import outputs_dir

MVP_FILE = "phase3_step5_mvp.html"
PLACEHOLDER = "placeholder: the Phase 3 MVP has not been built yet (STUBBED)"


def product_target() -> str:
    path = outputs_dir() / MVP_FILE
    return f"outputs/{MVP_FILE}" if path.is_file() else PLACEHOLDER


def deliver(order_id: str) -> dict:
    with payments._lock:
        state = payments.load_state()
        order = state["orders"].get(order_id)
        if order is None:
            raise KeyError(f"unknown order {order_id}")
        if order_id in state["grants"]:  # idempotency key = order id
            payments.log("delivery", "deliver_duplicate_noop", order_id=order_id, brief_id=order["brief_id"])
            return state["grants"][order_id]
        paid = any(p["order_id"] == order_id and p["status"] == "succeeded" for p in state["payments"].values())
        if not paid or order["status"] != "paid":
            payments.log("delivery", "deliver_refused", order_id=order_id, brief_id=order["brief_id"],
                         reason="no succeeded payment for this order")
            raise PermissionError("delivery needs a succeeded payment for this order")
        grant = {"order_id": order_id, "target": product_target(), "active": True, "granted_at": payments.now(),
                 "access_code": hashlib.sha256(f"access:{order_id}".encode()).hexdigest()[:16], "mocked": True}
        state["grants"][order_id] = grant
        order["status"] = "delivered"
        payments.save_state(state)
    payments.log("delivery", "grant_access", order_id=order_id, brief_id=order["brief_id"], target=grant["target"])
    return grant


def revoke(order_id: str, reason: str) -> None:
    with payments._lock:
        state = payments.load_state()
        grant = state["grants"].get(order_id)
        if not grant or not grant["active"]:
            return
        grant.update(active=False, revoked_at=payments.now(), revoked_because=reason)
        payments.save_state(state)
    payments.log("delivery", "revoke_access", order_id=order_id, reason=reason)


def has_access(order_id: str) -> bool:
    grant = payments.load_state()["grants"].get(order_id)
    return bool(grant and grant["active"])
