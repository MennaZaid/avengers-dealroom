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
import re
import threading
from datetime import UTC, datetime
from pathlib import Path

REQUIRED_KEYS = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")
_lock = threading.Lock()


# Gate decision entries (not threshold settings) must also carry an "outcome".
_GATE_DECISION = re.compile(r"(_gate|_gate_decision|_gate_passed|_gate_pass_refused|^evaluate_\w+_gate)$")


def validate_entry(e: dict) -> dict:
    """Raise ValueError if `e` does not follow the decision_log.json format; return it unchanged otherwise."""
    missing = [k for k in REQUIRED_KEYS if k not in e]
    if missing:
        raise ValueError(f"decision_log entry missing keys: {missing}")
    problems = []
    if not isinstance(e["timestamp"], str) or not e["timestamp"]:
        problems.append("timestamp must be a non-empty string")
    for k in ("agent", "action"):
        if not isinstance(e[k], str) or not e[k].strip():
            problems.append(f"{k} must be a non-empty string")
    if not isinstance(e["sources"], list) or not all(isinstance(u, str) for u in e["sources"]):
        problems.append("sources must be a list of strings (URLs)")
    if e["model"] is not None and not isinstance(e["model"], str):
        problems.append("model must be a string or null")
    if isinstance(e["cost"], bool) or not isinstance(e["cost"], (int, float)) or e["cost"] < 0:
        problems.append("cost must be a number >= 0 (USD)")
    if e["approved_by"] not in (None, "founder"):
        problems.append('approved_by must be "founder" or null')
    if e.get("agent") == "gate" and isinstance(e.get("action"), str) and _GATE_DECISION.search(e["action"])             and not (isinstance(e.get("outcome"), str) and e["outcome"]):
        problems.append("a gate decision entry needs an outcome")
    if problems:
        raise ValueError("bad decision_log entry: " + "; ".join(problems))
    return e


def _sources(sources) -> list:
    """A list of URLs. A single string is refused (list("https://...") would silently split it into letters)."""
    if isinstance(sources, (str, bytes)):
        raise TypeError("sources must be a list of URLs, not a single string")
    return list(sources or [])


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
        "sources": _sources(sources),
        "model": model,
        "cost": float(cost),
        "approved_by": approved_by,
        **extra,
    }
    validate_entry(entry)
    path = log_path()
    with _lock:
        entries = _read(path)
        entries.append(entry)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return entry


def log_actions(calls: list[dict]) -> list[dict]:
    """Append many entries with one file write (a pipeline run logs ~100 actions). Each item holds the same
    arguments as log_action: agent, action, and optional sources/model/cost/approved_by/extra keys."""
    entries = []
    for c in calls:
        c = dict(c)
        approved_by = c.pop("approved_by", None)
        if approved_by not in (None, "founder"):
            raise ValueError('approved_by must be "founder" or None')
        entries.append({
            "timestamp": c.pop("timestamp", None) or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent": c.pop("agent"),
            "action": c.pop("action"),
            "sources": _sources(c.pop("sources", None)),
            "model": c.pop("model", None),
            "cost": float(c.pop("cost", 0.0)),
            "approved_by": approved_by,
            **c,
        })
        validate_entry(entries[-1])
    if not entries:
        return entries
    path = log_path()
    with _lock:
        current = _read(path)
        current.extend(entries)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
    return entries


def read_log() -> list[dict]:
    return _read(log_path())


def entries_for(session_id: str | None = None, brief_id: str | None = None) -> list[dict]:
    """Entries of one conversation: its session_id, or its brief_id (stages after onboarding log under it)."""
    ids = {("session_id", session_id), ("brief_id", brief_id)} - {("session_id", None), ("brief_id", None)}
    return [e for e in read_log() if any(e.get(k) == v for k, v in ids)]


def reset_log() -> None:
    """Start a fresh log (before the demo run whose log will be committed)."""
    with _lock:
        log_path().write_text("[]\n", encoding="utf-8")
