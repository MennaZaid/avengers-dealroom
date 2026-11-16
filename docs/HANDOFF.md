# Handoff — project status (2026-11-16)

Read this first when picking the project up in a new Claude account or session. Then read
[planning/01-execution-plan.md](planning/01-execution-plan.md) (the plan) and
[planning/00-planning-report.md](planning/00-planning-report.md) (architecture, decisions D1–D11 in §15a).

> The original shared plan doc lives in the previous Claude account. Everything in it is now in these repo files;
> treat the repo as the source of truth.

## Rules that must not be broken

- **Zero spend (D9):** never add a payment method; free tiers, Colab free GPU and local models only.
- **Never invent:** facts need a dated source; unknown brief fields stay "unknown"; assumptions are labelled.
- **Founder gates:** no stage starts without the previous stage's recorded approval; external actions need their own scoped approval.
- **Secrets:** keys live only in `.env` (git-ignored). The database and API store env var **names**, never values.
- **Registry changes:** only admins add/deactivate sources (logged with a reason); crawler-found official bodies may be added as *provisional* tier B for 30 days (D8), enforced by Postgres row-level security.
- Nothing is committed to git yet; the team asked not to commit until told.

## What is built and tested (172 tests passing)

| Area | What | Files |
|---|---|---|
| Repo setup | Apache-2.0, README, Docker Compose (Postgres+pgvector, SearXNG), CI on push (lint + tests, no secrets), Windows-friendly task runner | `docker-compose.yml`, `.github/workflows/ci.yml`, `scripts/dev.py` |
| Source registry | 121 sources (85 from the team workbook, 33 case-study, 3 Egypt), 46 corpus items, 12 discovery rules; tiers A/B/C with max age | `config/sources/*.yaml`, `scripts/import_seed.py` |
| Tech catalog | 36 components (models, tools, infra) with licence / open-weight / OSI flags and status; 8 model endpoints (env var names only) | `config/catalog/*.yaml` |
| Database | Registry, catalog, change logs, source candidates, RAG documents/chunks (pgvector 1024-d, freshness view), onboarding sessions, documents, versioned briefs; roles `vos_admin`, `vos_agent`, `vos_app`, `vos_validator` | `db/schema.sql`, `db/seed.py` |
| Source validator | Rule-based checks for crawler-proposed sources (HTTPS, no IP/shortener/punycode, duplicates, robots, injection text, official-domain match) → rejected / provisional / queued | `src/venture_os/registry/validator.py` |
| Registry API | Read routes (sources by country/tier/use, corpus, components, endpoints, summary); admin routes with token, logged reasons, deactivate not delete | `src/venture_os/api/registry.py` |
| Onboarding chat | Asks 7 required + 5 optional fields; Arabic/English; PDF/Word/txt/md upload; "skip" → unknown; summary + corrections; saves a brief version only on "yes"; works with no model; with a model, extracts fields only when a real quote supports them | `src/venture_os/onboarding/`, `src/venture_os/api/onboarding.py`, `ui/app.py` |
| Brief Analyzer (onboarding) | **Tags** from a fixed vocabulary: industries (19), customer_type, revenue_model, country_code (ISO), languages; rules first, model only within the vocabulary, country/languages always rules, revenue_model "unknown" unless the founder said it; founder can correct (`industry: education`). **Follow-up questions**: up to 3 idea-specific questions (model, filtered to real questions; rule fallback by tag), answers saved, correct with `q2: ...`. **Unlabelled corrections** ("change the budget to 30,000 EGP", "خلي المدينة الجيزة"); asks which line when unclear; Arabic labels. **Inferred values** (country from a city) marked `inferred`, pointed out in chat and summary, never override the founder; on "yes" become answered with source "(inferred, confirmed by founder)". **Edit after confirmation**: any correction, "edit" or a new document reopens the brief; "yes" saves the next version with a change note, "cancel" restores; `GET /onboarding/briefs/{id}` returns latest version + history | `onboarding/tags.py`, `onboarding/analyst.py`, `onboarding/chat.py`, `tests/unit/test_onboarding_analysis.py` |
| Onboarding: hackathon rules (complete) | **Guardrails** (`guardrails.py`): excluded products (physical goods, financial/crypto, health or legal advice) block confirmation; must-never requests (fake reviews/sign-ups, urgency, income promises, impersonation, moving money, credentials, instruction injection) are refused in English and Arabic; card numbers/passwords are redacted before storage; `check_output()` for agents. **Decision log** (`decision_log.py`): every onboarding action, founder confirmation with `approved_by: "founder"`. **Outputs** (`outputs.py`): `phase1_step0_founder_brief.md` on confirm. **Prompts** in `prompts/`. **Budget** parsed to numbers + currency (`onboarding/money.py`). **Two-sided ideas** ask for the supply side. **Idea change** re-asks problem/customer and rewrites follow-ups. **Hand-off**: `onboarding/briefs.py` (`load_brief`, `is_stale`, `ConfirmedBrief`) | `guardrails.py`, `decision_log.py`, `outputs.py`, `prompts.py`, `prompts/`, `onboarding/money.py`, `onboarding/briefs.py`, `tests/unit/test_guardrails.py`, `tests/unit/test_brief_contract.py` |
| Model | Fanar-C-2-27B via `https://api.fanar.qa/v1` for extraction. Tested: JSON mode works, Egyptian dialect + English extraction grounded, injection ignored | `src/venture_os/llm/client.py`, `.env` |

