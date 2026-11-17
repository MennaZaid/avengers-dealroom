# Working in parallel: three people, deadline Tuesday 23:59

> Updated 2026-11-17 03:00. The submission is whatever is on `main` at the last push before **Tuesday 23:59**.
> The checker finds files by name and heading (`CLAUDE.md` at the repo root). Onboarding is complete, so the
> roles below are re-balanced: Menna takes the gates and Phase 2 from Roufayda.

## 1. Who does what

| | **A: Menna** | **B: Roufayda** | **C: Abdelrahman** |
|---|---|---|---|
| Area | Onboarding ✅ + **gates + Phase 2 Validate** | Orchestrator, approvals, **Phase 1 Discover** | Setup, architecture, phases 3-6, pitch |
| Scores most on | Founder control & safety (15), evidence & honesty (15) | Working prototype (25) | Reproducibility (10), architecture (20), pitch (15) |
| Owns these files | `onboarding/`, `api/onboarding.py`, `guardrails.py`, `decision_log.py`, `outputs.py`, `prompts.py`, **`gates.py`**, **`agents/business_designer.py`**, **`agents/landing_page.py`**, `prompts/brief_*.md`, `prompts/business_designer.md`, `prompts/landing_page.md`, `ui/pages/1_onboarding.py`, `ui/pages/3_decision_log.py` | `orchestrator.py`, `approval.py`, `agents/researcher.py`, `agents/interviewer.py`, `api/stages.py`, `ui/pages/2_pipeline.py`, `prompts/researcher.md`, `prompts/interviewer.md` | `Dockerfile`, `docker-compose.yml`, `.env.example`, `llm/`, `README.md`, `ARCHITECTURE.md`, `.github/`, `agents/` for phases 3-6, `delivery.py` |

**Shared files:** announce a change before making it. `api/main.py` (one `include_router` line per person),
`db/schema.sql` (append your own section only), `pyproject.toml` (Abdelrahman merges dependency requests),
`ui/common.py` (theme helpers).

### A: Menna

**Done (on `main`):** founder onboarding (Arabic/English chat, documents, versioned brief, product check,
budget parsing, supply side for marketplaces), guardrails (excluded products, must-never requests, redaction,
`check_output()`), decision log (per-session in the UI), outputs naming, prompts loader, brief hand-off
(`load_brief`, `is_stale`), **`gates.py`** (product, evidence and demand gates). 211 tests.

**Now:**
1. ✅ **`gates.py` (done, on `main`)**: the shared gate contract everyone uses. A gate returns a `GateDecision`:
   phase, gate name, outcome (`go` / `repeat` / `pivot` / `stop`), the metric, the **pre-set** target, the
   actual value, the reason, and the evidence used. Helpers:
   - `product_gate(brief)`: excluded product -> `stop`.
   - `evidence_gate(phase, sourced_claims, assumptions, min_sourced)`: too few sourced claims -> `repeat`,
     none at all -> `stop` (Roufayda uses this for Phase 1).
   - `demand_gate(target, actual, days)`: actual >= target -> `go`; >= 50% -> `repeat`; >= 25% -> `pivot`;
     below -> `stop`. Thresholds fixed in code and written into the decision, never adjusted after the result.
   - `record(decision, brief_id)`: writes `outputs/phase<N>_gate_<name>.md` (with `Brief id:`) and a
     `decision_log.json` entry with `agent="gate"` and `outcome`.
   Tests: each outcome, thresholds can't change after the result, the 12-of-100 example returns `stop`.
2. **Phase 2 Validate, core step "Design the business"**:
   - `agents/business_designer.py`: a Lean Canvas from the confirmed brief; every box is the founder's words,
     a sourced Phase 1 claim, or labelled `ASSUMPTION`. Output `phase2_step1_lean_canvas.md`.
   - `agents/landing_page.py`: a landing-page draft (HTML) with a waitlist and a pre-set target (e.g. 100
     sign-ups in 14 days). Publishing is **MOCKED** and needs the founder's approval; `check_output()` on all
     text (no countdowns, no fake testimonials). Output `phase2_step2_landing_page.html`.
   - Sign-up count: entered by the founder (or labelled MOCKED in the demo), never generated. Then
     `demand_gate` -> `phase2_gate_demand.md`.
