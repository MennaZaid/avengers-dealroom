# Working in parallel: three people, deadline Tuesday 23:59

> Updated 2026-11-17 morning. The submission is whatever is on `main` at the last push before **Tuesday 23:59**.
> The checker finds files by name and heading (`CLAUDE.md` at the repo root). New split: Menna builds Phase 3
> (Build) for real as a multi-agent stage; Abdelrahman (Docker done) takes Phase 2 and stubs Phases 4-6.

## 1. Who does what

| | **A: Menna** | **B: Roufayda** | **C: Abdelrahman** |
|---|---|---|---|
| Area | Onboarding ✅, gates ✅, **Phase 3 Build stage** | Orchestrator, approvals, **Phase 1 Discover** | Docker ✅, **Phase 2 Validate**, phases 4-6 stubs, docs, pitch |
| Scores most on | Working prototype (25), evidence & honesty (15) | Working prototype (25), founder control (15) | Reproducibility (10), architecture (20), pitch (15) |
| Owns these files | `onboarding/`, `api/onboarding.py`, `guardrails.py`, `decision_log.py`, `outputs.py`, `prompts.py`, `gates.py`, **`evidence.py`**, **`build_stage.py`**, **`agents/build_inputs.py`, `agents/requirements_mapper.py`, `agents/mvp_planner.py`, `agents/mvp_validator.py`, `agents/mvp_builder.py`, `agents/mvp_tester.py`, `agents/docs_writer.py`**, `templates/mvp/`, `prompts/brief_*.md`, `prompts/mvp_*.md`, `ui/pages/1_onboarding.py`, `ui/pages/3_decision_log.py` | `orchestrator.py`, `approval.py`, `agents/researcher.py`, `agents/interviewer.py`, `api/stages.py`, `ui/pages/2_pipeline.py`, `prompts/researcher.md`, `prompts/interviewer.md` | `Dockerfile`, `docker-compose.yml`, `.env.example`, `llm/`, `README.md`, `ARCHITECTURE.md`, `.github/`, **`agents/business_designer.py`, `agents/landing_page.py`**, `prompts/business_designer.md`, `prompts/landing_page.md`, `agents/` for phases 4-6, `delivery.py` |

**Shared files:** announce a change before making it. `api/main.py` (one `include_router` line per person),
`db/schema.sql` (append your own section only), `pyproject.toml` (Abdelrahman merges dependency requests),
`ui/common.py` (theme helpers).

### A: Menna

**Done (on `main`):** founder onboarding (Arabic/English chat, documents, versioned brief, product check,
budget parsing, supply side for marketplaces), guardrails (excluded products, must-never requests, redaction,
`check_output()`), decision log (per-session in the UI), outputs naming, prompts loader, brief hand-off
(`load_brief`, `is_stale`), **`gates.py`** (product, evidence and demand gates). 211 tests.

**Now: Phase 3 Build, a multi-agent stage with one founder approval at the end** (built agent by agent,
each merged when its tests pass). No approvals inside the stage: everything needed is collected at the start.

| Step | Agent | What it does | Output |
|---|---|---|---|
| 0 | `build_inputs` (code) | Entry check: confirmed brief + Phase 1/2 evidence items, each labelled evidenced / founder-stated / inferred / assumption; stops if Phase 2 said stop; lists what is missing **at the start** | `phase3_step1_build_inputs.md` |
| 1 | `requirements_mapper` | Evidence -> requirements; each cites its evidence or is marked `ASSUMPTION` / `INFERRED`; priority follows evidence strength | `phase3_step2_requirements.md` |
| 2 | `mvp_planner` | Smallest scope within budget, time, skills; picks one of 5 templates (booking, directory, tracker, content library, calculator); screens, flows, data fields, out of scope | `phase3_step3_mvp_plan.md` |
| 3 | `mvp_validator` | Plan holds together (screens reachable, flows complete, fields used); every feature traces to evidence or is labelled; fits constraints and values; rules first, then one model review; failures go back to the planner (max 2 rounds) | `phase3_step4_validation.md` |
| 4 | `mvp_builder` | Renders the plan into a fixed template; the model writes copy only, never code; Arabic RTL or English | `phase3_step5_mvp.html` (single file) |
| 5 | `mvp_tester` | Opens and works, features present, no outside calls, no password/card fields, `check_output()`, payments MOCKED; failures go back to the builder | `phase3_step6_test_report.md` |
| 6 | `docs_writer` | User guide + "what is evidenced, what is assumed" | `phase3_step7_user_guide.md` |
| Gate | `gates.build_gate` | All pass -> go; still failing -> repeat; excluded or Phase 2 stop -> stop; then the founder approves once | `phase3_gate_build.md` |

