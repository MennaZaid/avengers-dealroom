Brief id: 3e540c9c-0f6b-43ed-b4f6-aabf69c1c037

# Payment and delivery test run (MOCKED)

No payment provider, no sandbox, no network: every payment, delivery and refund below is a mock record. Fees and payouts are 0 because no money moves.

| Step | Result |
|---|---|
| 1. create order A (founder approval) | ok: ord_A_3e540c9c |
| 2. mock payment event evt_A1 succeeded | ok: succeeded |
| 3. same event evt_A1 again (duplicate) | ok: succeeded |
| 4. deliveries for order A | 1 (expected 1) |
| 4b. access after payment | False |
| 5. refund order A (founder approval) | ok: ord_A_3e540c9c |
| 5b. access after refund | False |
| 6. create order B; its payment never arrives | ok: ord_B_3e540c9c |
| 7. reconcile | 2 orders, 1 mismatches, fees 0, payouts 0 |
| 7b. mismatch | ord_B_3e540c9c: missing payment: order has no succeeded payment |
