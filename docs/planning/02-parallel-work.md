# Working in parallel: three people, deadline Tuesday 23:59

> Updated 2026-11-16 after the organizers' `CLAUDE.md` (repo root) arrived. The submission is whatever is on
> `main` at the last push before **Tuesday 23:59**. The checker finds files by name and heading, so the layout
> in `CLAUDE.md` is part of the score. This plan replaces the earlier two-person version.

## 1. Who does what

| | **A: Menna** | **B: Roufayda** | **C: Abdelrahman** |
|---|---|---|---|
| Area | Onboarding + safety | The pipeline: phases 1-2 + gates | Repo, setup, architecture, later phases |
| Scores most on | Founder control & safety (15) | Working prototype (25), evidence & honesty (15) | Architecture (20), reproducibility (10), pitch (15) |
| Owns these files | `src/venture_os/onboarding/`, `api/onboarding.py`, `ui/app.py`, `src/venture_os/guardrails.py` (new), `decision_log.py`, `outputs.py`, `prompts/brief_*.md` | `src/venture_os/orchestrator.py`, `gates.py`, `approval.py`, `agents/` (new), `api/stages.py`, `ui/pages/2_Pipeline.py`, `prompts/<agent>.md` | `Dockerfile`, `docker-compose.yml`, `.env.example`, `src/venture_os/llm/`, `README.md`, `ARCHITECTURE.md`, `.github/`, `agents/` for phases 3-6 |

**Shared files:** announce a change before making it. `api/main.py` (one `include_router` line per person),
`db/schema.sql` (append your own section only), `pyproject.toml` (C merges dependency requests).

### A: Menna (onboarding + safety): ✅ done, on `main` (2026-11-17)

All six items below are built and tested (172 tests), plus: budget parsed to numbers, a supply-side question
for marketplace ideas, re-checking problem/customer when the idea changes, and `onboarding/briefs.py` for the
hand-off. Next for A: help B integrate the brief, then README/ARCHITECTURE review and the demo script.

1. **Excluded products** (`guardrails.py`, used by onboarding *and* every agent): physical goods,
   financial/investment/crypto, health or legal advice. The product must be **digital**. Onboarding flags it
   before confirming and suggests a digital angle (e.g. "a booking app for cleaners" is fine; "selling rugs"
   is not). Adds a tag `allowed: true/false` with the reason.
2. **Trick-prompt refusals** in the chat and in agent outputs: fake reviews/testimonials/sign-ups, countdown
   urgency, income promises, posing as someone, moving money, storing passwords/cards. Polite refusal + log
   entry. Trick-prompt test cases go in `tests/` only.
3. **Decision log** in onboarding: every extraction, tagging, follow-up generation and the confirmation
   (`approved_by: "founder"`) via `log_action(...)`.
4. **Prompts out of code:** move the extractor/tagger/follow-up prompts to `prompts/brief_extractor.md`,
   `prompts/brief_tagger.md`, `prompts/followup_questions.md` and load them from there.
5. Write `outputs/phase1_step0_founder_brief.md` when the brief is confirmed.
6. Tests: one guardrail test per must-never rule.

### B: Roufayda (the working pipeline)

Input: the confirmed brief (`GET /onboarding/briefs/{id}`; fixtures in `tests/fixtures/briefs/`).

1. **`orchestrator.py`**: runs phase steps in order; a step starts only if the previous gate passed
   **for the same brief version** (plain code, not a prompt).
2. **`gates.py`**: each gate returns `go`, `repeat`, `pivot` or `stop` with the reason and the threshold it
   used. Recommends **stop** when the evidence is weak (too few sourced claims, an excluded product, a demand
   test below its pre-set target). Writes `outputs/phase<N>_gate_decision.md` and a log entry with `outcome`.
3. **`approval.py`**: the founder's approve / reject / revise is the only way past a gate, and the only way
   anything is "published" (all publishing is MOCKED). Test: nothing goes out without approval.
4. **Phase 1 Discover, core step "Find opportunities"** (`agents/researcher.py`): search with SearXNG +
   registry sources, claims with source URL and date, anything unsourced labelled `ASSUMPTION`; plus a
   Mom Test interview script (`agents/interviewer.py`). Outputs: `phase1_step1_opportunities.md`,
   `phase1_step2_interview_script.md`, `phase1_gate_decision.md`.
5. **Phase 2 Validate, core step "Design the business"**: Lean Canvas (`agents/business_designer.py`) and a
   landing-page draft with a waitlist target (e.g. 100 sign-ups in 14 days). Sign-up counts are
   **MOCKED**/entered by the founder, never invented. Outputs: `phase2_step1_lean_canvas.md`,
   `phase2_step2_landing_page.html`, `phase2_gate_decision.md`.
6. `ui/pages/2_pipeline.py`: run a phase, see outputs with sources, approve / reject at each gate. The UI is now
   multi-page (2026-11-17): a placeholder page with the six-phase layout is in place; replace its body and keep
   `ui/theme.py` for the header, colours and phase bar.

### C: Abdelrahman (repo, setup, architecture, phases 3-6)