Also: demo briefs (one that passes, one that ends in **stop**) and the 3-minute demo script.

### B: Roufayda

Input: the confirmed brief (`load_brief(brief_id)`; fixtures in `tests/fixtures/briefs/`).

1. **`orchestrator.py`**: runs the phase steps in order; a step starts only if the previous gate's outcome is
   `go` **for the same brief version** (`is_stale()`); plain code, not a prompt. Starts with
   `gates.product_gate(brief)`.
2. **`approval.py`**: the founder's approve / reject / revise is the only way past a gate and the only way
   anything is "published" (all publishing MOCKED). Test: nothing goes out without approval.
3. **Phase 1 Discover, core step "Find opportunities"**: `agents/researcher.py` (SearXNG + registry sources;
   every claim has a source URL and date, anything unsourced is labelled `ASSUMPTION`; answer the brief's
   `open_questions`), `agents/interviewer.py` (Mom Test interview script). Then `gates.evidence_gate(...)`.
   Outputs `phase1_step1_opportunities.md`, `phase1_step2_interview_script.md`, `phase1_gate_evidence.md`.
4. `ui/pages/2_pipeline.py`: run a phase, see outputs with sources, approve / reject at each gate.

### C: Abdelrahman

1. ✅ **`docker compose up`** (db, seed, Ollama with `qwen3:4b-instruct`, API, UI). Check on a fresh clone that the
   build doesn't stop at "additional privileges requested (`--allow=fs.read=Dockerfile`)"; warm the model at
   startup (the first answer took ~3 minutes cold, 5-30 s warm).
2. **Phase 2 Validate, core step "Design the business"** (proposed, moved from Menna):
   - `agents/business_designer.py`: Lean Canvas from the brief + Phase 1 evidence; every box is the founder's
     words, a sourced claim, or `ASSUMPTION`. Output `phase2_step1_lean_canvas.md`.
   - `agents/landing_page.py`: landing-page draft (HTML) with a waitlist and a target declared **before** the test
     (`gates.plan_demand_test(100, 14)`); publishing MOCKED; `check_output()` on all text.
   - Sign-up count entered by the founder or labelled MOCKED, then `gates.demand_gate` -> `phase2_gate_demand.md`
     (the required **stop** example: 12 of 100).
   - Write Phase 2 findings as evidence items (`evidence.add(...)`, see Contracts) so Phase 3 can use them.
3. **Phases 4-6 as STUBBED agents** with labelled outputs: Commercial (price hypotheses + draft terms/privacy/
   refund policies), Launch (store page and posts as drafts; `delivery.py` mocked with idempotency), Operate
   (persevere-or-pivot memo).
4. Keep README/ARCHITECTURE status tables in step with `main`; record tokens per call; Postgres in CI; pitch deck
   and ≤3 min backup video (Wednesday 14:00 if we reach the top 5).

## 2. Contracts (ready now)

