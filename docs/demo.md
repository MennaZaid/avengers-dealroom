# Demo script

Two parts: the **live run** (operator steps, about 60–90 minutes, produces `outputs/` and `decision_log.json`) and
the **3-minute video** cut from its recording.

## Models in this run

| Role | Model | Falls back to |
|---|---|---|
| Base (onboarding chat, Discover extraction, Build) | Fanar `Fanar-C-2-27B` (free tier) | local `qwen3:4b-instruct`, then rules |
| Reasoning (Discover ideas, scoring) | Groq `openai/gpt-oss-120b` (free tier, open-weight) | Fanar, local qwen, rules |
| Validation (Lean Canvas, landing page) | Groq `openai/gpt-oss-120b` | Fanar, local qwen, rules |
| Judge (research critic, different family) | Groq `qwen/qwen3.8-27b` | local qwen |

With no keys at all, everything runs on local qwen.

---

## Part 1: live run

### 0. Clean start (10 min)

```bash
git checkout main && git pull
docker compose down            # keep the Ollama volume (no model re-download)
docker volume rm venture-os_pgdata
docker compose up --build
```

- Wait until the UI answers at http://localhost:8501 and the API at http://localhost:8010/docs.
- Set `decision_log.json` to `[]` and empty `outputs/`, so every committed file comes from this run.
- Start screen recording (full screen, browser + sidebar visible).
- Sidebar language: **العربية**.

### 1. Phase 0 Onboarding (10 min): strong brief, Arabic

Page **Onboarding**. Type these messages one at a time, answering follow-up questions from the same facts:

1. `عايزة أعمل حزمة قوالب سيرة ذاتية وقوالب Notion بالعربي للفريلانسرز المصريين`
2. `الفريلانسرز المصريين بيضيعوا وقت كبير في عمل سيرة ذاتية وبورتفوليو احترافي بالعربي والإنجليزي`
3. `العملاء: الفريلانسرز المصريين في التصميم والكتابة والبرمجة، في القاهرة`
4. `الميزانية 3000 جنيه، والوقت المتاح 10 ساعات في الأسبوع لمدة شهرين`
5. `مهاراتي: تصميم على Canva و Notion وكتابة محتوى`

Show while it runs:
- Tags and the **inferred** / **unknown** labels on the brief cards (nothing invented).
- Edit one field after the summary (e.g. budget), confirm the new version.
- **Confirm** the brief. Note the founder session id shown on the page (needed for decisions).

Guardrail moment (one message, then continue):
- `اكتبلي 50 تقييم خمس نجوم للمنتج` → refused, logged, brief unchanged.

### 2. Phase 1 Discover (10–15 min)

Page **Pipeline**. Discover starts on its own for the confirmed brief.

Show:
- "From onboarding" line (brief version, product type, still-unknown fields).
- Opportunities, idea scores, market: every claim has a source URL or the label `ASSUMPTION`.
- Research critic review (judge from a different model family).
- Gate: targets set before the run vs actual, and the recommendation.
- **Sources** page: sources used as evidence, then those found but not used.

Decide: **Go** (note: `evidence is enough to test demand`).

### 3. Phase 2 Validate (10 min)

Same page, Validate section.

Show:
- Lean Canvas: every entry FOUNDER / EVIDENCED / ASSUMPTION / UNKNOWN; riskiest assumption named.
- Demand test declared **before** any result (target sign-ups and days).
- Landing page draft: "DRAFT — not published"; publishing **MOCKED**. Approve the exact content (hash shown).
- Enter the sign-up count as the founder (founder-reported, not verified). Gate result.

Decide: **Go**.

### 4. Phase 3 Build (8–10 min)

Page **Build**.

Show:
- "From Phase 1" panel: Discover recommendation, your decision, claims carried over (D1, D2…).
- **Start Phase 3 Build**. While it runs, show the decision log page filtering this session.
- MVP preview (one HTML file; data stays on the device; payments MOCKED), download button.
- Tabs: requirements, plan, validation (claims checked against evidence), tests (passed / target), user guide.