1. **One-command setup:** a `Dockerfile` and a `docker-compose.yml` that start db, API, UI and **Ollama**
   with an open-weight model (e.g. `qwen3:8b`), so `docker compose up` gives a working app at
   http://localhost:8501 with no keys. Optional free hosted route (e.g. GPT-OSS on a free tier) through
   `.env`. Every setting in `.env.example`, placeholders only.
2. **Model profiles** in `llm/`: Ollama local by default; record tokens per call so cost per run is
   measured (local = $0).
3. **`README.md`** with exactly the 8 `##` headings from `CLAUDE.md`, in order, including the "What works
   and what is mocked" table (each step: Working / MOCKED / STUBBED) and a `$` cost per run.
4. **`ARCHITECTURE.md`** with the 7 sections from `CLAUDE.md`: all six phases (agents, tools, method, output),
   gates with go/repeat/pivot/stop and when STOP is recommended, **sale to cash** (payment triggers delivery,
   refund revokes access, idempotency, reconciliation: all MOCKED), data flow, built vs stubbed, roadmap.
   Mermaid diagrams. Material: `docs/planning/00-planning-report.md`. **A first version exists (2026-11-17):**
   keep its "Built vs. stubbed" table and phase statuses in step with what actually lands on `main`.
5. **Phases 3-6 as STUBBED agents** (only after 1-4): `agents/<role>.py` that produce a labelled STUBBED
   output so the pipeline visibly reaches each phase: Build (PRD + MVP template), Commercial (price
   hypotheses + draft terms/privacy/refund policies), Launch (store page draft, launch posts as drafts,
   `delivery.py` mocked with idempotency), Operate (persevere-or-pivot memo).
6. Pitch deck and ≤3 min backup video (needed Wednesday 14:00 if we reach the top 5).

## 2. Contracts (ready now)

| What | How |
|---|---|
| Brief (**onboarding is complete**) | In Python: `from venture_os.onboarding.briefs import load_brief, is_stale` -> `brief = load_brief(brief_id)` gives a typed `ConfirmedBrief`: `brief.known("budget")` (founder's words or `None`; never fill unknowns), `brief.budget` (`{min, max, currency, currency_source}` or `None`), `brief.tag("country_code")`, `brief.allowed` (False = excluded product: the pipeline must stop), `brief.open_questions` (research questions for Discover), `brief.followups`, `is_stale(brief_id, version_used)`. Over HTTP: `GET /onboarding/briefs/{id}` (same keys + history). Fields: the 12 brief fields + `supply_side` (filled only for marketplace/booking ideas). Without a database: `ConfirmedBrief.from_file("tests/fixtures/briefs/nadafa_v1.json")` (Arabic, two-sided, allowed) or `pharmastock_v1.json` (English, Kenya, product check `review`). Confirming writes `outputs/phase1_step0_founder_brief.md` and a `confirm_brief` log entry with `approved_by: "founder"`. |
| Guardrails | `from venture_os.guardrails import check_request, check_output, check_product, redact`. Run `check_output(text)` on every generated text before showing it (income promises, fake urgency, fake reviews); block if it returns rules. |
| Prompts | `from venture_os.prompts import load_prompt` then `load_prompt("researcher", query=...)` reads `prompts/researcher.md` (`## System prompt` section, `$placeholders`). |
| Decision log | `from venture_os.decision_log import log_action` then `log_action("researcher", "find_opportunities", sources=[...], model="qwen3:8b", cost=0, approved_by=None, outcome=...)`. Writes `decision_log.json`. |
| Outputs | `from venture_os.outputs import write_output` then `write_output(1, 1, "opportunities", markdown)` -> `outputs/phase1_step1_opportunities.md`; `write_output(1, None, "decision", md, gate=True)` -> `outputs/phase1_gate_decision.md`. |
| Model call | `venture_os.llm.client.chat_json(messages)` (C adds profiles; the signature stays). |
| Tests | Never write to the real log/outputs: `tests/conftest.py` redirects both to a temp folder. |

## 3. Timeline

| When (Tue) | A: Menna | B: Roufayda | C: Abdelrahman |
|---|---|---|---|
| Mon night | ✅ Merged to `main` | Read brief contract, start orchestrator + gates | Dockerfile + compose with Ollama |
| 12:00 checkpoint | Guardrails + logging in onboarding | Phase 1 runs end to end with its gate, incl. STOP | `docker compose up` works on a clean clone; README skeleton |
| 16:00 checkpoint | Prompts in `prompts/`; trick-prompt tests | Phase 2 + gate; pipeline page | ARCHITECTURE.md; phases 3-6 stubs |
| **18:00 feature freeze** | | | |
| 18:00-21:00 | All: real demo run with 2 briefs, one that passes and one that gets **stop**; `reset_log()` first; commit `outputs/` and `decision_log.json` from that run | | |
| 21:00-23:00 | All: fresh clone -> `docker compose up` -> run the checklist at the end of `CLAUDE.md`; fix only | | |
| **by 23:00** | Final merge to `main` and push (one hour of buffer) | | |

## 4. Git

- `main` is the submission. Each person works on a branch (`onboarding/...`, `pipeline/...`, `repo/...`),
  pulls `main` often, and merges small pieces early; CI must be green.
- Never commit `.env`. Never hand-write `outputs/` or `decision_log.json`.
- Trick prompts and injection files live only under `tests/` (see `tests/fixtures/personas/`).
