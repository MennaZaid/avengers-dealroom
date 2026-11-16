# Venture OS — 30-Hour Execution Plan (3 people)

> Based on decisions D1–D7 in [00-planning-report.md](00-planning-report.md) §15a.
> Budget: 3 × 30 h = 90 person-hours. **Feature freeze at H20.** H0 = kickoff.
> M0 (repo skeleton) is already done, so it costs nothing in this budget.

## Roles

| Person | Owns | Main folders |
|---|---|---|
| **P1 – Core & Control** | data models, DB, stage state machine, approvals, audit log, permissions, CI/evals | `core/`, `db/`, `api/`, `security/`, `evals/`, `.github/` |
| **P2 – Evidence & LLM** | LLM router + replay, SearXNG search, fetch/extract (AR+EN), source registry, chunks + pgvector, credibility/freshness rules | `llm/`, `tools/`, `evidence/`, `config/sources/` |
| **P3 – Stages, UI & Demo** | stage step prompts + LangGraph DAGs, Streamlit UI, demo brief, recorded demo, pitch | `stages/`, `ui/`, `docs/demo.md` |

**Day-1 contract (H0–H2, everyone together):** freeze the Pydantic models in `core/models.py`
(Brief, Question, Claim, Evidence, Assumption, StepResult, StageRun, Approval, AuditEvent) and the
function signatures between layers. After that everyone codes against the same interfaces in parallel.

## Timeline

| Hours | P1 – Core & Control | P2 – Evidence & LLM | P3 – Stages, UI & Demo |
|---|---|---|---|
| **H0–2** | *Joint:* agree on models + interfaces, pick the demo idea, choose the hosted LLM provider | ← | ← |
| **H2–6** | `db/schema.sql` (tables in report §3.7) + repository layer; hash-chained audit log | `llm/router.py` (OpenAI-compatible, profiles), `llm/replay.py` (record/replay cassettes), JSON-schema output + one repair retry | Streamlit skeleton: brief form, page layout, RTL/Arabic text check; demo brief written |
| **H6–10** | Stage state machine + entry checker; approval API (approve / reject+notes / revise); 403 on skipped gate | `tools/search.py` (SearXNG JSON, AR+EN queries), `tools/fetch.py` + trafilatura/pypdf extraction, store document with `retrieved_at` + hash | Brief Analyzer step + follow-up questions loop; Research Planner step |
| **H10–14** | Permission broker (tiers T0–T4), scoped action approval (payload hash + expiry); safety tests | Chunk + embed (multilingual) into pgvector; dedupe; manual-upload ingest for CAPMAS/ITC files; registry loader + schema check | Discover LangGraph DAG: market, competitor, audience, opportunity steps writing typed claims |
| **H14–18** | Validator rules (fact has source, dated, freshness, geo match, quote = exact span); contradiction flag | Credibility tier scoring; evidence retrieval API for steps; record cassettes for the demo brief | UI: run view, claims with fact/inference/assumption badges, click claim → source + quote + date; approve/reject buttons |
| **H18–20** | Wire everything end-to-end with P2/P3; **integration test of full Discover run on replay** | Stage 2 lite: review-quote mining + competitor matrix steps | Stage 2 lite: evidence ladder, experiment plan, Go/Revise/Stop step + UI |
| **H20 — FEATURE FREEZE** | | | |
| **H20–24** | `evals/run_eval.py` → `results/summary.json` (category scores); CI uploads it; simple results page | Fix grounding failures found in evals; live run with hosted model, re-record cassettes | Decision-log view; Stale flag when brief changes; demo script `docs/demo.md` |
| **H24–27** | Docs: architecture, safety, costs (measured tokens/run), agent docs | Colab notebook (vLLM + tunnel) as secondary endpoint proof | Pitch deck + rehearsal #1; record backup demo video |
| **H27–30** | Bug fixes, final CI green, tag `v0.1` | Bug fixes | Rehearsal #2, final polish |

## Checkpoints (all 3 stop and verify)

| When | Must be true | If not |
|---|---|---|
| **H6** | LLM call works through the router, both live and replay; DB schema up | drop to one model profile |
| **H10** | Brief → questions → answers works in UI; one search returns stored, dated documents | cut audience step, merge into market |
| **H14** | Discover DAG runs end-to-end (even with weak outputs) | cut opportunity step to a template |
| **H20** | Full demo path works on replay: Discover → gate → reject → revise → approve → Validate-lite → Go/Revise/Stop | cut Stage 2 to evidence ladder + recommendation only |
| **H27** | CI green, demo rehearsed once | stop all features, only fix |

## Tests each person owns

| Area | Tests (all run in CI on replay, no secrets) |
|---|---|
| P1 | can't start stage N+1 without approval of N; reject → revise → re-approve logged; T3 action blocked without scoped approval; audit chain tamper detection |
| P2 | replay is deterministic; fetched doc has `retrieved_at` + hash; duplicate docs merged; registry YAML valid; Arabic text survives extraction |
| P3 | each step's output matches its schema; every `fact` claim has evidence; demo golden run passes; no "guaranteed income"-type phrases in output |

## Demo acceptance (definition of done)

1. Incomplete brief → system asks targeted questions.
2. Discover runs; trace shows real searches and fetched sources (Arabic + English).
3. Validator flags a stale or unsourced claim.
4. Founder rejects a section → only that step re-runs → approved.
5. Validate-lite produces quotes, competitor matrix, evidence ladder, Go/Revise/Stop.
6. Brief change marks later stages Stale.
7. "Publish landing page" is blocked until a scoped approval is given.
8. Decision log shows every step above; CI results page shows the latest commit score.

## Risks specific to 30 h

| Risk | Mitigation |
|---|---|
| Integration hell at H18 | shared models frozen at H2; daily-style 10-min syncs at H6/H10/H14 |
| Hosted model weak at JSON | constrained JSON mode + repair; pick provider at H0 by testing 5 prompts |
| SearXNG gets rate-limited by engines | cache all fetches; demo runs on replay |
| CAPMAS/ITC access slow or blocked | download 2–3 relevant tables/reports by H10 and ingest manually |
| Nobody sleeps | schedule 2 × 3 h rest blocks per person, staggered so one person is always awake near H15–24 |

## Open items for H0

- Demo business idea (Egypt). Suggestion: pick something with visible public reviews and competitors so Stage 2 has real evidence.
- Hosted provider choice (free tier if possible) + who holds the API key.
- GitHub repo owner/name.
