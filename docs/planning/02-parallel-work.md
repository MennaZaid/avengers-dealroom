# Working in parallel: Onboarding + Stage framework / Discover

> 2026-11-16. Two people work at the same time without touching the same files. Read
> [../HANDOFF.md](../HANDOFF.md) first for setup and the rules (zero spend, never invent, founder gates).

## 1. Who owns what

| | Onboarding (owner: Menna) | Stage framework + Discover planner (owner: colleague) |
|---|---|---|
| Code | `src/venture_os/onboarding/`, `src/venture_os/api/onboarding.py` | `src/venture_os/stages/` (new), `src/venture_os/api/stages.py` (new) |
| UI | `ui/app.py` | `ui/pages/2_Discover.py` (new; Streamlit shows it as a second page) |
| Tests | `tests/unit/test_onboarding*.py`, `tests/integration/test_onboarding_api.py` | `tests/unit/test_stages*.py`, `tests/integration/test_stages_api.py` (new) |
| Database | onboarding/brief tables in `db/schema.sql` | a **new section at the end** of `db/schema.sql` |

**Shared files (small, announced edits only):** `src/venture_os/api/main.py` (one `include_router` line
each), `db/schema.sql` (append only, never edit the other section), `pyproject.toml` (new dependencies),
`docs/HANDOFF.md`. Tell the other person before you change one of these.

## 2. The contract between the two halves

Onboarding ends with a **confirmed, versioned brief**. Everything after it reads the brief through one call:

```
GET /onboarding/briefs/{brief_id}
-> { brief_id, version, fields{...}, tags{...}, followups[...], open_questions[...], history[...] }
```

Two real examples (fictional personas) are saved as fixtures; build and test against them, so you don't
need the onboarding chat running:

- [tests/fixtures/briefs/pharmastock_v1.json](../../tests/fixtures/briefs/pharmastock_v1.json): English, B2B,
  Kenya (no Kenya pack in the registry).
- [tests/fixtures/briefs/nadafa_v1.json](../../tests/fixtures/briefs/nadafa_v1.json): Egyptian Arabic, B2C, Egypt.

What you can rely on:

| Key | Meaning |
|---|---|
| `fields.<name>.value` / `.status` | 12 fields. `status` is `answered`, `from_document`, `inferred` or `unknown`. **`unknown` means unknown: never fill it in.** |
| `fields.<name>.source` / `.quote` | Where the value came from (chat or `document:<file>`) and the exact words |
| `tags.industries.value` | 1-3 of a fixed list (see `onboarding/tags.py` `INDUSTRIES`) |
| `tags.customer_type.value` | `b2c`, `b2b`, `b2b2c`, `b2g`, `unknown` |
| `tags.revenue_model.value` | `subscription`, `commission`, ... or `unknown` |
| `tags.country_code.value` | ISO code (`EG`, `KE`) or `unknown` |
| `tags.languages.value` | `["ar", "en"]` etc.: search in each |
| `open_questions` | Research questions found during onboarding (prices, market size, laws). **Discover must try to answer these.** |
| `version` / `history` | Every edit after confirming creates a new version |

**Contract rule:** onboarding may add keys but will not rename or remove these without telling you first.

## 3. Your task (colleague): stage framework + Discover Research Planner

These are the next items on the critical path in [01-execution-plan.md](01-execution-plan.md) (H2-H10, P1/P3)
and depend only on the contract above.

### Part A: stage framework (the template every stage uses)

1. **Tables** (new section in `db/schema.sql`):
   - `stage_runs`: id, brief_id, **brief_version** (the version this run used), stage
     (`discover`, `validate`, `build`, `commercial`, `launch`, `operate`), status (`running`, `awaiting_approval`,
     `approved`, `revision_requested`, `rejected`, `failed`), output JSONB, created_at.
   - `stage_decisions`: stage_run_id, decision (`approve` / `revise` / `reject`), note, created_at.
     Append-only (no UPDATE/DELETE grants), like an audit log.
2. **Entry check** (plain code, no model): Discover can start only for a brief that has a confirmed version.
   Stage N+1 can start only if stage N has an `approve` decision **for the same brief version**.
3. **Stale:** a run is stale when the brief's latest version is newer than `stage_runs.brief_version`.
   Return `stale: true` on reads; never delete old runs.
4. **API** (`api/stages.py`, role `vos_app`):
   - `POST /stages/{stage}/runs {brief_id}` -> 403 if the entry check fails
   - `GET /stages/runs?brief_id=...` -> runs with `stale`
   - `POST /stages/runs/{id}/decision {decision, note}` -> the only way to approve (the gate is code, not a prompt)
5. **Tests:** stage N+1 refused without approval of N; revise then approve both logged; a brief edit marks
   the run stale; approval of an old brief version doesn't unlock the next stage.

### Part B: Discover step 1, the Research Planner (rules first, no model needed)

Input: a brief (fixture). Output: a `ResearchPlan` (Pydantic) stored as the run's output:

- **Sources:** from `GET /registry/sources?country=<country_code>` (it returns country + global sources).
  If no country-specific source exists (Kenya), say so in the plan: `"country_sources": "no verified source"`.
  Never invent a source.
- **Queries:** for each topic (market size, competitors, customer pain, pricing, regulation) and each language
  in `tags.languages`, built from `fields` and `tags`. Add one topic per item in `open_questions`.
  Use only fields whose status is not `unknown`.
- **Known competitors** from the brief become competitor queries.
- Tests with both fixtures: Egypt plan has Arabic + English queries and Egypt sources; Kenya plan is English
  and reports "no verified source"; no query uses an `unknown` field.

Optional after that: a model call to improve query wording (must keep the same schema; tests use replay).

### Part C: a Discover page

`ui/pages/2_Discover.py`: pick a confirmed brief, start Discover, show the plan, Approve / Request revision
buttons calling the decision endpoint, a "Stale" badge when the brief changed.

### Done when

- `pytest` green (CI runs without secrets or a live model), `ruff check .` clean.
- With the API running: confirm a brief in the onboarding page, open the Discover page, run the planner,
  approve; then edit the brief in onboarding and see the run marked Stale.

## 4. Git workflow

Nothing beyond `first commit` is in git yet, and the team asked not to commit until told. Parallel work
needs a shared starting point, so once the team agrees:

1. Commit the current state to `main` and push (one person, once).
2. Each person works on a branch: `onboarding/<topic>` and `stages/<topic>`.
3. Pull `main` into your branch at least daily; open a pull request to merge; CI must be green.
4. Never commit `.env` (it is git-ignored). Each person requests their own Fanar key.

## 5. Running both at once

Each person runs their own API, UI and Postgres on their own laptop (see HANDOFF "How to run").
Restart the API and UI after any change under `src/` (Streamlit reloads `ui/` files only).