3. **Demo briefs:** one that passes and one weak idea that ends in **stop**; the demo script for 3 minutes.

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

1. **`docker compose up`** (MUST, highest risk): a `Dockerfile` and a `docker-compose.yml` that start db, API,
   UI and **Ollama** with an open-weight model (e.g. `qwen3:8b`), working at http://localhost:8501 with no keys.
   Copy `prompts/` into the image (or set `PROMPTS_DIR`). Every setting in `.env.example`, placeholders only.
2. **Model profiles** in `llm/`: Ollama by default; record tokens per call so cost per run is measured.
3. **README.md** and **ARCHITECTURE.md** exist with the required headings: keep their status tables in step
   with what lands on `main` (Working / MOCKED / STUBBED), and fill the demo-video link.
4. **Phases 3-6 as STUBBED agents** with labelled outputs: Build (PRD + MVP template), Commercial (price
   hypotheses + draft terms/privacy/refund policies), Launch (store page and posts as drafts; `delivery.py`
   mocked with idempotency), Operate (persevere-or-pivot memo).
5. Postgres service in CI; pitch deck and ≤3 min backup video (Wednesday 14:00 if we reach the top 5).

## 2. Contracts (ready now)

| What | How |
|---|---|
| Brief | `from venture_os.onboarding.briefs import load_brief, is_stale` -> `brief = load_brief(brief_id)`: `brief.known("budget")` (founder's words or `None`; never fill unknowns), `brief.budget` (`{min, max, currency, currency_source}` or `None`), `brief.tag("country_code")`, `brief.allowed` (False = excluded product: stop), `brief.open_questions` (research questions for Discover), `brief.followups`, `is_stale(brief_id, version_used)`. HTTP: `GET /onboarding/briefs/{id}`. Without a database: `ConfirmedBrief.from_file("tests/fixtures/briefs/nadafa_v1.json")` or `pharmastock_v1.json`. |
| Gates (**ready**, `src/venture_os/gates.py`) | `gates.record(gates.product_gate(brief), brief_id)` before Discover; `gates.record(gates.evidence_gate(1, sources=[url per sourced claim], assumptions=n), brief_id)` after research; `test = gates.plan_demand_test(target=100, days=14)` **before** measuring, then `gates.record(gates.demand_gate(test, actual, days_elapsed, source="founder"), brief_id)`. Outcomes `go` / `repeat` / `pivot` / `stop`; `record()` writes `outputs/phase<N>_gate_<product|evidence|demand>.md` and a log entry. Gates only recommend: the founder's decision goes through `approval.py`. |
| Guardrails | `from venture_os.guardrails import check_output, check_product, redact`. Run `check_output(text)` on every generated text before showing it; block if it returns rules. |
| Prompts | `load_prompt("researcher", query=...)` reads `prompts/researcher.md` (`## System prompt` section, `$placeholders`). |
| Decision log | `log_action("researcher", "find_opportunities", sources=[...], model="qwen3:8b", cost=0, approved_by=None, outcome=..., brief_id=str(brief_id))`. **Always pass `brief_id`**: the UI shows only the current session's entries. |
| Outputs | `write_output(1, 1, "opportunities", markdown)` -> `outputs/phase1_step1_opportunities.md`. **Put `Brief id: <id>` in every file**: the UI lists only outputs containing the session's brief id. |
| Model call | `venture_os.llm.client.chat_json(messages)` (Abdelrahman adds profiles; the signature stays). |
| Tests | `tests/conftest.py` redirects the log and outputs to a temp folder; tests never touch the real ones. |

## 3. Timeline (Tuesday)

| When | A: Menna | B: Roufayda | C: Abdelrahman |
|---|---|---|---|
| Now | ✅ `gates.py` on `main`; next: Lean Canvas agent | Orchestrator + approval skeleton on the brief fixtures | Dockerfile + compose with Ollama |
| 12:00 checkpoint | Phase 2 agents produce their outputs; `demand_gate` -> **stop** example | Phase 1 end to end with `evidence_gate` | `docker compose up` works on a clean clone |
| 16:00 checkpoint | Pipeline page shows Phase 2 + gate; demo briefs ready | Approvals wired in the pipeline page | Phases 3-6 stubs; README/ARCHITECTURE in step |
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
