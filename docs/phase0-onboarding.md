# Phase 0: Onboarding (founder brief), method detail

Summary and status: [ARCHITECTURE.md](../ARCHITECTURE.md#phase-0-onboarding-founder-brief--working).

- **Agents:** brief extractor, brief tagger, follow-up writer (prompts in `prompts/brief_*.md`,
  `prompts/followup_questions.md`); code in `src/venture_os/onboarding/`.
- **Tools:** document reader (PDF, Word, text; text only, 10 MB limit), budget parser, product check,
  guardrails. Model: Fanar-C-2-27B (Arabic incl. Egyptian dialect, English) via a free API; with no model the
  chat still works rule by rule.
- **Method:** a chat asks for the 7 required fields (idea, problem, customer, country, budget, time, skills),
  offers 5 optional ones, then up to 3 follow-up questions only the founder can answer. Research questions are
  passed to Discover instead of being asked. A value from the model is kept only if its quote appears in the
  founder's text; "skip" stores *unknown*, never a guess. Document text is treated as untrusted data.
- **Output:** a versioned brief (`brief_versions` table), tags used to choose sources (country code,
  industries, customer type, revenue model), and `outputs/phase1_step0_founder_brief.md` on confirmation.
