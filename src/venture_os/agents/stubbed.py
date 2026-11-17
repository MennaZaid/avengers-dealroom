"""Shared plumbing for the thin (STUBBED) agents of phases 4-6: labelled outputs, guardrails, gates, approval.

- Every output starts with "Brief id: <id>" and then a STUBBED label line.
- Every text goes through landing_page.banned() (check_output + no income, urgency, reviews, user counts).
- Each phase ends in a gate written with gates.record(); a gate only recommends. pass_gate() lets the pipeline
  past it only with a founder approval of that exact decision confirmed by approval.py (fails closed).
"""

from __future__ import annotations

import hashlib
import importlib
import json
from datetime import UTC, datetime

from venture_os import gates
from venture_os.agents.landing_page import banned
from venture_os.decision_log import log_action
from venture_os.outputs import write_output

STUB_LABEL = ("**STUBBED:** thin prototype step. Built by rules from logged results and the founder's brief; "
              "nothing here is published, sent, spent or signed.")


def header(brief_id: str, title: str) -> list[str]:
    return [f"Brief id: {brief_id}", "", STUB_LABEL, "", f"# {title}", ""]


def cell(text: object) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def write_checked(phase: int, step: int, name: str, md: str) -> None:
    """Refuse to write text that breaks a must-never rule."""
    if rule := banned(md):
        raise RuntimeError(f"{name} failed the output guardrail: {rule}")
    write_output(phase, step, name, md)


def record_gate(phase: int, name: str, outcome: gates.Outcome, reason: str, rule: str,
                brief_id: str, evidence: list[str] | None = None) -> gates.GateDecision:
    d = gates.GateDecision(phase=phase, gate=name, outcome=outcome, reason=reason, rule=rule,
                           evidence=evidence or [], decided_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return gates.record(d, brief_id)


def decision_hash(d: gates.GateDecision) -> str:
    return hashlib.sha256(json.dumps(d.model_dump(), sort_keys=True).encode("utf-8")).hexdigest()


def pass_gate(brief_id: str, d: gates.GateDecision, approval: dict | None) -> bool:
    """True only if the founder approved passing exactly this gate decision (confirmed by approval.py).
    TODO(approval.py): needs has_founder_approval(brief_id, action, content_hash) -> bool (not on main yet)."""
    action, digest = f"pass_phase{d.phase}_gate", decision_hash(d)
    reason = None
    if not approval or approval.get("approved_by") != "founder" or approval.get("action") != action \
            or approval.get("content_hash") != digest:
        reason = "no founder approval for this gate decision"
    else:
        try:
            check = getattr(importlib.import_module("venture_os.approval"), "has_founder_approval", None)
            if check is None:
                reason = "approval.py has no has_founder_approval() yet"
            elif check(brief_id=brief_id, action=action, content_hash=digest) is not True:
                reason = "approval.py has no founder approval for this gate decision"
        except ImportError:
            reason = "approval.py is not available, so no founder approval can be verified"
    if reason:
        log_action("gate", f"phase{d.phase}_gate_pass_refused", sources=[], model=None, cost=0, approved_by=None,
                   brief_id=brief_id, outcome=d.outcome, reason=reason)
        raise PermissionError(f"phase {d.phase} gate not passed: {reason}")
    log_action("gate", f"phase{d.phase}_gate_passed", sources=[], model=None, cost=0, approved_by="founder",
               brief_id=brief_id, outcome=d.outcome, recommendation_overridden=d.outcome != "go")
    return True


def log_step(agent: str, action: str, brief_id: str, sources: list[str] | None = None, **extra) -> None:
    log_action(agent, action, sources=sources or [], model=None, cost=0, approved_by=None, brief_id=brief_id,
               stubbed=True, **extra)
