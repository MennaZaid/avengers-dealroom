# Avengers Capital · DealRoom Copilot

Team Avengers' investment-committee console for **The DealRoom** (ES × MADS, AUC): a simulated **USD 1,000,000** fund choosing among 13 pre-seed/seed startups.

It reads every startup's deck, founder video and financial model. Each claim is checked word for word against those files, markets and competitors are researched on the web with cited sources, and every startup is scored and valued. The tool then proposes how to split the $1M, forecasts the portfolio at year 5 (base case and downside, after dilution), and leaves every cheque to a human approve or reject.

## Run it

```powershell
pip install -r requirements.txt
copy .env.example .env      # add your free Groq / Fanar keys
streamlit run dealroom_app.py
```

Open http://localhost:8501. It also works on a phone. For hosting, see [DEPLOY.md](DEPLOY.md).

## Tabs

| Tab | What it shows |
|---|---|
| Portfolio | Every startup: score, valuation, their ask, our cheque and stake |
| Year 5 | Forecast after dilution (base and downside), runway, the milestone each cheque funds, and the cited benchmarks behind it |
| Startups | Full dossier per startup; edit the scorecard and the portfolio recalculates |
| Research | Web findings per startup with verdicts (supported / contradicted / context / unverified) and links |
| Analyst | A chatbot that answers only from our data room |
| Approve | Team sign-off on each cheque |
| Glossary | Plain-English VC terms ([for-the-team/GLOSSARY.md](for-the-team/GLOSSARY.md)) |
| Rules | Fund size, reserve, ticket limits, score bar |

## Pipeline (command line)

| Step | Command | Writes |
|---|---|---|
| Verify claims, score, value, allocate | `python -m dealroom.run` (`--approve` to sign off) | `outputs/dealroom/portfolio.md` |
| Web research per startup | `python -m dealroom.research [Startup ...]` | `data/research/*.json` |
| Forecast benchmarks (dilution, multiples) | `python -m dealroom.benchmarks` | `data/benchmarks.json` |
| Data room for the chatbot and the deck | built automatically by the app | `outputs/dealroom/data_room.md` |
| Smoke tests | `python -m pytest tests` | |

Re-running the research needs the local search engine: `docker compose -p dealroom up -d searxng`.

## What you edit

- `data/scores.yaml`: the team's 1–5 scorecard and reasoning
- `data/forecast.yaml`: year-5 values, burn rates and dilution; every input is labelled SOURCE, MODEL, DECK or ASSUMPTION
- `data/rules.yaml`: fund rules
- `data/evidence.yaml`: quoted founder claims (checked automatically)

## Honesty rules

Founder claims stay labelled DECK / VIDEO / MODEL. Web facts carry a URL, and anything else is labelled ASSUMPTION. Video transcripts are machine-made, so check names and numbers against the video before putting them on a slide. Models used: free tiers only (Groq `gpt-oss-120b`, Fanar), so it costs $0 per run.

Built by **Team Avengers**: Assemble.
