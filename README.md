# Venture OS

An open-source team of AI agents that takes a founder's brief toward a validated, sellable **digital** product,
phase by phase, with a gate after every step, a full decision log, and the founder in control. It recommends
**stop** when the evidence is weak. Runs on a local open-weight model for $0. Apache-2.0.

## Quickstart

```bash
docker compose up
```

Then open **http://localhost:8501**. No `.env` and no keys are needed. The first start downloads the
open-weight model `qwen3:4b-instruct` (about 2.5 GB); the app is usable right away with rule-based fallbacks
and uses the model once the download finishes. Host ports can be changed in `.env` (see `.env.example`).

## What works and what is mocked

| Phase | Step | Status |
|---|---|---|
| 0 Onboarding | Founder brief chat (Arabic/English, documents, versions, product check, refusals) | **Working** |
| 0 Onboarding | Product gate (excluded products stop) | **Working** |
| 1 Discover | Find opportunities, Mom Test interview script | **STUBBED** (in progress, not on `main`) |
| 1 Discover | Evidence gate (`gates.evidence_gate`) | **Working** (code); runs once Discover lands |
| 2 Validate | Lean Canvas with FOUNDER / EVIDENCED / ASSUMPTION / UNKNOWN basis | **Working** |
| 2 Validate | Demand test declared before results (100 sign-ups / 14 days) | **Working** |
| 2 Validate | Landing page draft (email-only waitlist sends nothing) | **Working** draft; publishing **MOCKED** |
| 2 Validate | Sign-up count | Entered by the founder (founder-reported, not verified); never generated |
| 2 Validate | Demand gate (12 of 100 -> stop) | **Working** |
| 3 Build | PRD, MVP from a template, tests, user guide, build gate | **STUBBED** (in progress, not on `main`) |
| 4 Commercial | Price hypotheses; draft terms, privacy, refund policy; gates | **STUBBED** |
| 5 Launch | Store page and 3 launch post drafts; launch gate | **STUBBED**; posting **MOCKED** |
| 5 Launch | Payments, delivery (once per order), refunds (revoke access), reconciliation | **MOCKED** |
| 6 Operate | Persevere-or-pivot memo from logged results; operate gate | **STUBBED** |
| All | Founder approval before anything is published, sent or spent (`approval.py`) | **STUBBED** (in progress); every check refuses until it lands |
| All | Decision log, outputs, guardrails, cost per run | **Working** |

## Architecture

Plain code runs the phases in order and each phase ends at a gate that compares results with a rule fixed before
the result was known; gates only recommend go / repeat / pivot / stop and the founder decides. Agents are one
module per role (`src/venture_os/agents/`) with prompts in `prompts/`, call one OpenAI-compatible client
(local Ollama by default) and fall back to rules without a model. Every action goes to `decision_log.json` and
every result to `outputs/`. Payments, delivery and publishing are mocked and need the founder's approval.
Details and diagrams: [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

- **Default:** `qwen3:4b-instruct` (Qwen3-4B-Instruct-2507, Apache-2.0, open-weight) in the Ollama container
  started by `docker compose up`. No key, no account, CPU is enough. A larger local model: set `OLLAMA_MODEL` and
  `LLM_MODEL_EXTRACT` in `.env` (e.g. `qwen3:8b`).
- **No model at all:** `LLM_MODE=replay` runs every agent on its rule-based path (this is how CI runs).
- **Optional:** any free OpenAI-compatible endpoint via `.env` (for example Fanar for Arabic); never a paid API.
- **Also local and free:** PostgreSQL + pgvector, SearXNG search.

## Cost per run

**About $0.00 per run** (local `qwen3:4b-instruct`, no paid APIs). Measured, not estimated: every model call is
logged with its tokens and `python scripts/cost_report.py` sums them from `decision_log.json`. On the log currently
in the repo it prints "About $0.00 per run (no model calls in this log: rule-based run)"; the demo run's line,
with its token count, replaces this.

## Demo video

Link to be added.

## What our system will NOT do

- Promise income or success, or state income forecasts.
- Write fake reviews or testimonials, invent sign-ups or user counts, or use countdowns or fake scarcity.
- Pose as the founder, a customer or another brand.
- Hold, move, charge or refund money, create accounts, or store passwords or card numbers.
- Publish, send, spend or sign anything without the founder's explicit approval.
- Work on physical goods, financial, investment or crypto products, or health or legal advice products.
- Hide core features behind a paywall.

## How the project stays alive after the hackathon

- **Maintainers:** the three founding team members.
- **Roadmap:** land the orchestrator and approvals, then Phases 1 and 3 on `main`; deepen Phases 4-6; more
  country source packs (see [ARCHITECTURE.md](ARCHITECTURE.md#roadmap)).
- **Community:** Apache-2.0; new agents are a module plus a prompt file, new markets a reviewed YAML source pack.
- **Funding:** none needed to run it (local models, self-hosted); hosting a shared instance is the only cost.

Team notes and plans: [docs/](docs/).
