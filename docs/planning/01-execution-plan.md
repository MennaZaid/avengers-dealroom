# Venture OS — 30-Hour Execution Plan (current)

> Last updated 2026-11-16. This file replaces the earlier two-stage version and mirrors the shared team doc.
> Decisions D1–D11 are in [00-planning-report.md](00-planning-report.md) §15a. Build status is in [../HANDOFF.md](../HANDOFF.md).

## 1. Overview

Three people have 30 hours each (90 person-hours) to ship an end-to-end demo: **founder onboarding chat → all six
stages (Discover, Validate, Build, Commercial, Launch, Operate), each ending in a founder approval gate**, with every
claim traced to a dated source. **Feature freeze at H20.**

| Decision | Choice |
| --- | --- |
| Spending | **Zero.** No payment method on any account; free tiers, Colab free GPU and local models only (D9) |
| Model hosting | Hosted open-weight API first (free only), Colab vLLM second (D2, D9) |
| Onboarding model | Fanar-C-2-27B via the Fanar API, Arabic incl. Egyptian dialect (D11) |
| Interface | Streamlit (D3) |
| Demo market | Egypt; English and Arabic (D4); the live idea comes from the judges |
| Search | Free only: SearXNG + registry sources; CAPMAS / ITC loaded manually (D6) |
| Licence | Apache-2.0 (D7) |
| CLAUDE.md | Provided later by the team (D1) |

## 2. Any-idea demo

The judges give the idea live, so nothing is hard-coded to one business.
- **Classify, don't hardcode:** the brief is tagged with industry, business model, country and language; tags drive questions, queries and sources.
- **Ask, don't invent:** missing fields become questions; "skip" records them as unknown.
- **Safety net:** if the network or model fails, switch to a recorded run of a rehearsed idea and say so.
- **Rehearse with 3 different ideas** (e.g. a food app, a B2B SaaS tool, a handmade-goods export business).

## 3. Agent system (32 AI roles + 6 control components)

Kinds: **Agent** = AI loop that picks tools (7 in total). **Step** = one model call, fixed output schema.
**Rules** = plain code. No agent has a tool that publishes, sends or spends.

**Control (plain code, shared):** Stage Coordinator, Stage Entry Checker, Evidence Validator, Source Validator,
Permission Broker, Decision Logger.

| # | Stage | Role | Kind | Produces |
|---|---|---|---|---|
| 1 | Onboarding | Brief Analyzer (the onboarding chat) | Step | Tagged brief, gaps, founder questions — **built** |
| 2 | Discover | Research Planner | Step | Sources + queries (AR/EN) |
| 3 | Discover | Source Finder | Agent | Official sources for an uncovered country (12 discovery rules) |
| 4 | Discover | Market Research | Agent | Market size, trends, demand signals with sources |
| 5 | Discover | Competitor Intelligence | Agent | Competitors, sites, apps, prices |
| 6 | Discover | Evidence Extractor | Step | Claims with exact quote, source, date |
| 7 | Discover | Audience Hypotheses | Step | Segments labelled as hypotheses |
| 8 | Discover | Opportunity Synthesizer | Step | Problems/gaps, evidenced or marked assumption |
| 9 | Discover | Research Critic | Step (different model family) | Weak reasoning, contradictions, overclaims |
| 10 | Validate | Review and Sentiment Miner | Agent | Verbatim quotes grouped into pain points |
| 11 | Validate | Competitor Benchmark | Step | Feature/price table, one source per cell |
| 12 | Validate | Value Proposition | Step | Evidenced pains mapped to solution |
| 13 | Validate | Experiment Designer | Step | Tests with metric, threshold, cost |
| 14 | Validate | Go / Revise / Stop | Step | Evidence-ladder score and recommendation |
| 15 | Build | Product Requirements | Step | PRD, user stories, prioritised MVP features |
| 16 | Build | UX Flow Designer | Step | Screens, flow, wireframe spec |
| 17 | Build | Architecture and Data Model | Step | Stack and schema |
| 18 | Build | MVP Builder | Agent (code, sandboxed) | Landing page + core flow from a fixed template |
| 19 | Build | QA and Security Reviewer | Step + tools | Tests, dependency and secret scan |
| 20 | Commercial | Pricing Research | Agent | Sourced competitor prices, pricing hypotheses |
| 21 | Commercial | Cost and Unit Economics | Step + calculator | Costs, break-even, labelled estimates |
| 22 | Commercial | Business and Revenue Model | Step | Revenue model, canvas |
| 23 | Commercial | Legal and Compliance Research | Agent | Country requirements from official sources only, or "unavailable" |
| 24 | Commercial | Commercial Readiness Checker | Rules | Checklist |
| 25 | Launch | Go-to-Market and Positioning | Step | Positioning, messaging, channels |
| 26 | Launch | Content Creator | Step | Drafts only, never sent |
| 27 | Launch | Launch Planner | Step | Calendar, checklist, KPIs |
| 28 | Launch | Launch Readiness Validator | Rules | Every external action has its own approval request |
| 29 | Operate | Metrics Collector | Rules | Real events from the MVP, real vs projected |
| 30 | Operate | Feedback Analyzer | Step | Themes from real feedback |
| 31 | Operate | Experiment and Growth Advisor | Step | Ranked next experiments |
| 32 | Operate | Roadmap and Learning Report | Step | Roadmap; flags earlier stages for revalidation |

## 4. Stage depth in 30 hours