| What | How |
|---|---|
| Brief | `from venture_os.onboarding.briefs import load_brief, is_stale` -> `brief = load_brief(brief_id)`: `brief.known("budget")` (founder's words or `None`; never fill unknowns), `brief.budget` (`{min, max, currency, currency_source}` or `None`), `brief.tag("country_code")`, `brief.allowed` (False = excluded product: stop), `brief.open_questions` (research questions for Discover), `brief.followups`, `is_stale(brief_id, version_used)`. HTTP: `GET /onboarding/briefs/{id}`. Without a database: `ConfirmedBrief.from_file("tests/fixtures/briefs/nadafa_v1.json")` or `pharmastock_v1.json`. |
| Gates (**ready**, `src/venture_os/gates.py`) | `gates.record(gates.product_gate(brief), brief_id)` before Discover; `gates.record(gates.evidence_gate(1, sources=[url per sourced claim], assumptions=n), brief_id)` after research; `test = gates.plan_demand_test(target=100, days=14)` **before** measuring, then `gates.record(gates.demand_gate(test, actual, days_elapsed, source="founder"), brief_id)`. Outcomes `go` / `repeat` / `pivot` / `stop`; `record()` writes `outputs/phase<N>_gate_<product|evidence|demand>.md` and a log entry. Gates only recommend: the founder's decision goes through `approval.py`. |
| Guardrails | `from venture_os.guardrails import check_output, check_product, redact`. Run `check_output(text)` on every generated text before showing it; block if it returns rules. |
| Prompts | `load_prompt("researcher", query=...)` reads `prompts/researcher.md` (`## System prompt` section, `$placeholders`). |
| Decision log | `log_action("researcher", "find_opportunities", sources=[...], model="qwen3:8b", cost=0, approved_by=None, outcome=..., brief_id=str(brief_id))`. **Always pass `brief_id`**: the UI shows only the current session's entries. |
| Outputs | `write_output(1, 1, "opportunities", markdown)` -> `outputs/phase1_step1_opportunities.md`. **Put `Brief id: <id>` in every file**: the UI lists only outputs containing the session's brief id. |
| Evidence items (**for Phase 1 and 2 to write, Phase 3 to read**) | `from venture_os import evidence` then `evidence.add(brief_id, [evidence.Item(phase=1, kind="pain", text=..., label="evidenced", sources=[url], date="2026-11-17", quote=...)])`; Phase 3 reads `evidence.load(brief_id)`. Labels: `evidenced` (has a source URL), `founder_stated`, `inferred`, `assumption`. |
| Build stage | `from venture_os.build_stage import run_build_stage` -> `run_build_stage(brief_id)` runs steps 0-6 and the build gate, returns the gate decision; the orchestrator then asks the founder once. |
| Model call | `venture_os.llm.client.chat_json(messages)` (Abdelrahman adds profiles; the signature stays). |
| Tests | `tests/conftest.py` redirects the log and outputs to a temp folder; tests never touch the real ones. |

## 3. Timeline (Tuesday)

| When | A: Menna | B: Roufayda | C: Abdelrahman |
|---|---|---|---|
| Now -> 11:00 | Phase 3: evidence contract, entry check, requirements mapper, planner | Orchestrator + approval on the brief fixtures | Phase 2 Lean Canvas + landing page |
| 11:00 -> 14:00 | Validator, builder (5 templates), tester | Phase 1 end to end with `evidence_gate`; writes evidence items | Demand gate -> **stop** example; Phase 2 evidence items |
| 14:00 -> 16:00 | Docs writer, build gate, `run_build_stage`; demo briefs | Orchestrator runs Phases 1-3; pipeline page with approvals | Phases 4-6 stubs; README/ARCHITECTURE in step |
| 16:00 -> 18:00 | Integration with the orchestrator; demo script | Integration | Fresh-clone `docker compose up` check |
| **18:00 feature freeze** | | | |
| 18:00-21:00 | All: empty `decision_log.json`, delete `outputs/`, run the demo with 2 briefs (one passes, one gets **stop**), commit both | | |
| 21:00-23:00 | All: fresh clone -> `docker compose up` -> checklist at the end of `CLAUDE.md`; fixes only | | |
| **by 23:00** | Final merge to `main` and push (one hour of buffer) | | |

## 4. Git

- `main` is the submission. Each person works on a branch (`gates/...`, `pipeline/...`, `repo/...`), pulls
  `main` often, and merges small pieces early; tests and lint must pass.
- Never commit `.env`. Never hand-write `outputs/` or `decision_log.json`.
- Injection test cases for **our own** guardrails are allowed, under `tests/` only (`CLAUDE.md`; confirmed by the organizers on 2026-11-17).
  They target Venture OS's onboarding chat (the brief, budget, confirmation), never the organizers' grading: no text anywhere addresses
  graders, reviewers or scores (that disqualifies the team).
