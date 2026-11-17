"""MOCKED sale-to-cash test run -> outputs/payment_test_log.md (written from this real run, never by hand).

    python scripts/payment_test.py --brief-id <id>

Scenario: order -> mock payment event -> the same event again (no-op) -> delivery happens once -> refund (access
revoked) -> a second order whose payment never arrives -> reconcile (flags the missing payment).
Every order and refund needs the founder's approval: the founder types "approve" here, and the approval is
recorded through approval.py (record_founder_approval). Without approval.py nothing runs, and the log says so.
No provider, no sandbox, no network, no money.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable

from venture_os import delivery, payments, reconcile, refunds
from venture_os.decision_log import read_log
from venture_os.outputs import outputs_dir

Approve = Callable[[str, str, dict], dict | None]
PRODUCT, PRICE, CURRENCY = "MVP access (Phase 3 output)", 15.0, "USD"


def terminal_approve(brief_id: str, action: str, payload: dict) -> dict | None:
    """The founder approves in the terminal; the approval is stored by approval.py (fails closed)."""
    answer = input(f"Founder: approve {action} {payload}? Type 'approve' or 'reject': ").strip().lower()
    if answer != "approve":
        return None
    digest = payments.content_hash(payload)
    module = importlib.import_module("venture_os.approval")  # ImportError -> nothing runs
    module.record_founder_approval(brief_id=brief_id, action=action, content_hash=digest)  # TODO(approval.py)
    return {"approved_by": "founder", "action": action, "content_hash": digest}


def run_scenario(brief_id: str, approve: Approve) -> list[tuple[str, str]]:
    steps: list[tuple[str, str]] = []

    def step(name: str, fn):
        try:
            result = fn()
            steps.append((name, f"ok: {result}"))
            return result
        except Exception as e:  # noqa: BLE001 - every refusal or error is written to the log, never hidden
            steps.append((name, f"refused/failed: {type(e).__name__}: {e}"))
            return None

    def approved(action, payload):
        return approve(brief_id, action, payload)

    a = step("1. create order A (founder approval)", lambda: payments.create_order(
        brief_id, PRODUCT, PRICE, CURRENCY, approved("create_order", payments.order_payload(
            brief_id, PRODUCT, PRICE, CURRENCY)), order_id="ord_A")["id"])
    if a is None:
        return steps
    step("2. mock payment event evt_A1 succeeded", lambda: payments.payment_event("ord_A", "evt_A1")["status"])
    step("3. same event evt_A1 again (duplicate)", lambda: payments.payment_event("ord_A", "evt_A1")["status"])
    grants = sum(1 for e in read_log() if e["action"] == "grant_access" and e.get("order_id") == "ord_A")
    steps.append(("4. deliveries for order A", f"{grants} (expected 1)"))
    steps.append(("4b. access after payment", str(delivery.has_access("ord_A"))))
    step("5. refund order A (founder approval)", lambda: refunds.refund("ord_A", approved(
        "refund_order", {"order_id": "ord_A", "amount": PRICE, "currency": CURRENCY}))["order_id"])
    steps.append(("5b. access after refund", str(delivery.has_access("ord_A"))))
    step("6. create order B; its payment never arrives", lambda: payments.create_order(
        brief_id, PRODUCT, PRICE, CURRENCY, approved("create_order", payments.order_payload(
            brief_id, PRODUCT, PRICE, CURRENCY)), order_id="ord_B")["id"])
    report = reconcile.reconcile()
    summary = (f"{len(report['orders'])} orders, {len(report['issues'])} mismatches, "
               f"fees {report['fees_total']}, payouts {report['payouts_total']}")
    steps.append(("7. reconcile", summary))
    if report:
        for issue in report["issues"]:
            steps.append(("7b. mismatch", f"{issue['order_id']}: {issue['issue']}"))
    return steps


def write_log(brief_id: str, steps: list[tuple[str, str]]) -> str:
    lines = [f"Brief id: {brief_id}", "", "# Payment and delivery test run (MOCKED)", "",
             ("No payment provider, no sandbox, no network: every payment, delivery and refund below is a mock "
              "record. Fees and payouts are 0 because no money moves."), "", "| Step | Result |", "|---|---|"]
    lines += [f"| {n} | {r.replace('|', '/')} |" for n, r in steps]
    path = outputs_dir() / "payment_test_log.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--brief-id", required=True)
    a = p.parse_args(argv)
    steps = run_scenario(a.brief_id, terminal_approve)
    print(write_log(a.brief_id, steps))
    for n, r in steps:
        print(f"{n}: {r}")


if __name__ == "__main__":
    sys.exit(main())
