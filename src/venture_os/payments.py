"""MOCKED: payments for the sale-to-cash flow. No payment provider, no sandbox, no network, no money.

Flow (each step logged with log_action, model None, cost 0):
  create_order (founder approval required) -> payment_event("succeeded") -> delivery.deliver (once per order)
  -> refunds.refund (founder approval required) -> reconcile.reconcile

A "payment" here is a record in a local JSON file that says a mock event happened. Nothing is charged, held or
moved. State lives in <data dir>/sale_to_cash.json; the data dir is DATA_DIR, or data/ next to the decision log
(tests redirect the log to a temp folder, so tests never touch real state).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from venture_os.decision_log import log_action, log_path

_lock = threading.RLock()
MOCK = "MOCKED"


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or (log_path().parent / "data"))


def _state_path() -> Path:
    return data_dir() / "sale_to_cash.json"


def load_state() -> dict:
    p = _state_path()
    state = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    for key in ("orders", "payments", "grants", "refunds", "payouts"):
        state.setdefault(key, {})
    return state


def save_state(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(agent: str, action: str, **extra) -> None:
    log_action(agent, action, sources=[], model=None, cost=0, approved_by=extra.pop("approved_by", None),
               mocked=True, **extra)


# ---------- founder approval (approval.py) ----------

def content_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def require_founder_approval(brief_id: str, action: str, payload: dict, approval: dict | None) -> str:
    """Raise PermissionError unless the founder approved exactly this action and payload. Fails closed.
    The approval dict alone is not trusted: approval.py must confirm it.
    TODO(approval.py): needs has_founder_approval(brief_id, action, content_hash) -> bool (not on main yet)."""
    digest = content_hash(payload)
    reason = None
    if not approval or approval.get("approved_by") != "founder" or approval.get("action") != action \
            or approval.get("content_hash") != digest:
        reason = f"no founder approval for this exact {action}"
    else:
        try:
            module = importlib.import_module("venture_os.approval")
            check = getattr(module, "has_founder_approval", None)
            if check is None:
                reason = "approval.py has no has_founder_approval() yet"
            elif check(brief_id=brief_id, action=action, content_hash=digest) is not True:
                reason = f"approval.py has no founder approval for this exact {action}"
        except ImportError:
            reason = "approval.py is not available, so no founder approval can be verified"
    if reason:
        log("payments", f"{action}_refused", brief_id=brief_id, reason=reason, content_hash=digest)
        raise PermissionError(f"{action} refused: {reason}")
    return digest


# ---------- orders and mock payment events ----------

def order_payload(brief_id: str, product: str, price: float, currency: str) -> dict:
    return {"brief_id": str(brief_id), "product": product, "price": price, "currency": currency}


def create_order(brief_id: str, product: str, price: float, currency: str, approval: dict | None,
                 order_id: str | None = None) -> dict:
    """MOCKED order. Only after the founder approved this exact order (product, price, currency)."""
    payload = order_payload(brief_id, product, price, currency)
    digest = require_founder_approval(str(brief_id), "create_order", payload, approval)
    with _lock:
        state = load_state()
        oid = order_id or f"ord_{uuid.uuid4().hex[:10]}"
        if oid in state["orders"]:
            return state["orders"][oid]
        order = {**payload, "id": oid, "status": "created", "created_at": now(), "approval_hash": digest,
                 "mocked": True}
        state["orders"][oid] = order
        save_state(state)
    log("payments", "create_order", approved_by="founder", brief_id=str(brief_id), order_id=oid, price=price,
        currency=currency)
    return order


def payment_event(order_id: str, event_id: str, status: str = "succeeded") -> dict:
    """A MOCKED payment-provider event (as a webhook would deliver it). Repeated event ids are no-ops.
    A succeeded payment triggers delivery; delivery itself is idempotent per order."""
    from venture_os import delivery
    with _lock:
        state = load_state()
        order = state["orders"].get(order_id)
        if order is None:
            log("payments", "payment_event_rejected", order_id=order_id, event_id=event_id, reason="unknown order")
            raise KeyError(f"unknown order {order_id}")
        if event_id in state["payments"]:
            log("payments", "payment_event_duplicate_noop", order_id=order_id, event_id=event_id,
                brief_id=order["brief_id"])
            return state["payments"][event_id]
        payment = {"event_id": event_id, "order_id": order_id, "status": status, "amount": order["price"],
                   "currency": order["currency"], "fee": 0, "received_at": now(), "mocked": True}
        state["payments"][event_id] = payment
        if status == "succeeded" and order["status"] == "created":
            order["status"] = "paid"
        save_state(state)
    log("payments", "payment_event", order_id=order_id, event_id=event_id, status=status, brief_id=order["brief_id"],
        amount=order["price"], currency=order["currency"])
    if status == "succeeded":
        delivery.deliver(order_id)
    return payment