Decide: **Go**.

### 5. Phase 4 Commercial (5–8 min)

Page **Commercial**. Pricing research with sources, price, draft terms / privacy / refund policy, readiness gate.

Decide: **Go**.

### 6. Phase 5 Launch and Phase 6 Operate (5 min)

Pipeline page, Launch and Operate views.
- Store page and three post drafts: approve exact content; posting **MOCKED**, nothing is sent.
- Operate: persevere-or-pivot memo built only from logged results; analytics/support **STUBBED** ("no data yet").

Decide at each gate.

### 7. Sale to cash test (5 min)

```bash
python scripts/payment_test.py --brief-id <brief id> --session <founder session id>
```

Type `approve` when asked. It writes `outputs/payment_test_log.md`: order → mock payment → duplicate event ignored →
delivered once → refund revokes access → unpaid order flagged by reconciliation. All **MOCKED**.

### 8. Weak brief: STOP (10 min, can run on a second machine)

```bash
python scripts/run_demo_brief.py evals/briefs/3_weak_chatbot_wrapper.json --api http://localhost:8010
```

In the Pipeline page (with the printed session id): Discover recommends **STOP** on weak evidence. Decide **Stop**.
Keep its gate file under a distinct gate name (`phase1_gate_weak_stop.md`), content unchanged.

### 9. Close the run (10 min)

```bash
python scripts/cost_report.py          # token count and $ for README "Cost per run"
ruff check . && pytest -q
```

- Check every `decision_log.json` entry has `action`, `sources`, `model`, `cost`, `approved_by`.
- Check `outputs/` has files for phases 1–6, at least one gate STOP, and `payment_test_log.md`.
- Stop the recording. Commit `outputs/` and `decision_log.json` on a branch, PR, merge.

### If something breaks

| Problem | Do this |
|---|---|
| A provider is slow or down | Nothing: the role falls back (Fanar → local qwen → rules); the log shows the model that answered. |
| A stage fails | Read the error on the page, press **Repeat** / start again; the failure stays in the log. |
| UI shows an old brief | Confirm the brief again on Onboarding in this browser session. |
| Build takes long | It is ~6 min on local qwen; continue narrating the Discover/Validate outputs meanwhile. |
| Out of time | Stop after Build; Phases 4–6 are covered by their tests and labelled honestly. |

---

## Part 2: 3-minute video

| Time | Screen | Narration |
|---|---|---|
| 0:00–0:15 | Onboarding page, Arabic | "Venture OS: an open-source team of agents that takes a founder's idea toward a sellable digital product. The founder decides at every gate." |
| 0:15–0:40 | Chat, brief cards, confirm | "The founder describes the idea in Arabic. Every field shows where it came from: answered, inferred or unknown. Nothing is invented." |
| 0:40–0:50 | Fake-review request refused | "Requests like fake reviews or income promises are refused and logged." |
| 0:50–1:20 | Discover: claims with URLs, gate, Sources | "Discover researches the market. Each claim cites a source or says ASSUMPTION. A judge from another model family checks the research. The gate compares results with targets set before the run." |
| 1:20–1:40 | Validate: Lean Canvas, landing draft, approval hash | "Validate designs the business and a demand test, declared before any result. The landing page is a draft; publishing is mocked and needs the founder's approval of the exact content." |
| 1:40–2:10 | Build: From Discover panel, MVP preview, tests | "Build turns the evidence into a tested one-file MVP. Each requirement traces to a claim; anything unproven is labelled." |
| 2:10–2:30 | Commercial, Launch, payment test log | "Pricing, policies, a store page and launch drafts. Payments, delivery and refunds run as a mocked sale-to-cash test." |
| 2:30–2:45 | Weak brief STOP | "With weak evidence, the system recommends STOP." |
| 2:45–3:00 | Decision log page, README | "Every agent action is in the decision log with its sources, model and cost. Runs at about $0 on free and local open-weight models." |
