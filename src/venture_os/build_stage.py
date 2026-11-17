"""Phase 3 (Build): runs the whole stage with no founder approval inside it; one gate at the end.

    from venture_os.build_stage import run_build_stage
    result = run_build_stage(brief)          # a ConfirmedBrief (or run_build_stage_for(brief_id))
    result.decision.outcome                  # go / repeat / stop -> the founder approves once (approval.py)

Steps: entry check -> requirements -> plan -> validation (failures go back to the planner, at most 2 re-plans)
-> build -> tests (a failure rebuilds with fixed copy and tests again) -> user guide + evidence summary -> gate.
Every step writes its outputs/phase3_* file and a decision_log.json entry.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from pydantic import BaseModel

from venture_os import gates
from venture_os.agents import (
    build_inputs,
    docs_writer,
    mvp_builder,
    mvp_planner,
    mvp_tester,
    mvp_validator,
    requirements_mapper,
)
from venture_os.decision_log import log_action

MAX_REPLANS = 2


class BuildResult(BaseModel):
    brief_id: str
    decision: gates.GateDecision
    template: str | None = None
    plan_rounds: int = 0
    test_attempts: int = 0
    seconds: float = 0.0


def _no_model(messages):  # forces the builder's fixed copy on a rebuild
    raise RuntimeError("fixed copy")


def run_build_stage(brief, chat_json: Callable[[list[dict]], str] | None = None, model: str | None = None,
                    use_browser: bool | None = None, extra_items: list | None = None) -> BuildResult:
    """`extra_items`: Phase 1-2 findings handed over directly (see discover_items)."""
    t0 = time.monotonic()
    kw = {"chat_json": chat_json, "model": model}
    inputs = build_inputs.run(brief, extra_items)
    if not inputs.can_start:
        d = gates.record(gates.build_gate(False, inputs.stop_reason, False, [], 0, 0),
                         inputs.brief_id, inputs.brief_version)
        return BuildResult(brief_id=inputs.brief_id, decision=d, seconds=time.monotonic() - t0)

    reqs = requirements_mapper.run(inputs, **kw)
    plan = mvp_planner.run(inputs, reqs, **kw)
    rounds = 1
    validation = mvp_validator.run(inputs, reqs, plan, round_no=rounds, **kw)
    while not validation.passed and rounds <= MAX_REPLANS:
        plan = mvp_planner.run(inputs, reqs, feedback=validation.issues, **kw)
        rounds += 1
        validation = mvp_validator.run(inputs, reqs, plan, round_no=rounds, **kw)
    if not validation.passed:  # last resort: the fixed per-template plan
        plan = mvp_planner.run(inputs, reqs, chat_json=_no_model, feedback=validation.issues)
        rounds += 1
        validation = mvp_validator.run(inputs, reqs, plan, round_no=rounds, chat_json=_no_model)

    page = mvp_builder.run(inputs, reqs, plan, **kw)
    tests = mvp_tester.run(inputs, reqs, plan, page, attempt=1, use_browser=use_browser)
    attempts = 1
    if not tests.passed:
        page = mvp_builder.run(inputs, reqs, plan, chat_json=_no_model)
        attempts = 2
        tests = mvp_tester.run(inputs, reqs, plan, page, attempt=2, use_browser=use_browser)

    docs_writer.run(inputs, reqs, plan, validation, tests)
    d = gates.record(gates.build_gate(True, None, validation.passed, validation.issues,
                                      sum(c.passed for c in tests.checks), len(tests.checks)),
                     inputs.brief_id, inputs.brief_version)
    secs = time.monotonic() - t0
    log_action("build_stage", "run_build_stage", sources=[], model=None, cost=0, approved_by=None,
               outcome=d.outcome, brief_id=inputs.brief_id, brief_version=inputs.brief_version,
               template=plan.template, plan_rounds=rounds, test_attempts=attempts, seconds=round(secs, 1))
    return BuildResult(brief_id=inputs.brief_id, decision=d, template=plan.template, plan_rounds=rounds,
                       test_attempts=attempts, seconds=secs)


# Discover claim topic -> evidence kind
_TOPIC_KIND = {"pain": "pain", "customer_pain": "pain", "competitors": "competitor", "pricing": "price",
               "market_size": "market", "demand": "demand", "customers": "customer"}


def claims_to_items(claims: list[dict]) -> list:
    """Discover claims (rows of the `claims` table joined to their document) -> evidence items.
    A sourced fact whose quote was found and is not stale is EVIDENCED; other facts and inferences are INFERRED;
    assumptions stay ASSUMPTION. Nothing is upgraded."""
    from venture_os.evidence import Item

    items = []
    for c in claims:
        flags = set(c.get("flags") or [])
        if c.get("type") == "fact" and c.get("url") and not flags & {"quote_not_found", "stale"}:
            label = "evidenced"
        elif c.get("type") in ("fact", "inference"):
            label = "inferred"
        else:
            label = "assumption"
        topic = str(c.get("topic") or "")
        items.append(Item(phase=1, kind=_TOPIC_KIND.get(topic, "claim"), text=f"{topic}: {c.get('text', '')}"[:400],
                          label=label, sources=[c["url"]] if c.get("url") else [],
                          date=str(c.get("published_at") or c.get("retrieved_at") or "")[:10] or None,
                          quote=(c.get("quote") or None)))
    return items


def discover_items(brief_id: str, brief_version: int) -> list:
    """Claims of the latest approved Discover run for this brief version, as evidence items."""
    from venture_os.api.db import connect

    with connect("vos_app") as conn:
        run = conn.execute("SELECT id FROM stage_runs WHERE brief_id = %s AND brief_version = %s AND stage = "
                           "'discover' AND status = 'approved' ORDER BY created_at DESC LIMIT 1",
                           (brief_id, brief_version)).fetchone()
        if not run:
            return []
        rows = conn.execute(
            "SELECT c.topic, c.text, c.type, c.quote, c.flags, d.url, d.published_at, d.retrieved_at FROM claims c "
            "LEFT JOIN documents d ON d.id = c.document_id WHERE c.stage_run_id = %s ORDER BY c.created_at",
            (run["id"],)).fetchall()
    return claims_to_items(rows)


def run_build_stage_for(brief_id: str, **kw) -> BuildResult:
    """Load the latest confirmed brief from the database and run the stage."""
    from venture_os.onboarding.briefs import load_brief

    return run_build_stage(load_brief(brief_id), **kw)
