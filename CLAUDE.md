# CLAUDE.md: DealRoom VC copilot

This repo supports a team in **The DealRoom** (ES x MADS, AUC): a simulated VC fund of **USD 1,000,000** choosing among 13 pre-seed/seed startups (see data/briefing.txt). **Deck as PDF emailed by Fri 27 Nov 2026, 15:00**; filtration 16:00 (5-min pitch + Q&A, every member presents); final Sat 28 Nov. Deliver: picks + weights + reserve, year-5 value after dilution (base + downside), and the why. Equity % = cheque ÷ post-money.

## Pipeline (`python -m dealroom.run`)
1. **Brief** - `data/evidence.yaml`: per-startup claims, each a verbatim `quote` with a `source` (`deck`, `video`, `deck_image:<page>`, or a URL).
2. **Verify** - `dealroom/verify.py` checks each quote really appears in the source text; failures are flagged, never silently kept.
3. **Validate** - `data/scores.yaml` is the team's scorecard (1-5 per criterion, with a reason). Scorecard-method and Berkus valuations are computed from it.
4. **Portfolio** - allocates the $1M under `data/rules.yaml`; every ticket needs a human approve/override (`--approve`).

## Rules
- Founder claims stay labelled DECK / VIDEO; outside facts need a URL; anything else is `ASSUMPTION`.
- Video transcripts are machine-made: check names and numbers against the video before putting them on a slide.
- Never hand-write `outputs/`; regenerate with the pipeline.
- Never commit secrets or `.env`.