## How to run

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev,ui]"
cp .env.example .env            # then fill LLM_API_KEY etc.; set LLM_MODE=live to use a model
docker compose up -d db
.venv/Scripts/python db/seed.py # creates schema + loads registry/catalog (re-runnable)
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m uvicorn venture_os.api.main:app --port 8010
.venv/Scripts/python -m streamlit run ui/app.py -- --api http://localhost:8010
```

Port 8000 is used by another program on the dev laptop, hence 8010. `.claude/launch.json` has both servers.

## Open items (in priority order)

1. **Confirm Fanar is free** (docs show only rate limits, 50 req/min). Ask support@fanar.qa if unclear. The key in `.env` was pasted into a chat once — request a new one if that chat is shared; each teammate should request their own.
2. **Check Fanar's base model terms** (Gemma 3) before calling it fully open source.
3. **Per-profile endpoints:** all profiles share `LLM_BASE_URL`; give each profile its own base URL/key env vars before adding a second provider.
4. **Choose the remaining models** (reasoning, code, judge) from free routes. Reviewed so far: gpt-oss-120b/20b (Apache 2.0, paid providers only seen), Qwen2.5-Coder-7B GGUF (no provider), Mistral Large 4 (not OSI, API only), ALLaM-7B (Arabic, 4k context, licence unnamed), Llama 3.1 8B (rejected: no Arabic), a decensored Qwen fine-tune (rejected: safety), an English-only sentiment BERT (rejected).
5. **Put the DB checks in CI:** add a Postgres service to the workflow so `tests/integration` and `tests/sql/registry_roles.sql` run on every push; add the evaluation/grading step and results page.
6. **Verify registry URLs and licences:** every seed row is `verified: false` / `UNVERIFIED`; Acadia is only reachable via the Wayback Machine (find the snapshot URL).
7. **Next build steps** follow the timeline in the execution plan: stage template + gates (P1), router/search/fetch/agents (P2), Discover and Validate workflows (P3).
8. **CLAUDE.md** is still to be provided by the team.
9. **Stale marking:** brief versions exist (v1, v2, ...) but there is no stage-run table yet. When P1 builds the stage
   template, a stage run must store the `brief_version` it used and show Stale when `GET /onboarding/briefs/{id}`
   reports a newer version.
10. **Fixed after the Nadafa demo run (2026-11-16):** a focused answer keeps the founder's own words for the field
    asked (the model only fills *other* fields, and optional ones picked up that way are marked inferred);
    follow-ups ask only what the founder knows, research questions (prices, market size, laws) are stored as
    `open_questions` on the brief version for Discover; Arabic labels in summary and UI; extractor told the
    founder's language. Test script: `tests/fixtures/personas/nadafa-plan.txt` + the steps in the demo notes.
11. **Fixed after the PharmaStock run:** labels anywhere in a line (`business model: X budget: Y`), follow-up
    answers as `q1. ... , q2. ...`, Word-table rows (`Values | ...`); a required value the model deduced is asked
    ("I assumed the country is Kenya... is that right?"); a required value picked up in passing with 1-3 words
    ("Pharmacist") is still asked, showing what we have; values picked up in passing never overwrite a field;
    an upload no longer skips the pending question; the same file uploaded twice is read once; questions not
    addressed to the founder go to `open_questions`.
12. **Parallel work:** see [planning/02-parallel-work.md](planning/02-parallel-work.md) (ownership, the brief
    contract, the colleague's task, git workflow). Fixtures: `tests/fixtures/briefs/`.
13. **Test personas** in `tests/fixtures/personas/`: 1 Nadafa (Egyptian Arabic, document upload), 2 PharmaStock (English,
    Kenya, Word table, injection file), 3 Sanaa (Arabic + English words, PDF, `ايوه`, tag correction, edit ->
    version 2, cancel). Persona 3 found: Fanar copies the `<untrusted>` tag into quotes (all fields were
    dropped; now stripped before the quote check), `لـ` left in unlabelled corrections, country re-asked as
    "too short". All fixed. Open: for a marketplace idea the model may pick the supply side (artisans) as the
    target customer; the founder corrects it in the summary.
14. **Budget is free text** ("حوالي خمسين الف جنيه"); the Commercial stage will need a normalised amount + currency.
15. **Model quirks seen live (Fanar):** sometimes writes values in English for Arabic founders, and may put
    "no coding" into technical_preferences. Both are visible in the summary and correctable; consider a
    "fields the founder volunteered vs. the field asked" check if it matters in the demo.
