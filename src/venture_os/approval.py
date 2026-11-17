"""Approval: the ONLY way a gate decision is recorded. Plain code; a model can never call this successfully.

- The caller must be the founder: the API passes actor="founder" only after checking the founder's onboarding
  session owns the brief (X-Founder-Session). Any other actor raises PermissionError, and the database refuses
  any actor other than 'founder' (CHECK constraint on stage_decisions.actor).
- pivot needs the idea to pivot to (an idea id from the run, or "onboarding" to reshape the idea);
  waive needs a reason and is allowed only when the only failing gate checks are the interview checks.
- Every decision is appended to stage_decisions (append-only) and to decision_log.json with
  approved_by="founder" and the gate outcome; nothing is ever published, sent or spent here.

Outward actions (publish_landing_page, create_order, refund_order) need a founder approval of the EXACT content:

    h = approval.content_hash(draft_html)                          # SHA-256 of the exact draft or payload
    if not approval.has_founder_approval(brief_id, "publish_landing_page", h):
        raise PermissionError("not approved by the founder")      # caller must stop here

record_founder_approval() is called only by the UI (POST /approvals, founder session header) or the CLI
(`python -m venture_os.approval ...`, the founder types "approve"). It needs the founder's onboarding session;
the database also refuses any other actor, channel or session (founder_approvals table + trigger).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from typing import Literal
from uuid import UUID

from venture_os.decision_log import log_action
from venture_os.gates import OUTCOME, GateRefused, apply_decision, can_waive

FOUNDER = "founder"
ACTIONS = ("publish_landing_page", "create_order", "refund_order")
Action = Literal["publish_landing_page", "create_order", "refund_order"]
Channel = Literal["ui", "cli"]
_HASH = re.compile(r"^[0-9a-f]{64}$")


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


# ---------------------------------------------------------------- outward actions: exact-content approvals

def content_hash(content: str | bytes) -> str:
    """SHA-256 (hex) of the exact draft or payload. str is hashed as UTF-8."""
    return hashlib.sha256(content.encode("utf-8") if isinstance(content, str) else content).hexdigest()


def _check(action: str, content_hash: str) -> None:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}; expected one of {', '.join(ACTIONS)}")
    if not isinstance(content_hash, str) or not _HASH.match(content_hash):
        raise ValueError("content_hash must be the SHA-256 hex digest (64 lowercase hex characters)")


def record_founder_approval(brief_id: UUID | str, action: Action, content_hash: str, *, session_id: str,
                            channel: Channel, conn=None) -> dict:
    """Store the founder's approval of one exact draft/payload. Only the UI and the CLI call this, with the
    founder's onboarding session; anything else raises PermissionError. Returns the stored row."""
    _check(action, content_hash)
    if channel not in ("ui", "cli"):
        raise PermissionError("approvals are made by the founder in the UI or the CLI only")
    if conn is None:
        from venture_os.api.db import connect

        with connect("vos_app") as c:
            return record_founder_approval(brief_id, action, content_hash, session_id=session_id,
                                           channel=channel, conn=c)
    if not founder_owns_brief(conn, brief_id, session_id):
        raise PermissionError("only the founder can approve: the session must be the one that confirmed this brief")
    row = conn.execute("INSERT INTO founder_approvals (brief_id, action, content_hash, actor, channel, session_id) "
                       "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, created_at",
                       (str(brief_id), action, content_hash, FOUNDER, channel, session_id)).fetchone()
    rid, created = (row["id"], row["created_at"]) if isinstance(row, dict) else row
    log_action("founder", f"approve_{action}", sources=[], model=None, cost=0.0, approved_by=FOUNDER,
               brief_id=str(brief_id), content_hash=content_hash, channel=channel)
    return {"id": rid, "brief_id": str(brief_id), "action": action, "content_hash": content_hash,
            "channel": channel, "created_at": str(created)}


def has_founder_approval(brief_id: UUID | str, action: str, content_hash: str, conn=None) -> bool:
    """True only if the founder approved exactly this content for this action and brief. Never raises on bad
    input: anything malformed is simply not approved."""
    try:
        _check(action, content_hash)
        UUID(str(brief_id))
    except ValueError:
        return False
    if conn is None:
        from venture_os.api.db import connect

        with connect("vos_app") as c:
            return has_founder_approval(brief_id, action, content_hash, conn=c)
    return conn.execute("SELECT 1 FROM founder_approvals WHERE brief_id = %s AND action = %s AND content_hash = %s "
                        "AND actor = %s LIMIT 1", (str(brief_id), action, content_hash, FOUNDER)).fetchone() is not None


def main(argv: list[str] | None = None, stdin=None, stdout=None) -> int:
    """CLI: python -m venture_os.approval --brief ID --action publish_landing_page --file draft.html --session SID
    Shows the hash and the start of the content; the founder must type "approve" at an interactive terminal."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    p = argparse.ArgumentParser(prog="python -m venture_os.approval", description=main.__doc__)
    p.add_argument("--brief", required=True)
    p.add_argument("--action", required=True, choices=ACTIONS)
    p.add_argument("--file", required=True, help="the exact draft or payload file to approve")
    p.add_argument("--session", required=True, help="your founder session id (from onboarding)")
    a = p.parse_args(argv)
    if not stdin.isatty():
        print("Refused: approve at an interactive terminal (input cannot be piped).", file=stdout)
        return 2
    with open(a.file, "rb") as f:
        data = f.read()
    h = content_hash(data)
    preview = data[:600].decode("utf-8", errors="replace")
    print(f"Action: {a.action}", f"Brief: {a.brief}", f"SHA-256: {h}", "--- start of content ---", preview, "---",
          sep="\n", file=stdout)
    print('Type "approve" to approve exactly this content (anything else cancels): ', end="", file=stdout,
          flush=True)
    if stdin.readline().strip() != "approve":
        print("Cancelled: nothing approved.", file=stdout)
        return 1
    try:
        rec = record_founder_approval(a.brief, a.action, h, session_id=a.session, channel="cli")
    except PermissionError as e:
        print(f"Refused: {e}", file=stdout)
        return 3
    print(f"Approved ({rec['action']}, {h[:12]}...) at {rec['created_at']}.", file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
