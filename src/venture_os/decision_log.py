"""decision_log.json: one entry per agent action (format required by CLAUDE.md).

Every agent, gate and approval calls `log_action(...)`. Required keys are always present:
timestamp, agent, action, sources (list of URLs), model (str or None), cost (USD number), approved_by
("founder" for gated actions, else None). Extra keys (e.g. outcome="stop", brief_id) are allowed.

The file path comes from DECISION_LOG_PATH (default: decision_log.json at the repo root). Tests point it at a
temporary file. Commit only the demo run's log: call `reset_log()` before the demo run.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

REQUIRED_KEYS = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")
_lock = threading.Lock()


def log_path() -> Path:
    return Path(os.environ.get("DECISION_LOG_PATH", "decision_log.json"))


def _read(path: Path) -> list[dict]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def log_action(agent: str, action: str, *, sources: list[str] | None = None, model: str | None = None,
               cost: float = 0.0, approved_by: str | None = None, **extra) -> dict:
    """Append one entry and return it. `approved_by` must be "founder" or None."""
    if approved_by not in (None, "founder"):
        raise ValueError('approved_by must be "founder" or None')
    entry = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent": agent,
        "action": action,
        "sources": list(sources or []),
        "model": model,
        "cost": float(cost),
        "approved_by": approved_by,
        **extra,
    }
    path = log_path()
    with _lock:
        entries = _read(path)
        entries.append(entry)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return entry


def read_log() -> list[dict]:
    return _read(log_path())


def reset_log() -> None:
    """Start a fresh log (before the demo run whose log will be committed)."""
    with _lock:
        log_path().write_text("[]\n", encoding="utf-8")
