"""Stage runs, founder decisions and founder-entered interviews. Runs under the vos_app database role.

- POST /stages/{stage}/runs: the entry check (gates.py, plain code) must pass. Discover saves its plan at once
  and runs the agents in the background (orchestrator.py); poll GET /stages/runs/{id}.
- POST /stages/runs/{id}/decision: the ONLY way past a gate (approval.py). Founder-authenticated: the header
  X-Founder-Session must be the onboarding session that confirmed this brief. A model has no such session.
- Validate (Phase 2) starts after an approved Discover for the same brief version. In the background it builds the
  Lean Canvas, then the landing page step, which DECLARES the demand test (target and days) before drafting the
  page (publishing MOCKED). The run then waits for the founder's sign-up count:
  POST /stages/runs/{id}/signups {actual, days_elapsed} runs the demand gate against the declared test; the
  founder then decides through POST /stages/runs/{id}/decision.
- Commercial (Phase 4), Launch (Phase 5: posting and sale-to-cash MOCKED) and Operate (Phase 6) each start after
  the founder's go on the previous phase: <phase>_stage.run_<phase>_stage in the background (STUBBED with a
  'repeat' recommendation until that entry point exists), then the founder's one decision.
- Build (Phase 3) starts after an approved Validate. It runs build_stage.run_build_stage in the background with
  the Discover claims as evidence, stores the gate and every phase3_* file in the run, and waits for the
  founder's one decision.
- POST /stages/discover/interviews: the founder's Mom Test notes (stored as written, tagged by rules); the gate
  is re-evaluated with them.
- POST /stages/approvals: the founder approves one exact draft/payload (publish_landing_page, create_order,
  refund_order) from the UI; GET /stages/approvals/check tells a caller whether that exact content is approved.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from venture_os import approval, discover_report, gates, orchestrator
from venture_os.agents import research_planner
from venture_os.agents.interview_designer import tag_interview
from venture_os.api.db import connect
from venture_os.api.onboarding import get_brief
from venture_os.api.registry import list_sources
from venture_os.evidence.store import EvidenceStore

router = APIRouter(prefix="/stages", tags=["stages"])

RUN_COLS = "id, brief_id, brief_version, stage, status, output, created_at, updated_at"
IMPLEMENTED = {"discover", "validate", "build", "commercial", "launch", "operate"}


class RunIn(BaseModel):
    brief_id: UUID


class DecisionIn(BaseModel):
    decision: gates.Decision          # approve=go, revise=repeat, pivot, reject=stop, waive
    note: str = Field("", max_length=2000)
    pivot_to: str | None = Field(None, max_length=40)        # idea id (I1, I2, ...) or "onboarding"
    waiver_reason: str | None = Field(None, max_length=2000)


class ApprovalIn(BaseModel):
    brief_id: UUID
    action: approval.Action
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")   # SHA-256 of the exact draft or payload
    decision: str = "approve"     # approve | reject; gates (pass_phase<N>_gate): go | repeat | pivot | stop
    note: str | None = Field(None, max_length=2000)
    pivot_to: str | None = Field(None, max_length=60)
    brief_version: int | None = None


class SignupsIn(BaseModel):
    actual: int = Field(ge=0, strict=True)        # the founder's real count; never defaulted or generated
    days_elapsed: int = Field(ge=0, strict=True)


class InterviewIn(BaseModel):
    brief_id: UUID
    person: str = Field(min_length=2, max_length=200)
    held_on: date | None = None
    notes: str = Field(min_length=5, max_length=10000)
    describes_problem: bool = True


def toolbox_factory():
    """Real search/fetch/APIs/store. Tests replace this with offline fakes."""
    return orchestrator.LiveToolbox(), EvidenceStore()


def plan_for(brief: dict) -> research_planner.ResearchPlan:
    cc = (brief.get("tags", {}).get("country_code") or {}).get("value")
    cc = cc if isinstance(cc, str) and cc != "unknown" else None
    sources = list_sources(country=cc, tier=None, use=None, include_inactive=False,
                           product_scope="digital,any")  # = GET /registry/sources?product_scope=digital,any
    return research_planner.build_plan(brief, sources)


def _latest_version(conn, brief_id) -> int | None:
    if not conn.execute("SELECT 1 FROM briefs WHERE id = %s", (brief_id,)).fetchone():
        raise HTTPException(404, "brief not found")
    return conn.execute("SELECT max(version) AS v FROM brief_versions WHERE brief_id = %s",
                        (brief_id,)).fetchone()["v"]


def _with_state(conn, runs: list[dict]) -> list[dict]:
    """Add `stale` and the decision log to each run."""
    if not runs:
        return runs
    latest, decisions = {}, {r["id"]: [] for r in runs}
    for row in conn.execute(
        "SELECT stage_run_id, decision, note, pivot_to, waiver_reason, actor, created_at FROM stage_decisions "
        "WHERE stage_run_id = ANY(%s) ORDER BY id", ([r["id"] for r in runs],)
    ).fetchall():
        decisions[row.pop("stage_run_id")].append(row)
    for r in runs:
        if r["brief_id"] not in latest:
            latest[r["brief_id"]] = conn.execute(
                "SELECT max(version) AS v FROM brief_versions WHERE brief_id = %s", (r["brief_id"],)).fetchone()["v"]
        r["latest_brief_version"] = latest[r["brief_id"]]
        r["stale"] = gates.is_stale(r["brief_version"], r["latest_brief_version"])
        r["decisions"] = decisions[r["id"]]
    return runs


def _research(run_id: str, plan: research_planner.ResearchPlan, brief: dict) -> None:
    toolbox, store = toolbox_factory()
    orchestrator.run_discover(run_id, plan, brief, toolbox, store)


BUILD_FILES = ["phase3_step1_build_inputs.md", "phase3_step2_requirements.md", "phase3_step3_mvp_plan.md",
               "phase3_step4_validation.md", "phase3_step5_mvp.html", "phase3_step6_test_report.md",
               "phase3_step7_user_guide.md", "phase3_step8_evidence_summary.md", "phase3_gate_build.md"]


def _build(run_id: str, brief_id: str, version: int) -> None:
    """Phase 3 in the background: no founder approval inside the stage; the run then waits for one decision.
    The files are copied into the run, so each run keeps its own MVP even when outputs/ is overwritten."""
    from venture_os.build_stage import discover_items, run_build_stage
    from venture_os.onboarding.briefs import load_brief
    from venture_os.outputs import outputs_dir

    store = EvidenceStore()
    try:
        brief = load_brief(brief_id, version)
        result = run_build_stage(brief, extra_items=discover_items(brief_id, version))
        files = {}
        for name in BUILD_FILES:
            f = outputs_dir() / name
            if f.exists():
                files[name] = f.read_text(encoding="utf-8")
        store.update_run(run_id, {"build": {"status": "done", "gate": result.decision.model_dump(),
                                            "template": result.template, "plan_rounds": result.plan_rounds,
                                            "test_attempts": result.test_attempts,
                                            "seconds": round(result.seconds, 1), "files": files}},
                         status="awaiting_approval")
    except Exception as e:  # noqa: BLE001 - a failed run is recorded, not hidden
        store.update_run(run_id, {"build": {"status": "failed", "error": f"{type(e).__name__}: {e}"}},
                         status="failed")


VALIDATE_FILES = ["phase2_step1_lean_canvas.md", "phase2_step2_demand_test_plan.md", "phase2_step2_landing_page.html",
                  "phase2_gate_demand.md"]


def _files(names: list[str]) -> dict[str, str]:
    from venture_os.outputs import outputs_dir

    return {n: (outputs_dir() / n).read_text(encoding="utf-8") for n in names if (outputs_dir() / n).is_file()}


def _validate(run_id: str, brief_id: str, version: int) -> None:
    """Phase 2 in the background, in this order: Lean Canvas -> demand test DECLARED (target and days fixed
    before any number exists) -> landing-page draft (publishing MOCKED). Then the run waits for the founder's
    sign-up count; no gate decision is made here."""
    from venture_os.agents import business_designer, landing_page
    from venture_os.build_stage import discover_items
    from venture_os.onboarding.briefs import load_brief

    store = EvidenceStore()
    try:
        brief = load_brief(brief_id, version)
        store.update_run(run_id, {"validate": {"status": "lean_canvas"}})
        canvas = business_designer.run(brief_id, brief=brief, evidence_items=discover_items(brief_id, version) or None)
        store.update_run(run_id, {"validate": {"status": "landing_page", "canvas": canvas.model_dump()}})
        draft = landing_page.run(brief_id, canvas, brief=brief)  # declares the demand test first
        store.update_run(run_id, {"validate": {
            "status": "awaiting_signups", "canvas": canvas.model_dump(),
            "canvas_md": business_designer.to_markdown(canvas), "demand_test": draft.demand_test,
            "draft": {**draft.model_dump(exclude={"html"}), "publishing": "MOCKED"}, "draft_html": draft.html,
            "files": _files(VALIDATE_FILES)}})
    except Exception as e:  # noqa: BLE001 - a failed run is recorded, not hidden
        store.update_run(run_id, {"validate": {"status": "failed", "error": f"{type(e).__name__}: {e}"}},
                         status="failed")


# Phases 4-6: one entry point each (owned by the phase's author), run in the background with no approval inside
# the stage; the run then waits for the founder's one decision. A missing entry point gives a STUBBED run with a
# 'repeat' recommendation, never a pass. stage -> (phase, module, function, what it would have produced)
LATER_STAGES = {
    "commercial": (4, "commercial_stage", "run_commercial_stage", "No price or policy was produced."),
    "launch": (5, "launch_stage", "run_launch_stage",
               "No store page or launch post was drafted; nothing was posted or sold (MOCKED)."),
    "operate": (6, "operate_stage", "run_operate_stage", "No persevere-or-pivot memo was written."),
}


def _later_stage(stage: str, run_id: str, brief_id: str, version: int) -> None:
    import importlib

    phase, module, func, missing = LATER_STAGES[stage]
    store = EvidenceStore()
    try:
        try:
            run_stage = getattr(importlib.import_module(f"venture_os.{module}"), func)
        except (ImportError, AttributeError):
            gate = gates.GateDecision(
                phase=phase, gate=stage, outcome="repeat", rule=f"STUBBED: no Phase {phase} entry point",
                reason=f"STUBBED: the Phase {phase} agents ({module}.{func}) are not on main yet. {missing}",
                decided_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
            store.update_run(run_id, {stage: {"status": "done", "gate": gate.model_dump(), "files": {},
                                              "stubbed": [f"all Phase {phase} steps"]}}, status="awaiting_approval")
            return
        result = run_stage(brief_id, version)
        store.update_run(run_id, {stage: {
            "status": "done", "gate": result.decision.model_dump(), "files": _files(list(result.files)),
            "stubbed": list(getattr(result, "stubbed", []) or [])}}, status="awaiting_approval")
    except Exception as e:  # noqa: BLE001 - a failed run is recorded, not hidden
        store.update_run(run_id, {stage: {"status": "failed", "error": f"{type(e).__name__}: {e}"}}, status="failed")


@router.get("/briefs")
def list_briefs():
    """Confirmed briefs (latest version of each), newest first, for picking one in the UI."""
    with connect("vos_app") as conn:
        return conn.execute(
            "SELECT * FROM (SELECT DISTINCT ON (brief_id) brief_id, version, fields->'idea'->>'value' AS idea, "
            "tags->'country_code'->>'value' AS country_code, created_at FROM brief_versions "
            "ORDER BY brief_id, version DESC) b ORDER BY created_at DESC"
        ).fetchall()


@router.post("/{stage}/runs", status_code=201)
def start_run(stage: gates.Stage, body: RunIn, background: BackgroundTasks):
    with connect("vos_app") as conn:
        latest = _latest_version(conn, body.brief_id)
        runs = conn.execute("SELECT stage, brief_version, status FROM stage_runs WHERE brief_id = %s",
                            (body.brief_id,)).fetchall()
        try:
            gates.entry_check(stage, latest, [gates.RunView(**r) for r in runs],
                              skip=[s for s in gates.STAGES if s not in IMPLEMENTED])
        except gates.GateRefused as e:
            raise HTTPException(403, str(e)) from e
    if stage not in IMPLEMENTED:
        raise HTTPException(501, f"entry check passed, but the {stage} workflow is not built yet")
    brief = get_brief(body.brief_id)  # the onboarding contract: latest confirmed version
    if (brief.get("product_check") or {}).get("status") == "excluded":
        raise HTTPException(403, "excluded product (not a digital product the system may build): the pipeline "
                                 "stops here; reshape the idea in onboarding")
    if stage in LATER_STAGES:
        with connect("vos_app") as conn:
            run = conn.execute(
                f"INSERT INTO stage_runs (brief_id, brief_version, stage, status, output) VALUES (%s,%s,%s,%s,%s) "
                f"RETURNING {RUN_COLS}", (body.brief_id, brief["version"], stage, "running",
                                          Jsonb({stage: {"status": "queued"}}))).fetchone()
            out = _with_state(conn, [run])[0]
        background.add_task(_later_stage, stage, str(run["id"]), str(body.brief_id), brief["version"])
        return out
    if stage == "validate":
        with connect("vos_app") as conn:
            run = conn.execute(
                f"INSERT INTO stage_runs (brief_id, brief_version, stage, status, output) VALUES (%s,%s,%s,%s,%s) "
                f"RETURNING {RUN_COLS}", (body.brief_id, brief["version"], stage, "running",
                                          Jsonb({"validate": {"status": "queued"}}))).fetchone()
            out = _with_state(conn, [run])[0]
        background.add_task(_validate, str(run["id"]), str(body.brief_id), brief["version"])
        return out
    if stage == "build":
        with connect("vos_app") as conn:
            run = conn.execute(
                f"INSERT INTO stage_runs (brief_id, brief_version, stage, status, output) VALUES (%s,%s,%s,%s,%s) "
                f"RETURNING {RUN_COLS}", (body.brief_id, brief["version"], stage, "running",
                                          Jsonb({"build": {"status": "queued"}}))).fetchone()
            out = _with_state(conn, [run])[0]
        background.add_task(_build, str(run["id"]), str(body.brief_id), brief["version"])
        return out
    try:
        plan = plan_for(brief)
        output, status = {"plan": plan.model_dump(), "research": {"status": "queued", "trace": []}}, "running"
    except Exception as e:  # noqa: BLE001 - a failed run is recorded, not hidden
        plan, output, status = None, {"error": f"{type(e).__name__}: {e}"}, "failed"
    with connect("vos_app") as conn:
        run = conn.execute(
            f"INSERT INTO stage_runs (brief_id, brief_version, stage, status, output) VALUES (%s,%s,%s,%s,%s) "
            f"RETURNING {RUN_COLS}", (body.brief_id, brief["version"], stage, status, Jsonb(output))).fetchone()
        out = _with_state(conn, [run])[0]
    if plan is not None:
        background.add_task(_research, str(run["id"]), plan, brief)
    return out


@router.get("/runs")
def list_runs(brief_id: UUID, stage: gates.Stage | None = None):
    with connect("vos_app") as conn:
        _latest_version(conn, brief_id)
        sql, args = f"SELECT {RUN_COLS} FROM stage_runs WHERE brief_id = %s", [brief_id]
        if stage:
            sql += " AND stage = %s"
            args.append(stage)
        return _with_state(conn, conn.execute(sql + " ORDER BY created_at DESC", args).fetchall())


@router.get("/runs/{run_id}")
def get_run(run_id: UUID):
    with connect("vos_app") as conn:
        run = conn.execute(f"SELECT {RUN_COLS} FROM stage_runs WHERE id = %s", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "run not found")
        return _with_state(conn, [run])[0]


@router.get("/runs/{run_id}/claims")
def run_claims(run_id: UUID):
    """The run's claims as stored in Postgres, each joined to its stored document."""
    with connect("vos_app") as conn:
        return conn.execute(
            "SELECT c.id, c.topic, c.agent, c.text, c.type, c.quote, c.language, c.flags, c.extracted_by, "
            "d.url, d.title, d.published_at, d.retrieved_at, d.source_id FROM claims c "
            "LEFT JOIN documents d ON d.id = c.document_id WHERE c.stage_run_id = %s ORDER BY c.topic, c.created_at",
            (run_id,)).fetchall()


