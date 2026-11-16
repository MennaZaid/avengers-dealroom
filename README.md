# Venture OS

Open-source, founder-controlled multi-agent system that turns a business idea into evidence-backed,
validated deliverables, stage by stage, with explicit founder approval gates and a full decision log.

> Status: hackathon MVP in progress. Planning: [docs/planning/00-planning-report.md](docs/planning/00-planning-report.md)

## Quick start

```bash
cp .env.example .env          # fill in hosted LLM endpoint for live mode
python scripts/dev.py setup   # install (Python 3.11+; 3.12 recommended)
python scripts/dev.py up      # Postgres + pgvector, SearXNG (Docker)
python scripts/dev.py test
```

`LLM_MODE=replay` (default) uses recorded responses so tests and the demo run offline and reproducibly.

## Principles
- Every claim is typed **fact / inference / assumption**; facts link to a source with retrieval date.
- Stage transitions require a recorded founder approval; external actions need their own scoped approval.
- Open-weight models via any OpenAI-compatible endpoint (hosted primary, Colab vLLM secondary).

## License
Apache-2.0, see [LICENSE](LICENSE).
