"""Tests never write to the repository's decision_log.json or outputs/: both go to a temp folder."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_log_and_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.json"))
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))


@pytest.fixture(autouse=True)
def _isolated_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))


@pytest.fixture(autouse=True)
def _no_live_model(monkeypatch):
    """Tests never call a real model, whatever the developer's .env says: rule-based mode (LLM_MODE=none)."""
    monkeypatch.setenv("LLM_MODE", "none")