@router.post("/runs/{run_id}/decision")
def decide(run_id: UUID, body: DecisionIn, x_founder_session: str | None = Header(None)):
    """The founder's decision at a gate: approve (go), revise (repeat), pivot (to an idea), reject (stop), or
    waive (go despite missing interviews, reason required)."""
    with connect("vos_app") as conn:
        run = conn.execute(f"SELECT {RUN_COLS} FROM stage_runs WHERE id = %s FOR UPDATE", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "run not found")
        if not approval.founder_owns_brief(conn, run["brief_id"], x_founder_session):
            raise HTTPException(401, "only the founder can decide: send the onboarding session that confirmed "
                                     "this brief as X-Founder-Session")
        try:
            approval.record_decision(conn, run, body.decision, body.note, actor=approval.FOUNDER,
                                     pivot_to=body.pivot_to, waiver_reason=body.waiver_reason)
        except gates.GateRefused as e:
            raise HTTPException(409, str(e)) from e
        out = _with_state(conn, [conn.execute(f"SELECT {RUN_COLS} FROM stage_runs WHERE id = %s",
                                              (run_id,)).fetchone()])[0]
    if out["stage"] == "discover":
        research = (out.get("output") or {}).get("research") or {}
        discover_report.write_gate(str(run_id), research, {
            "decision": body.decision, "outcome": gates.OUTCOME[body.decision], "note": body.note,
            "pivot_to": body.pivot_to, "waiver_reason": body.waiver_reason})
    return out


