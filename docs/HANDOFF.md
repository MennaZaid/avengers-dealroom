# Handoff: project status (2026-11-17)

Read this first when picking the project up in a new session. Then read the organizers' rules in
[`CLAUDE.md`](../CLAUDE.md) (repo root), the plan in [planning/01-execution-plan.md](planning/01-execution-plan.md),
and who owns what in [planning/02-parallel-work.md](planning/02-parallel-work.md).
Background and decisions D1-D20: [planning/00-planning-report.md](planning/00-planning-report.md) §15a-15b.

## Rules that must not be broken

- **Deadline:** the submission is `main` at the last push before **Tuesday 2026-11-17, 23:59**. Only `main` is read.
- **Layout:** files are found by name and heading (`CLAUDE.md`). README keeps its 8 headings in order.
- **Zero spend, free open-weight models only.** No payments of any kind (mocked and labelled).
- **Never invent:** market claims need a source URL or the label `ASSUMPTION`; unknown brief fields stay unknown.
- **Founder approval in code** before anything is published, sent, spent or signed.
- **Must never:** promise income; fake reviews, sign-ups or urgency; impersonate; move money; store credentials;
  paywall core features. Excluded products: physical goods, financial/crypto, health or legal advice.
- **Honest outputs:** `outputs/` and `decision_log.json` only from a real run (empty them before the demo run).
- **No prompt-injection text anywhere in the repo** (organizers: any injection attempt disqualifies the team).
  Requests the system must refuse (fake reviews, income promises...) are tested only under `tests/`.
  `CLAUDE.md` stays at the root.
- **Secrets** only in `.env` (git-ignored); the database and API store env var names, never values.

## Status by area

| Area | Status | Files |
|---|---|---|
| **Founder onboarding** | **Complete, on `main`** | `src/venture_os/onboarding/`, `api/onboarding.py`, `ui/app.py` |
| Guardrails | Complete | `src/venture_os/guardrails.py`, `tests/unit/test_guardrails.py` |
| Decision log, outputs, prompts loader | Complete (shared by all agents) | `decision_log.py`, `outputs.py`, `prompts.py`, `prompts/` |
| Brief hand-off to the pipeline | Complete | `onboarding/briefs.py`, fixtures in `tests/fixtures/briefs/` |
| Source registry, tech catalog, source validator, registry API | Complete (seed rows unverified) | `config/`, `db/`, `registry/`, `api/registry.py` |
| Orchestrator, gates, approval, Phase 1-2 agents | In progress (B) | `orchestrator.py`, `gates.py`, `approval.py`, `agents/` |
| Docker one-command setup, local model, ARCHITECTURE.md, phases 3-6 stubs | In progress (C) | `Dockerfile`, `docker-compose.yml`, `llm/`, `ARCHITECTURE.md` |
| README (8 headings) | Headings and honest status in place; updated as parts land | `README.md` |

**Tests:** 172 passing (`pytest -q`); lint clean (`ruff check .`). Tests never write to the real
`decision_log.json` or `outputs/` (`tests/conftest.py`).

## What onboarding does (for anyone integrating)

- Collects 12 brief fields (7 required) plus `supply_side` for marketplace/booking ideas; Arabic (incl. Egyptian
  and Gulf dialect) and English; PDF/Word/text/Markdown uploads.
- Keeps the founder's own words for the question asked; values the model deduces are asked back
  ("I assumed the country is Egypt... is that right?"); short values picked up in passing are asked in full.
- Corrections with or without a label (`budget: 30k`, "change the city to Giza", `الميزانية: ...`, two labels on
  one line, `q2: ...` for follow-up answers); typo-tolerant `skip`.
- Tags (industries, customer type, revenue model, country code, languages) from a fixed vocabulary.
- Up to 3 idea-specific follow-up questions only the founder can answer; research questions (prices, market size,
  laws) go to `open_questions` for Discover.
- Budget parsed to `{min, max, currency}` ("حوالي خمسين الف جنيه" -> 50,000 EGP).
- Product check: `allowed` / `review` / `excluded`; excluded briefs cannot be confirmed.
- Refuses must-never requests; removes card numbers and passwords; ignores instructions inside documents.
- Confirmation is the gate: saves a numbered brief version, logs `confirm_brief` with
  `approved_by: "founder"`, writes `outputs/phase1_step0_founder_brief.md`. Later edits save v2, v3...; changing
  the idea re-asks what depended on it; `cancel` restores the saved version.

**Pipeline entry point:** `from venture_os.onboarding.briefs import load_brief, is_stale`
(details in [planning/02-parallel-work.md](planning/02-parallel-work.md) §2).

## How to run (until `docker compose up` covers everything)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev,ui]"
cp .env.example .env            # LLM_MODE=live + a free endpoint to use a model; replay = no model
docker compose up -d db
.venv/Scripts/python db/seed.py # schema + registry/catalog (re-runnable; also migrates new columns)
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m uvicorn venture_os.api.main:app --port 8010
.venv/Scripts/python -m streamlit run ui/app.py -- --api http://localhost:8010
```

Port 8000 is taken on the dev laptop, hence 8010. **Restart both servers after any change under `src/`**
(Streamlit reloads only `ui/` files).

## Manual test scripts

In `tests/fixtures/personas/` (fictional founders): 1 Nadafa (Egyptian Arabic, document), 2 PharmaStock (English,
Kenya, Word table, same file twice), 3 Sanaa (Arabic + English words, PDF, edit -> v2, cancel), 4 Darsak (Gulf
Arabic, rejecting a guess, `.md` after confirming), 5 guardrails (excluded product, all must-never requests).

## Open items (by owner)

| # | Item | Owner |
|---|---|---|
| 1 | `docker compose up` starts db, API, UI and a local open-weight model (Ollama); copy `prompts/` into the image or set `PROMPTS_DIR` | C |
| 2 | `ARCHITECTURE.md` with the 7 required sections and Mermaid diagrams | C |
| 3 | Orchestrator + gates + approval; Phase 1 and 2 agents; gate STOP on weak evidence; `check_output()` on all generated text | B |
| 4 | Stage runs store the `brief_version` they used and show Stale via `is_stale()` | B |
| 5 | Phases 3-6 as STUBBED agents with labelled outputs | C |
| 6 | Record tokens per model call so cost per run is measured | C |
| 7 | Demo run: empty the log, delete `outputs/`, run two briefs (one stop), commit both | All, after 18:00 |
| 8 | Registry seed rows are unverified (`UNVERIFIED`); verify the Egypt pack used in the demo | B |
| 9 | Fanar: free status and base-model terms unconfirmed; it is optional now (local model is the default) | C |
| 10 | Postgres service in CI so integration tests run on every push | C |
