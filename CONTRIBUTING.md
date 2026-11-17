# Contributing

## Run

```bash
docker compose up
```

Open http://localhost:8501. No `.env` or keys needed; copy `.env.example` to `.env` only to change a setting.

## Test

```bash
pip install -e ".[dev]"   # Python 3.12
pytest -q
ruff check .
```

Tests never call a live model (`tests/conftest.py` forces replay mode). Database tests need the `db` service
from `docker compose up` (`DATABASE_URL` in `.env.example`); without it they are skipped or fail to connect.

## Pull requests

1. Branch from `main`; keep changes small.
2. `ruff check .` and `pytest -q` must pass.
3. Follow `CLAUDE.md`: label mocks MOCKED/STUBBED, never commit `.env` or keys, never hand-write `outputs/`.
4. Open a PR to `main` describing what changed and how you tested it.
