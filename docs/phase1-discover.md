# Phase 1: Discover, method detail

Summary, status and diagram: [ARCHITECTURE.md](../ARCHITECTURE.md#phase-1-discover--working-core-step-find-opportunities).

Starts when the founder confirms the brief (that confirmation is the approval to research); `orchestrator.py`
runs the steps below and ends at the founder's gate. Gate thresholds are read from `config/gates/discover.yaml`
and logged (`set_gate_thresholds`) **before** any research.


- **Agents (`agents/`):** `brief_analyzer`, `research_planner`, `market_research` and `competitor_intelligence`
  (tool-using `ResearchAgent`s), `opportunity_finder`, `idea_scorer`, `market_definer`, `interview_designer`,
  `research_critic`. Prompts: one file each in `prompts/`.
- **Tools:** SearXNG (spaced queries), page fetcher, free APIs with no key (HN Algolia, Stack Exchange, GitHub,
  iTunes Search and App Store reviews, WordPress plugins, npm, World Bank), the source registry filtered by
  `product_scope` (digital/any; goods-trade sources excluded), and hybrid search (keyword + `bge-m3` vectors) over
  the evidence store and the method corpus (team-written summaries with links, never book text).
- **Method:**
  1. Brief: the six required fields; unknown stays unknown. The product type is decided by rules and must be
     digital; excluded products are refused before any research.
  2. Opportunities: find people describing the pain. A claim is kept only with a verbatim quote found in the
     stored page, its URL and dates. Page text is data: instructions inside pages are ignored and logged. Then the
     founder's idea is sharpened and alternatives are proposed for the same pain.
  3. Scoring: 1–5 per criterion against the founder's skills, hours and budget. A score without evidence is
     capped at 3 and labelled `ASSUMPTION`, and totals are computed in code.
  4. Market: competitors and substitutes with sourced prices, and a bottom-up TAM/SAM/SOM where every input is
     either sourced or labelled `ASSUMPTION`.
  5. Interviews (The Mom Test):
     - a script linter rejects hypothetical, pitching and compliment-seeking questions (EN + AR) and rewrites
       them about past behaviour;
     - the founder's notes are tagged, and only past behaviour, current workarounds, money or time already spent
       and commitments count as evidence.
  6. Critic: rule checks, plus a second-opinion model of a **different family** when one is configured (otherwise the
     critic says the model review was skipped).
- **Output:** `phase1_step1_brief`, `phase1_step2_opportunities`, `phase1_step3_idea_scores`, `phase1_step4_market`,
  `phase1_step5_interview_plan` and `phase1_gate_decision` (`.md` + `.json` each).
