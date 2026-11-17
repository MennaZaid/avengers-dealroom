# Venture OS: execution plan (current)

> Updated 2026-11-17. Replaces the earlier 30-hour, all-stages-deep plan. The organizers' conventions are in
> [`CLAUDE.md`](../../CLAUDE.md) at the repo root and override anything here that disagrees.
> Status: [../HANDOFF.md](../HANDOFF.md) · who does what: [02-parallel-work.md](02-parallel-work.md) ·
> background and decisions: [00-planning-report.md](00-planning-report.md).

## 1. What we are building and by when

An open-source team of AI agents that takes a founder's brief toward a validated, sellable **digital** product,
through six phases with a gate after each step, and that can recommend **stop** when the evidence is weak.

| | |
|---|---|
| Submission | Whatever is on `main` at the last push before **Tuesday 2026-11-17, 23:59** |
| Top 5 | Announced Wed 02:00; deck + ≤3 min backup video due Wed 14:00; live demo on an unseen founder brief |
| Team | 3 people: A (Menna), B, C ([split](02-parallel-work.md)) |
| Strategy | One part working live end to end, the rest shown in the architecture and labelled STUBBED |

## 2. Rules that decide the score

| Rule | How we meet it |
|---|---|
| Free open-weight model, no paid APIs | Ollama local model in Docker by default (C); Fanar free tier as an extra |
| No payments of any kind | Payments and delivery are MOCKED and labelled |
| Founder approval before anything is published, sent, spent or signed | Gates and approvals in code (`approval.py`, onboarding confirmation) |
| Every market claim sourced or labelled `ASSUMPTION` | Researcher output; the brief is labelled "founder statements, not market facts" |
| Never: promise income, fake reviews/sign-ups/urgency, impersonate, move money, store credentials, paywall | `guardrails.py` (requests and generated text), tests in `tests/unit/test_guardrails.py` |
| Excluded products: physical goods, financial/crypto, health or legal advice | `guardrails.check_product()`; excluded briefs cannot be confirmed |
| Label every mock | README table + labels in the UI |
| Log every agent action | `decision_log.json` via `log_action()` (7 required keys) |
| Outputs from a real run, named by phase and step | `outputs/phase<N>_step<M>_*.md` via `write_output()` |

Judging: working prototype 25, architecture 20, evidence & honesty 15, pitch 15, founder control & safety 15,
reproducibility 10. Breaking a must-never rule or hiding a mock means disqualification.

## 3. The six phases (organizers' definition) and our depth

| Phase | Core step | What we show | Depth | Owner |
|---|---|---|---|---|
| 0. Onboarding (before Discover) | Founder brief | Chat in Arabic/English, documents, guardrails, versioned brief, product check | **Working** | A |
| 1. Discover | Find opportunities (+ Mom Test interviews) | Sourced opportunities, interview script, gate with go/repeat/pivot/stop | **Working** (target) | B |
| 2. Validate | Design the business | Lean Canvas, landing-page draft, waitlist target; sign-ups entered by the founder or MOCKED | Working (thin) | Abdelrahman (proposed) |
| 3. Build | Build the product | Multi-agent stage: evidence -> requirements -> MVP plan -> validation -> single-file HTML MVP -> tests -> user guide; one founder approval at the end | **Working** (target) | Menna |
| 4. Commercial setup | Set the price and policies | Price hypotheses, draft terms/privacy/refunds; no payments | STUBBED | C |
| 5. Launch | Open the store; deliver automatically | Store page and launch posts as drafts; delivery MOCKED with idempotency | STUBBED | C |
| 6. Operate and learn | (none) | Persevere-or-pivot memo | STUBBED | C |

Every step ends with a gate: founder approval, a pre-set evidence threshold, or passing tests. Outcomes are
go, repeat, pivot back, or **stop**. Example to demo: target 100 waitlist sign-ups in 14 days, 12 reached ->
the gate recommends pivot or stop instead of spinning the result.

## 4. Required repository layout (checked by file name and heading)

| Path | Status | Owner |
|---|---|---|
| `README.md` with the 8 exact headings | Headings in place; content filled as parts land | C (A drafted) |
| `LICENSE` (Apache-2.0) | ✅ | - |
| `docker-compose.yml`: `docker compose up` starts everything | ❌ db + SearXNG only so far | C |
| `decision_log.json` from the demo run | Code ready (`decision_log.py`); log written at the demo run | all |
| `outputs/` named by phase and step, incl. a gate decision with **stop** | Code ready (`outputs.py`); onboarding writes `phase1_step0_founder_brief.md` | B, all |
| `tests/` smoke tests (pipeline steps, gate, nothing goes out without approval) | 211 tests (onboarding, guardrails, injection cases, log, outputs, gates); approval tests to add | Roufayda |
| `ARCHITECTURE.md` (7 sections, Mermaid) | ❌ | C |
| `.env.example` placeholders only | ✅ | C keeps it complete |
| `prompts/` one file per agent prompt | ✅ onboarding prompts; agents add theirs | all |
| Code names: `gates.py` ✅; `orchestrator.py`, `approval.py`, `agents/<role>.py`, `delivery.py` ❌ | Partly | Roufayda, Menna, Abdelrahman |
| `CLAUDE.md` at root, not in `docs/`; trick prompts only under `tests/` | ✅ | - |

## 5. Timeline (Tuesday)

| When | A | B | C |
|---|---|---|---|
| Done | Onboarding complete; `gates.py` on `main` | | |
| 12:00 | Help B wire the brief into the orchestrator; review guardrail use in agents | Orchestrator + Phase 1 with its gate, incl. STOP | `docker compose up` works from a clean clone |
| 16:00 | Phase 3 Build stage complete; demo script | Orchestrator runs Phases 1-3; pipeline page | Phase 2 + demand gate; phases 4-6 STUBBED |
| **18:00** | **Feature freeze** | | |
| 18:00-21:00 | All: empty `decision_log.json`, delete `outputs/`, run the demo with two briefs (one passes, one gets **stop**), commit both | | |
| 21:00-23:00 | All: fresh clone -> `docker compose up` -> checklist at the end of `CLAUDE.md`; fixes only | | |
| **by 23:00** | Final merge to `main` and push (1 h buffer) | | |

## 6. Demo (3 minutes, unseen brief)

1. Paste the judges' brief into onboarding; show the product check and one refused trick prompt.
2. Confirm the brief (logged with `approved_by: "founder"`).
3. Run Phase 1: sourced opportunities, `ASSUMPTION` labels, the gate decision.
4. Show a **stop** on a weak idea (recorded run if the live one passes).
5. Show `decision_log.json` and the `outputs/` files from the run.
6. Backup: the recorded run and video if the network or model fails.

## 7. Risks

| Risk | Mitigation |
|---|---|
| `docker compose up` fails on the judges' machine | Test from a fresh clone at 21:00; small local model; no keys required |
| Free hosted model rate limits | Local Ollama default; onboarding also works with no model (rule-based) |
| A must-never rule broken by generated text | `check_output()` on every generated text; guardrail tests |
| Mock shown as working | README table and UI labels say MOCKED/STUBBED |
| Late merge conflicts | File ownership in [02-parallel-work.md](02-parallel-work.md); merge small pieces early |