@router.post("/discover/interviews", status_code=201)
def add_interview(body: InterviewIn, x_founder_session: str | None = Header(None)):
    """Store one founder-entered interview exactly as written, tag its lines by rules, and re-evaluate the gate
    of the brief's latest Discover run."""
    with connect("vos_app") as conn:
        if not approval.founder_owns_brief(conn, body.brief_id, x_founder_session):
            raise HTTPException(401, "only the founder can enter interviews (X-Founder-Session)")
        tagged = [n.model_dump() for n in tag_interview(body.notes)]
        row = conn.execute(
            "INSERT INTO discover_interviews (brief_id, person, held_on, notes, tagged, describes_problem) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, person, held_on, tagged, describes_problem, created_at",
            (body.brief_id, body.person, body.held_on, body.notes, Jsonb(tagged), body.describes_problem)).fetchone()
        run = conn.execute(f"SELECT {RUN_COLS} FROM stage_runs WHERE brief_id = %s AND stage = 'discover' "
                           "ORDER BY created_at DESC LIMIT 1", (body.brief_id,)).fetchone()
    regated = _regate(run) if run and run["status"] in ("awaiting_approval", "revision_requested") else None
    return {"interview": row, "noise": [n for n in tagged if not n["counts"]],
            "gate": regated["gate"] if regated else None}


