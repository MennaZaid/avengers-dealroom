"""Approval: the ONLY way a gate decision is recorded. Plain code; a model can never call this successfully.

- The caller must be the founder: the API passes actor="founder" only after checking the founder's onboarding
  session owns the brief (X-Founder-Session). Any other actor raises PermissionError, and the database refuses
  any actor other than 'founder' (CHECK constraint on stage_decisions.actor).
- pivot needs the idea to pivot to (an idea id from the run, or "onboarding" to reshape the idea);
  waive needs a reason and is allowed only when the only failing gate checks are the interview checks.
- Every decision is appended to stage_decisions (append-only) and to decision_log.json with
  approved_by="founder" and the gate outcome; nothing is ever published, sent or spent here.
"""

from __future__ import annotations

from uuid import UUID

from venture_os.decision_log import log_action
from venture_os.gates import OUTCOME, GateRefused, apply_decision, can_waive

FOUNDER = "founder"


def founder_owns_brief(conn, brief_id: UUID | str, session_id: str | None) -> bool:
    if not session_id:
        return False
    try:
        UUID(str(session_id))
    except ValueError:
        return False
    return conn.execute("SELECT 1 FROM onboarding_sessions WHERE id = %s AND brief_id = %s",
                        (session_id, brief_id)).fetchone() is not None


def record_decision(conn, run: dict, decision: str, note: str, actor: str, pivot_to: str | None = None,
                    waiver_reason: str | None = None) -> str:
    """Validate and store one founder decision; returns the run's new status. `conn` holds the run row lock."""
    if actor != FOUNDER:
        raise PermissionError("only the founder can record a gate decision")
    status = apply_decision(run["status"], decision)
    research = (run.get("output") or {}).get("research") or {}
    gate = research.get("gate") or {}
    if decision == "pivot":
        ideas = {i["id"] for i in research.get("ideas") or []}
        if not pivot_to or (pivot_to not in ideas and pivot_to != "onboarding"):
            raise GateRefused("pivot needs the idea to pivot to (an idea id from this run, or 'onboarding')")
    if decision == "waive":
        if not waiver_reason or len(waiver_reason.strip()) < 10:
            raise GateRefused("a waiver needs a reason (at least 10 characters)")
        ok, why = can_waive(gate)
        if not ok:
            raise GateRefused(why)
    conn.execute("INSERT INTO stage_decisions (stage_run_id, decision, note, actor, pivot_to, waiver_reason) "
                 "VALUES (%s,%s,%s,%s,%s,%s)", (run["id"], decision, note, actor, pivot_to, waiver_reason))
    conn.execute("UPDATE stage_runs SET status = %s, updated_at = now() WHERE id = %s", (status, run["id"]))
    log_action("gate", f"{run['stage']}_gate_decision", sources=[], model=None, cost=0.0, approved_by=FOUNDER,
               decision=decision, outcome=OUTCOME[decision], recommendation=gate.get("recommendation"),
               pivot_to=pivot_to, waiver_reason=waiver_reason, note=note, run_id=str(run["id"]),
               brief_version=run["brief_version"])
    return status
