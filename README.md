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
| 2. Validate: landing page | **Working** / **MOCKED** | Publishing MOCKED. Self-contained HTML, email-only waitlist that sends nothing, "DRAFT — not published (MOCKED)" banner |
| 2. Validate: sign-up count + demand gate | **Working** | `POST /stages/runs/{id}/signups`: count entered by the founder (founder-reported, not verified), never generated; the stop / pivot / repeat thresholds are fixed before the result |
| 3. Build: build the product + build gate | **Working** | Brief + Discover findings + Validate Lean Canvas -> requirements -> product spec written by the model (every value sourced or `ASSUMPTION`) -> plan -> validation -> single-file HTML MVP with a try-it form and live preview -> QA checks plus checks from the brief (relevance, core action wired) -> user guide; one founder approval at the end; buy, delivery and waitlist in the MVP are **MOCKED** |
| 4. Commercial: pricing research, price, draft policies, readiness + gate | **Working** | Runs after the founder's Go on Build (Pipeline page or the Commercial page); founder decides at the gate. `run_commercial_stage`: only sourced prices (URL + date); min/median/max and break-even in code, labelled ESTIMATE; terms/privacy/refund "DRAFT — not legal advice", citing official registry sources or "No verified official source found"; no payments |
| 5. Launch: store page and 3 post drafts + gate | **STUBBED** / **MOCKED** | Rule-based drafts (STUBBED); posting MOCKED. Runs after the founder's Go on Commercial; nothing is posted; the gate recommends go only if the MOCKED sale-to-cash test completes |
| 5. Launch: payments, delivery, refunds, reconciliation | **MOCKED** | Run inside Phase 5 (`payment_test_log.md`); each test order and refund needs the founder's approval of that exact payload; delivery once per order; a refund revokes access; reconciliation flags missing payments; no money moves |
| 6. Operate: persevere-or-pivot memo + gate | **Working** / **STUBBED** | Support and analytics STUBBED. Runs after the founder's Go on Launch. Built only from logged results; support and analytics say "no data yet" |
| Founder decisions at stage gates (`approval.py`) | **Working** | Approve / repeat / pivot / stop / waive, logged with `approved_by: "founder"` |
| Founder approval of exact content (landing page, launch posts, order, refund) | **Working** | `POST /stages/approvals` (UI) or `python -m venture_os.approval` (CLI); the action is refused unless this exact content was approved |
| Founder decision to pass a phase gate (`pass_phase<N>_gate`: go / repeat / pivot / stop) | **Working** | Only the founder's latest decision "go" passes a gate; each phase after Validate starts only after that go on the previous phase |
| Decision log, outputs, cost per run | **Working** | `decision_log.json` (tokens per model call), `outputs/phase<N>_step<M>_*`, `scripts/cost_report.py` |

## Architecture

A deterministic orchestrator runs the phases in order; each step's agent writes typed outputs and a log entry,
and a gate (founder approval, a pre-set evidence threshold, or passing tests) recommends go, repeat, pivot or
stop; the founder decides. Gates and approvals are plain code, not prompts. Every market claim needs a source URL
or is labelled `ASSUMPTION`. Agents live in `src/venture_os/agents/` with prompts in `prompts/`, call one
OpenAI-compatible client (local Ollama by default) and fall back to rules without a model. Payments, delivery and
publishing are mocked. Details: [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

All models are free: free tiers or a local open-weight model. No paid API is used and none is required.

| Role | Model | Provider | Free tier | Fallback |
|---|---|---|---|---|
| Base: onboarding chat, Discover extraction, Build | `Fanar-C-2-27B` | Fanar (`LLM_BASE_URL`, `LLM_MODEL_EXTRACT`) | Yes | Local Ollama `qwen3:4b-instruct`, then the rule-based path |
| Reasoning and validation (Discover reasoning, Validate) | `openai/gpt-oss-120b` (open-weight) | Groq (`LLM_REASONING_*`, `LLM_VALIDATE_*`) | Yes | Base model, then local Ollama `qwen3:4b-instruct`, then the rule-based path |
| Judge (research critic, a different model family) | `qwen/qwen3.8-27b` | Groq (`LLM_JUDGE_*`, `LLM_MODEL_JUDGE`) | Yes | Base model, then local Ollama `qwen3:4b-instruct`, then the rule-based path |

- **No account needed:** with no `.env`, `docker compose up` runs every role on `qwen3:4b-instruct`
  (Qwen3-4B-Instruct-2507, Apache-2.0, open-weight) in the Ollama container, with `bge-m3` embeddings. No key and
  no GPU are needed.
- **Routing:** each role tries its own endpoint, then the base endpoint, then local Ollama, then its rule-based
  path (`src/venture_os/llm/client.py`). The decision log records the model that actually answered.
- **No model at all:** `LLM_MODE=none` runs every agent on its rule-based path (this is how the tests run;
  `replay` is accepted as the same mode).
- **Keys:** only in an untracked `.env`; `.env.example` holds placeholders.
- **Build:** the MVP tester's headless-browser check is skipped when no Edge or Chrome is installed; the static
  checks on the HTML file still run.
- **Also local and free:** PostgreSQL + pgvector, SearXNG search.

## Cost per run

About $0.00 per run (Fanar-C-2-27B, openai/gpt-oss-120b, qwen/qwen3.8-27b, qwen3:4b-instruct, ~153k tokens)

## Demo video

- Video (3 minutes at most): [link to be added](#demo-video)

## What our system will NOT do

- Promise income or success, or state income forecasts.
- Write fake reviews or testimonials, invent sign-ups or user counts, or add countdown timers or fake scarcity.
- Pose as the founder, a customer or another brand.
- Hold, move, charge or refund money, create accounts, or store passwords or card numbers (they are removed before storage).
- Publish, send, spend or sign anything without an explicit founder approval in the app.
- Work on physical goods, financial, investment or crypto products, or health or legal advice products.
- Hide core features behind a paywall.

## How the project stays alive after the hackathon

- **Maintainers:** Menna Zaid, Roufayda and Abdelrahman (the founding team).
- **Roadmap:** see [ARCHITECTURE.md Roadmap](ARCHITECTURE.md#roadmap).
- **Community:** GitHub Issues for bugs and requests, GitHub Discussions for ideas and questions; how to contribute
  is in [CONTRIBUTING.md](CONTRIBUTING.md).
- **Funding:** none required to run (free models, self-hosted). Later: donations, or paid hosting or support;
  never a paywall on core features.
