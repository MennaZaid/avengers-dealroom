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
    product_spec,
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
    try:  # the approved Validate run's Lean Canvas goes to the model with the Discover findings
        extra_items = list(extra_items or []) + validate_items(brief.brief_id, brief.version)
    except Exception:  # noqa: BLE001, S110 - no database / no approved Validate run
        pass
    from venture_os.llm.client import live_enabled
    require_model = chat_json is not None or live_enabled()  # a model is configured: the MVP must be written by it
    inputs = build_inputs.run(brief, extra_items)
    if not inputs.can_start:
        d = gates.record(gates.build_gate(False, inputs.stop_reason, False, [], 0, 0),
                         inputs.brief_id, inputs.brief_version)
        return BuildResult(brief_id=inputs.brief_id, decision=d, seconds=time.monotonic() - t0)

    reqs = requirements_mapper.run(inputs, **kw)
    spec = product_spec.run(inputs, **kw)  # what is sold, the core action, delivery (validated in code)
    plan =mvp_planner.run(inputs, reqs, **kw)
    rounds = 1
    validation = mvp_validator.run(inputs, reqs, plan, round_no=rounds, **kw)
    while not validation.passed and rounds <= MAX_REPLANS:
        plan = mvp_planner.run(inputs, reqs, feedback=validation.issues, offer_kind=spec.offer_kind, **kw)
        rounds += 1
        validation = mvp_validator.run(inputs, reqs, plan, round_no=rounds, **kw)
    if not validation.passed:  # last resort: the fixed per-template plan
        plan = mvp_planner.run(inputs, reqs, chat_json=_no_model, feedback=validation.issues,
                               offer_kind=spec.offer_kind)
        rounds += 1
        validation = mvp_validator.run(inputs, reqs, plan, round_no=rounds, chat_json=_no_model)

    page = mvp_builder.run(inputs, reqs, plan, spec=spec, **kw)
    tests = mvp_tester.run(inputs, reqs, plan, page, attempt=1, use_browser=use_browser,
                               require_model=require_model)
    attempts = 1
    if not tests.passed:  # 1 repair pass: the failures go back to the spec, copy is fixed
        failed = [f"{c.name}: {c.detail}" for c in tests.checks if not c.passed]
        spec = product_spec.run(inputs, feedback=failed, **kw)
        page = mvp_builder.run(inputs, reqs, plan, chat_json=_no_model, spec=spec)
        attempts = 2
        tests = mvp_tester.run(inputs, reqs, plan, page, attempt=2, use_browser=use_browser,
                               require_model=require_model)
    if not tests.passed and spec.source == "model":  # then rules only; a failure after that is reported as is
        spec = product_spec.run(inputs, chat_json=_no_model, feedback=["rules only"])
        page = mvp_builder.run(inputs, reqs, plan, chat_json=_no_model, spec=spec)
        attempts = 3
        tests = mvp_tester.run(inputs, reqs, plan, page, attempt=3, use_browser=use_browser,
                               require_model=require_model)

    docs_writer.run(inputs, reqs, plan, validation, tests)
    d = gates.record(gates.build_gate(True, None, validation.passed, validation.issues,
                                      sum(c.passed for c in tests.checks), len(tests.checks)),
                     inputs.brief_id, inputs.brief_version)
    secs = time.monotonic() - t0
    log_action("build_stage", "run_build_stage", sources=[], model=None, cost=0, approved_by=None,
               outcome=d.outcome, brief_id=inputs.brief_id, brief_version=inputs.brief_version,
               template=plan.template, offer_kind=spec.offer_kind, plan_rounds=rounds, test_attempts=attempts, seconds=round(secs, 1))
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


# Lean Canvas box -> evidence kind (boxes not listed become "claim")
_BOX_KIND = {"problem": "pain", "customer_segments": "customer", "early_adopters": "customer", "solution": "idea",
             "unique_value_proposition": "idea", "revenue_streams": "revenue", "cost_structure": "constraint",
             "existing_alternatives": "competitor"}
_BASIS_LABEL = {"FOUNDER": "founder_stated", "EVIDENCED": "evidenced", "ASSUMPTION": "assumption",
                "UNKNOWN": "assumption"}


def canvas_to_items(canvas: dict) -> list:
    """The approved Validate run's Lean Canvas -> evidence items, keeping each entry's own basis and source."""
    from venture_os.evidence import Item

    items = []
    for box, entries in (canvas.get("boxes") or {}).items():
        for e in entries or []:
            text = str(e.get("text") or "").strip()
            label = _BASIS_LABEL.get(str(e.get("basis")), "assumption")
            url = e.get("url") if str(e.get("url") or "").startswith(("http://", "https://")) else None
            if not text or text == "-":
                continue
            if label == "evidenced" and not url:
                label = "inferred"
            items.append(Item(phase=2, kind=_BOX_KIND.get(box, "claim"), text=f"lean canvas {box}: {text}"[:400],
                              label=label, sources=[url] if url else [], date=e.get("date")))
    if canvas.get("riskiest_assumption"):
        items.append(Item(phase=2, kind="claim", label="assumption",
                          text=f"lean canvas riskiest assumption: {canvas['riskiest_assumption']}"[:400]))
    return items


def validate_items(brief_id: str, brief_version: int) -> list:
    """The Lean Canvas of the latest approved Validate run for this brief version, as evidence items."""
    from venture_os.api.db import connect

    with connect("vos_app") as conn:
        run = conn.execute("SELECT output FROM stage_runs WHERE brief_id = %s AND brief_version = %s AND stage = "
                           "'validate' AND status = 'approved' ORDER BY created_at DESC LIMIT 1",
                           (brief_id, brief_version)).fetchone()
    canvas = ((run or {}).get("output") or {}).get("validate", {}).get("canvas") or {}
    return canvas_to_items(canvas)


def run_build_stage_for(brief_id: str, **kw) -> BuildResult:
    """Load the latest confirmed brief from the database and run the stage."""
    from venture_os.onboarding.briefs import load_brief

    return run_build_stage(load_brief(brief_id), **kw)
