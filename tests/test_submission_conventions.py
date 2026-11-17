"""Layout and README conventions from CLAUDE.md (the fast part of scripts/audit_submission.py)."""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location("audit_submission",
                                               Path(__file__).resolve().parents[1] / "scripts" / "audit_submission.py")
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


@pytest.mark.parametrize("name", list(audit.LAYOUT_CHECKS))
def test_layout_and_readme(name):
    assert audit.LAYOUT_CHECKS[name]() == []


def test_required_files_exist():
    for f in ("README.md", "LICENSE", "decision_log.json", "ARCHITECTURE.md", ".env.example"):
        assert (audit.ROOT / f).is_file(), f
    assert (audit.ROOT / "docker-compose.yml").is_file() or (audit.ROOT / "compose.yaml").is_file()
    assert (audit.ROOT / "outputs").is_dir() and (audit.ROOT / "tests").is_dir()