| Stage | Depth | Live demo shows |
|---|---|---|
| Onboarding | **Built** | Arabic/English chat, document upload, confirm-before-save |
| 1 Discover | Full | Live searches, AR/EN sources, claims with quotes and dates |
| 2 Validate | Full | Review quotes, competitor table, evidence ladder, Go/Revise/Stop |
| 3 Build | Thin | PRD; MVP Builder fills a landing-page template for the judges' idea |
| 4 Commercial | Thin | Sourced pricing; cost calculator; Egypt legal pack or visible "no verified source" |
| 5 Launch | Thin | Drafts; Publish blocked until a scoped approval |
| 6 Operate | Thin | Real visits from judges opening the landing page |

Thin stages are built from one shared stage template. Sample data is labelled DEMO DATA; projections are labelled
estimates; nothing is published, sent or paid for.

**Cut order** (decided at H14): merge Audience Hypotheses into Opportunity Synthesizer and UX Flow into Product
Requirements → drop Source Finder (use the Egypt pack) → make QA a plain test run. Stages and gates are never cut.

## 5. Roles

| Person | Owns | Folders |
|---|---|---|
| P1 – Core, Control & Operate | Stage template (coordinator, entry check, gate), approvals, decision log, permission broker, evidence validator rules, CI/evals, Stage 6 analytics + dashboard | core/, db/, api/, security/, stages/operate/, evals/, .github/ |
| P2 – Evidence & Agents | Model router + replay, SearXNG search, fetch/extract (AR/EN), pgvector hybrid search, registry + source validator, the 7 agents | llm/, tools/, evidence/, registry/, agents/ |
| P3 – Stages, UI & Demo | Steps and workflows for Stages 1–5, Streamlit screens, landing-page template, demo script, pitch | stages/, ui/, templates/, docs/demo.md |

## 6. Timeline

| Hours | P1 – Core, Control, Operate | P2 – Evidence and Agents | P3 – Stages, UI and Demo |
|---|---|---|---|
| H0–2 | *All: freeze shared models and the stage template interface* | | |
| H2–6 | Stage template: coordinator, entry check, gate | Model router + replay, JSON repair | Streamlit shell around the existing onboarding chat |
| H6–10 | Permission broker, scoped approvals, decision log | SearXNG search (AR+EN), fetch + extract, dated | Stage 1 Discover: planner, extractor, synthesis |
| H10–14 | Evidence validator rules; DB role tests in CI | Hybrid search (pgvector); market + competitor agents | Stage 2 Validate; gate UI approve/revise |
| H14–18 | Stage 6 Operate: analytics events + dashboard | Review miner, pricing agent, legal agent (Egypt pack) | Stages 3–5 from template: PRD, MVP Builder, drafts |
| H18–20 | End-to-end integration, all six stages on replay | Record runs for 3 ideas; Source Finder + validator | Evidence and decision-log views |
| **H20** | **Feature freeze** | | |
| H20–24 | Scoring script, CI results page | Fix grounding failures; live run, re-record | Demo script; dry run with 3 ideas |
| H24–27 | Docs: architecture, safety, measured usage | Colab notebook (self-hosted proof) | Pitch deck; rehearsal 1; backup video |
| H27–30 | Bug fixes, CI green, tag v0.1 | Bug fixes, help rehearse | Rehearsal 2, polish |

## 7. Checkpoints

| Hour | Must be true | Fallback |
|---|---|---|
| H6 | Model call works live and on replay; a dummy stage runs through the template and stops at its gate | One model profile; hard-code the gate screen |
| H10 | Onboarding → confirmed brief → Discover produces dated, sourced claims | Merge Audience into Opportunity |
| H14 | Discover and Validate run end to end with both gates, on replay | Drop Source Finder; use the Egypt pack |
| H20 | All six stages run on replay with gates; landing page records a visit on the dashboard | Stages 4–5 one step each; merge UX into PRD |
| H27 | CI green; rehearsed with 3 different ideas | Fixes only |

## 8. Tests each person owns (CI, recorded responses, no secrets)

- **P1:** stage N+1 can't start without approval of N; reject → revise → re-approve logged; external action blocked without scoped approval; audit-chain tamper detection; registry role checks (tests/sql/registry_roles.sql) moved into CI.
- **P2:** replay deterministic; documents have retrieval date + hash; duplicates merged; registry YAML valid; Arabic survives extraction; source validator rules (done).
- **P3:** step outputs match schemas; every fact claim has evidence; golden demo run passes; no "guaranteed income" phrasing; onboarding flow (done).

## 9. Demo definition of done

- [x] Founder onboarding chat in Arabic/English with document upload, confirm before save
- [ ] Discover runs; trace shows real searches and fetched AR/EN sources
- [ ] Validator flags an out-of-date or unsourced claim
- [ ] Founder rejects a section, only that step re-runs, then approves
- [ ] Validate: review quotes, competitor table, evidence ladder, Go/Revise/Stop
- [ ] Build: PRD and a working landing page for the judges' idea
- [ ] Commercial: sourced pricing, cost estimate, legal from official sources or "no verified source"
- [ ] Launch: drafts; Publish blocked until scoped approval
- [ ] Operate: real visits from judges, marked real data
- [ ] Changing the brief marks later stages Stale
- [ ] Decision log shows all of the above; CI results page shows latest commit's score

## 10. Risks

| Risk | Mitigation |
|---|---|
| Integration breaks at H18 | Shared models frozen at H2; syncs at H6/H10/H14 |
| Free model tiers rate-limit during the demo (Fanar: 50 req/min) | Cache; recorded backup run; rule-based fallbacks keep onboarding working with no model |
| Free model access changes or is not actually free | Confirm Fanar terms; keep Colab + local fallback; D9 forbids paid fallback |
| SearXNG rate-limited by engines | Cache fetches; demo on replay |
| CAPMAS/ITC slow or blocked | Download 2–3 tables by H10, ingest manually |
| Team exhaustion | Two staggered 3-hour rest blocks per person |
