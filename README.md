# Venture OS

An open-source team of AI agents that takes a founder's brief toward a validated, sellable **digital** product,
phase by phase, with a gate after every step, a full decision log, and the founder in control. It can recommend
**stop** when the evidence is weak. Apache-2.0.

## Quickstart

```bash
docker compose up
```

Then open http://localhost:8501 (founder onboarding chat). The API docs are at http://localhost:8010/docs.

No keys or `.env` needed. `docker compose up` starts Postgres + pgvector (seeded with the source registry),
SearXNG search, a local open-weight model in Ollama, the API and the app. The first start downloads the model
(about 2.5 GB) into a Docker volume, so it takes a few minutes; later starts are fast. Give Docker about 6 GB
of memory.

## What works and what is mocked

| Phase / step | Status | Notes |
|---|---|---|
| 0. Founder onboarding (brief) | **Working** | Arabic/English chat, PDF/Word/text upload, versioned brief, founder confirmation |
| Guardrails (excluded products, must-never requests) | **Working** | Refuses fake reviews, income promises, impersonation, moving money, credentials |
| Decision log and outputs | **Working** | `decision_log.json`, `outputs/phase<N>_step<M>_*` written by the code |
| Gates (product, evidence, demand) | **Working** | go / repeat / pivot / stop from thresholds fixed before the result; 12 of 100 sign-ups -> stop |
| 1. Discover: find opportunities + gate | In progress | Sourced claims or `ASSUMPTION`; gate go / repeat / pivot / stop |
| 2. Validate: design the business + gate | In progress | Lean Canvas, landing-page draft; sign-up counts entered by the founder or **MOCKED** |
| 3. Build: build the product | **STUBBED** | PRD and MVP template |
| 4. Commercial setup: price and policies | **STUBBED** | Draft terms, privacy and refund policies; no payments |
| 5. Launch: store and automatic delivery | **MOCKED** | Drafts only; delivery and payments mocked, nothing is published or charged |
| 6. Operate and learn | **STUBBED** | Persevere-or-pivot memo |

## Architecture

A deterministic orchestrator runs the phases in order; each step's agent writes typed outputs and a log entry,
and a gate (founder approval, a pre-set evidence threshold, or passing tests) decides go, repeat, pivot or stop.
Gates and approvals are plain code, not prompts. Every market claim needs a source URL or is labelled
`ASSUMPTION`. Founder onboarding produces a confirmed, versioned brief that every later step reads.
Details: [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

Runs on free open-weight models only, with no paid APIs. The default is **`qwen3:4b-instruct`**
(Qwen3-4B-Instruct-2507, Apache-2.0) running locally in Ollama, started by `docker compose up` (no key needed;
about 2.5 GB, CPU is enough). For better quality set `OLLAMA_MODEL` and `LLM_MODEL_EXTRACT` to a larger model
such as `qwen3:8b` in `.env`. Optional free hosted route: any OpenAI-compatible endpoint set in `.env`
(we tested onboarding with Fanar-C-2-27B on its free tier). Onboarding also works with no model at all
(rule-based), so the demo never depends on a paid service.

## Cost per run

About $0.00 per run (free open-weight models; local model or free tier). Every model call is listed in
`decision_log.json` with its cost (0 for free models). The model client meters prompt and completion tokens
for every call (`venture_os.llm.client.usage_summary`); the measured count of the committed demo run is added
here after that run.

## Demo video

Link added before the pitch deadline.

## What our system will NOT do

- Promise income or success.
- Write fake reviews or testimonials, create fake sign-ups, followers or accounts, or add countdown timers or fake scarcity.
- Pose as the founder, a customer or another brand.
- Hold, move, charge or refund money, create accounts, or store passwords or card numbers (they are removed before storage).
- Publish, send, spend or sign anything without an explicit founder approval in the app.
- Work on physical goods, financial, investment or crypto products, or health or legal advice products.
- Hide core features behind a paywall.

## How the project stays alive after the hackathon

- **Maintainers:** the three founding team members.
- **Roadmap:** finish Phases 3-6 from the shared stage template, measured cost per run, more country source packs.
- **Community:** Apache-2.0, open issues for new country packs and agents; contributions follow `CLAUDE.md`.
- **Funding:** none required to run (free models, self-hosted); grants or incubator partnerships for hosting later.
