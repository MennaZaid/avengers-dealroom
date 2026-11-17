# Venture OS

An open-source team of AI agents that takes a founder's brief toward a validated, sellable **digital** product,
phase by phase, with a gate after every step, a full decision log, and the founder in control. It recommends
**stop** when the evidence is weak. Runs on a local open-weight model for $0. Apache-2.0.

## Quickstart

```bash
docker compose up
```

Then open **http://localhost:8501** (the UI logs this URL when ready; API docs at http://localhost:8010/docs).
No `.env` and no keys are needed. The first start downloads the open-weight models (`qwen3:4b-instruct`, about
2.5 GB, and the `bge-m3` embeddings) into a Docker volume; the app is usable right away with rule-based fallbacks
and uses the models once the download finishes (measured on a laptop: the app answers about 25 s after
`docker compose up`; while the model is still loading, a chat reply can take up to 2 minutes before the
rule-based answer). Give Docker about 6 GB of memory. Host ports: see `.env.example`.

## What works and what is mocked

| Phase / step | Status | Notes |
|---|---|---|
| 0. Founder onboarding (brief) | **Working** | Arabic/English chat, PDF/Word/text upload, versioned brief, founder confirmation |
| Guardrails (excluded products, must-never requests) | **Working** | Refuses fake reviews, income promises, impersonation, moving money, credentials |
| Product gate | **Working** | Excluded products (physical, financial/crypto, health or legal advice) stop |
| 1. Discover: find opportunities + evidence gate | **Working** | Live web + free APIs; verbatim-quoted claims or `ASSUMPTION`; ideas scored, market sized bottom-up, Mom Test script; founder decides. Critic's judge model **STUBBED** unless a different-family model is set |
| 2. Validate: Lean Canvas | **Working** | Every entry FOUNDER / EVIDENCED (id + URL + date) / ASSUMPTION / UNKNOWN; riskiest assumption named |
| 2. Validate: demand test plan | **Working** | 100 waitlist sign-ups in 14 days, declared before any result |
| 2. Validate: landing page | **Working**; publishing **MOCKED** | Self-contained HTML, email-only waitlist that sends nothing, "DRAFT — not published (MOCKED)" banner |
| 2. Validate: sign-up count + demand gate | **Working** | `POST /stages/runs/{id}/signups`: count entered by the founder (founder-reported, not verified), never generated; 12 of 100 -> stop |
| 3. Build: build the product + build gate | **Working** | Evidence -> requirements -> plan -> validation -> single-file HTML MVP -> QA checks -> user guide; one founder approval at the end; payments in the MVP are **MOCKED** |
| 4. Commercial: pricing research, price, draft policies, readiness + gate | **Working** (stage logic); pipeline wiring in progress | `run_commercial_stage`: only sourced prices (URL + date); min/median/max and break-even in code, labelled ESTIMATE; terms/privacy/refund "DRAFT — not legal advice", citing official registry sources or "No verified official source found"; no payments |
| 5. Launch: store page and 3 post drafts + gate | **STUBBED**; posting **MOCKED** | Not run by the pipeline yet; nothing is posted |
| 5. Launch: payments, delivery, refunds, reconciliation | **MOCKED** | Delivery once per order; a refund revokes access; reconciliation flags missing payments; no money moves |
| 6. Operate: persevere-or-pivot memo + gate | **STUBBED** | Not run by the pipeline yet. Built only from logged results; support and analytics "no data yet" |
| Founder decisions at stage gates (`approval.py`) | **Working** | Approve / repeat / pivot / stop / waive, logged with `approved_by: "founder"` |
| Founder approval of exact content (landing page, launch posts, order, refund) | **Working** | `POST /stages/approvals` (UI) or `python -m venture_os.approval` (CLI); the action is refused unless this exact content was approved |
| Founder decision to pass a phase gate (`pass_phase<N>_gate`: go / repeat / pivot / stop) | **Working** | Only the founder's latest decision "go" passes a gate; the Phase 4-6 agents are still STUBBED and not run by the pipeline |
| Decision log, outputs, cost per run | **Working** | `decision_log.json` (tokens per model call), `outputs/phase<N>_step<M>_*`, `scripts/cost_report.py` |

## Architecture

A deterministic orchestrator runs the phases in order; each step's agent writes typed outputs and a log entry,
and a gate (founder approval, a pre-set evidence threshold, or passing tests) recommends go, repeat, pivot or
stop; the founder decides. Gates and approvals are plain code, not prompts. Every market claim needs a source URL
or is labelled `ASSUMPTION`. Agents live in `src/venture_os/agents/` with prompts in `prompts/`, call one
OpenAI-compatible client (local Ollama by default) and fall back to rules without a model. Payments, delivery and
publishing are mocked. Details: [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

- **Default:** `qwen3:4b-instruct` (Qwen3-4B-Instruct-2507, Apache-2.0, open-weight) and `bge-m3` embeddings in
  the Ollama container started by `docker compose up`. No key, no account, CPU is enough. For better quality set
  `OLLAMA_MODEL` and `LLM_MODEL_EXTRACT` to a larger local model such as `qwen3:8b` in `.env`.
- **No model at all:** `LLM_MODE=replay` runs every agent on its rule-based path (this is how CI runs).
- **Optional:** any free OpenAI-compatible endpoint via `.env` (we tested onboarding with Fanar-C-2-27B on its free
  tier); never a paid API.
- **Also local and free:** PostgreSQL + pgvector, SearXNG search.

## Cost per run

**About $0.00 per run** (local `qwen3:4b-instruct`, no paid APIs). Measured, not estimated: every model call is
logged with its prompt and completion tokens, and `python scripts/cost_report.py` sums them from
`decision_log.json`. The token count of the committed demo run is added here from that report after the run.

## Demo video

Link to be added.

## What our system will NOT do

- Promise income or success, or state income forecasts.
- Write fake reviews or testimonials, invent sign-ups or user counts, or add countdown timers or fake scarcity.
- Pose as the founder, a customer or another brand.
- Hold, move, charge or refund money, create accounts, or store passwords or card numbers (they are removed before storage).
- Publish, send, spend or sign anything without an explicit founder approval in the app.
- Work on physical goods, financial, investment or crypto products, or health or legal advice products.
- Hide core features behind a paywall.

## How the project stays alive after the hackathon

- **Maintainers:** the three founding team members.
- **Roadmap:** founder approval of single actions in the UI, deeper Phases 4-6 (sourced pricing, legal sources per
  country, metrics from the MVP's own events), more country source packs.
- **Community:** Apache-2.0; new agents are a module plus a prompt file, new markets a reviewed YAML source pack;
  contributions follow `CLAUDE.md`.
- **Funding:** none required to run (free models, self-hosted); grants or incubator partnerships for hosting later.