@router.get("/discover/interviews")
def list_interviews(brief_id: UUID):
    with connect("vos_app") as conn:
        return conn.execute("SELECT id, person, held_on, notes, tagged, describes_problem, type, created_at "
                            "FROM discover_interviews WHERE brief_id = %s ORDER BY created_at", (brief_id,)).fetchall()


def _regate(run: dict) -> dict:
    store = EvidenceStore()
    result = orchestrator.regate(run, store.interviews(str(run["brief_id"])))
    output = run["output"]
    output["research"].update(gate=result["gate"], interviews=result["interviews"])
    store.update_run(run["id"], output)
    discover_report.write_gate(str(run["id"]), output["research"])
    return result


@router.post("/approvals", status_code=201)
def approve_content(body: ApprovalIn, x_founder_session: str | None = Header(None)):
    """The founder approves exactly this content for one outward action (UI channel)."""
    with connect("vos_app") as conn:
        try:
            return approval.record_founder_approval(body.brief_id, body.action, body.content_hash, body.decision,
                                                    body.note, session_id=x_founder_session or "", channel="ui",
                                                    pivot_to=body.pivot_to, brief_version=body.brief_version,
                                                    conn=conn)
        except PermissionError as e:
            raise HTTPException(401, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e


@router.get("/approvals/check")
def check_approval(brief_id: UUID, action: str, content_hash: str):
    return {"approved": approval.has_founder_approval(brief_id, action, content_hash),
            "decision": approval.founder_decision(brief_id, action, content_hash)}


@router.post("/runs/{run_id}/signups")
def enter_signups(run_id: UUID, body: SignupsIn, x_founder_session: str | None = Header(None)):
    """The founder's waitlist sign-up count for a Validate run. Runs the demand gate against the test declared
    before the landing page was drafted, stores the gate in the run, and opens the founder's decision."""
    from venture_os.agents import demand_test

    with connect("vos_app") as conn:
        run = conn.execute(f"SELECT {RUN_COLS} FROM stage_runs WHERE id = %s FOR UPDATE", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "run not found")
        if not approval.founder_owns_brief(conn, run["brief_id"], x_founder_session):
            raise HTTPException(401, "only the founder can enter the sign-up count (X-Founder-Session)")
        if run["stage"] != "validate":
            raise HTTPException(409, "sign-ups belong to a Validate run")
        v = (run["output"] or {}).get("validate") or {}
        if not v.get("demand_test") or run["status"] not in ("running", "awaiting_approval", "revision_requested"):
            raise HTTPException(409, "this run is not waiting for sign-ups (the demand test must be declared first)")
    test = gates.DemandTest(**v["demand_test"])
    try:
        d = demand_test.enter_signups(str(run["brief_id"]), body.actual, body.days_elapsed, test=test,
                                      brief_version=run["brief_version"])
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    v.update(status="gated", gate=d.model_dump(), signups={"actual": body.actual, "days_elapsed": body.days_elapsed,
                                                          "source": "founder", "label": demand_test.FOUNDER_LABEL},
             files={**(v.get("files") or {}), **_files(["phase2_gate_demand.md"])})
    EvidenceStore().update_run(str(run_id), {"validate": v}, status="awaiting_approval")
    with connect("vos_app") as conn:
        return _with_state(conn, [conn.execute(f"SELECT {RUN_COLS} FROM stage_runs WHERE id = %s",
                                               (run_id,)).fetchone()])[0]
