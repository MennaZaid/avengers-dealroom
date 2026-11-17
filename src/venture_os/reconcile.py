"""MOCKED: reconciliation of orders, payments, fees and payouts (fees and payouts are always 0: no money moves).

reconcile() matches every order with its mock payments, deliveries and refunds and reports each mismatch:
an order without a succeeded payment, a payment without an order, a delivery without a payment, access still
active after a refund, a payment amount that differs from the order, and any fee or payout that is not 0.
"""

from __future__ import annotations

from venture_os import payments


def reconcile() -> dict:
    s = payments.load_state()
    orders, pays, grants, refunds, payouts = s["orders"], s["payments"], s["grants"], s["refunds"], s["payouts"]
    issues: list[dict] = []
    rows = []
    for oid, o in orders.items():
        ok_pays = [p for p in pays.values() if p["order_id"] == oid and p["status"] == "succeeded"]
        paid = sum(p["amount"] for p in ok_pays)
        if not ok_pays:
            issues.append({"order_id": oid, "issue": "missing payment: order has no succeeded payment"})
        elif abs(paid - o["price"]) > 1e-9:
            issues.append({"order_id": oid, "issue": f"amount mismatch: order {o['price']}, payments {paid}"})
        grant = grants.get(oid)
        if grant and not ok_pays:
            issues.append({"order_id": oid, "issue": "delivered without a payment"})
        if oid in refunds and grant and grant["active"]:
            issues.append({"order_id": oid, "issue": "refunded but access is still active"})
        rows.append({"order_id": oid, "status": o["status"], "price": o["price"], "currency": o["currency"],
                     "paid": paid, "fees": sum(p.get("fee", 0) for p in ok_pays),
                     "refunded": refunds.get(oid, {}).get("amount", 0), "delivered": bool(grant),
                     "access_active": bool(grant and grant["active"])})
    for eid, p in pays.items():
        if p["order_id"] not in orders:
            issues.append({"order_id": p["order_id"], "issue": f"payment {eid} has no order"})
        if p.get("fee", 0) != 0:
            issues.append({"order_id": p["order_id"], "issue": f"payment {eid} has a non-zero fee"})
    payout_total = sum(x.get("amount", 0) for x in payouts.values())
    if payout_total != 0:
        issues.append({"order_id": None, "issue": f"payouts total {payout_total}, expected 0 (no money moves)"})
    report = {"orders": rows, "issues": issues, "fees_total": sum(r["fees"] for r in rows),
              "payouts_total": payout_total, "mocked": True}
    payments.log("reconcile", "reconcile", orders=len(rows), issues=len(issues))
    return report
