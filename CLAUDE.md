# CLAUDE.md: DealRoom VC copilot

This repo supports a team in **The DealRoom** (ES x MADS, AUC): a simulated VC fund of **USD 1,000,000** choosing among 14 pre-seed/seed startups. Portfolio + presentation due **Fri 27 Nov 2026, 16:00**.

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
