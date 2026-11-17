"""Phase 5 Launch, core steps "Open the store; deliver automatically". Posting and payments are MOCKED.

    from venture_os.launch_stage import run_launch_stage
    result = run_launch_stage(brief_id, brief_version)    # -> StageResult(decision, files, stubbed)

No approval inside the stage: the stage API starts it after the founder's Go on Phase 4, and the founder decides on
its gate through POST /stages/runs/{id}/decision.

  step 1  store page draft      phase5_step1_store_page.md    (rule-based draft, labelled STUBBED, nothing posted)
  step 2  launch post drafts    phase5_step2_launch_posts.md  (3 drafts; posting needs the founder's approval, MOCKED)
  step 3  sale-to-cash test     payment_test_log.md           (MOCKED order -> payment -> delivery once -> refund
                                                               -> reconcile; each order/refund only if the founder
                                                               approved that exact payload in approval.py)
  gate                          phase5_gate_launch.md
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from venture_os import gates, payments
from venture_os.agents import launch
from venture_os.decision_log import log_action

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "payment_test.py"
RULE = ("drafts pass the guardrails and the MOCKED sale-to-cash test delivers once, revokes access on refund and "
        "reconciles -> go; the test could not run (no founder approval of the test order) -> repeat")


class StageResult(BaseModel):
    decision: gates.GateDecision
    files: list[str]
    stubbed: list[str] = []


def _scenario():
    spec = importlib.util.spec_from_file_location("payment_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def founder_approved(brief_id: str, action: str, payload: dict) -> dict | None:
    """The stage never approves: it only asks approval.py whether the founder already approved this exact payload."""
    digest = payments.content_hash(payload)
    try:
        from venture_os import approval
        ok = approval.has_founder_approval(brief_id, action, digest)
    except Exception:  # noqa: BLE001 - no database / no approval: not approved
        ok = False
    return {"approved_by": "founder", "action": action, "content_hash": digest} if ok else None


def run_launch_stage(brief_id: str, brief_version: int | None = None, *, brief: Any = None,
                     approve=founder_approved) -> StageResult:
    brief_id = str(brief_id)
    if brief is None:
        from venture_os.onboarding.briefs import load_brief
        brief = load_brief(brief_id, brief_version)
    version = brief_version if brief_version is not None else getattr(brief, "version", None)
    launch.run(brief_id, brief=brief, record_gate=False)

    sc = _scenario()
    steps = sc.run_scenario(brief_id, approve)
    sc.write_log(brief_id, steps)
    results = dict(steps)
    delivered_once = results.get("4. deliveries for order A") == "1 (expected 1)"
    revoked = results.get("5b. access after refund") == "False"
    flagged = any(n == "7b. mismatch" and "missing payment" in r for n, r in steps)
    ran = delivered_once and revoked and flagged
    log_action("launch", "sale_to_cash_test (MOCKED)", sources=[], model=None, cost=0, approved_by=None,
               brief_id=brief_id, brief_version=version, completed=ran, mocked=True)

    common = {"phase": 5, "gate": "launch", "rule": RULE, "decided_at": payments.now()}
    if ran:
        d = gates.GateDecision(outcome="go", reason="Store page and posts are drafts (nothing posted); the MOCKED "
                                                    "sale-to-cash test delivered once, revoked access on refund and "
                                                    "reconciliation flagged the missing payment.", **common)
    else:
        d = gates.GateDecision(outcome="repeat", reason="The MOCKED sale-to-cash test did not complete: the founder "
                                                        "has not approved the test order and refund yet (see "
                                                        "payment_test_log.md). Drafts are ready; nothing was posted.",
                               **common)
    gates.record(d, brief_id, version)
    files = ["phase5_step1_store_page.md", "phase5_step2_launch_posts.md", "payment_test_log.md",
             "phase5_gate_launch.md"]
    return StageResult(decision=d, files=files, stubbed=["store_page_copy (rule-based draft)",
                                                         "launch_posts_copy (rule-based drafts)"])
