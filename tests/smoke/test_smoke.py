from pathlib import Path

import venture_os
from venture_os.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_package_imports():
    assert venture_os.__version__


def test_default_mode_is_replay(monkeypatch):
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert Settings(_env_file=None).llm_mode == "replay"


def test_required_repo_files_exist():
    for name in ["README.md", "LICENSE", ".env.example", "docker-compose.yml"]:
        assert (ROOT / name).is_file(), name
