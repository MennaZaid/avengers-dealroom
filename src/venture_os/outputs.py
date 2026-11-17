"""outputs/: demo-run results named the way CLAUDE.md requires.

    write_output(1, 1, "opportunities", md)          -> outputs/phase1_step1_opportunities.md
    write_output(1, None, "decision", md, gate=True)  -> outputs/phase1_gate_decision.md

Only the pipeline writes here (never by hand). Text formats only. Directory from OUTPUTS_DIR (default outputs/).
Every write runs the guardrail check first (guardrails.scrub_output): a span that breaks a must-never rule is
replaced by [REMOVED by guardrails: <rule>] and the removal is logged, so no output carries it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

TEXT_EXTS = {"md", "json", "csv", "txt", "html"}


def outputs_dir() -> Path:
    return Path(os.environ.get("OUTPUTS_DIR", "outputs"))


def output_name(phase: int, step: int | None, name: str, ext: str = "md", gate: bool = False) -> str:
    if not 1 <= phase <= 6:
        raise ValueError("phase must be 1-6")
    if ext not in TEXT_EXTS:
        raise ValueError(f"outputs must be text: {sorted(TEXT_EXTS)}")
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "output"
    if gate:
        return f"phase{phase}_gate_{slug}.{ext}"
    if step is None or step < 0:
        raise ValueError("step is required unless gate=True")
    return f"phase{phase}_step{step}_{slug}.{ext}"


def write_output(phase: int, step: int | None, name: str, content: str, ext: str = "md", gate: bool = False) -> Path:
    return write_named(output_name(phase, step, name, ext, gate), content)


def write_named(filename: str, content: str) -> Path:
    """The one write path into outputs/ (also for fixed names such as payment_test_log.md): the guardrail check
    runs first."""
    from venture_os.guardrails import scrub_output

    if "/" in filename or "\\" in filename or filename.rsplit(".", 1)[-1] not in TEXT_EXTS:
        raise ValueError(f"outputs/ takes plain text file names only: {filename!r}")
    content, fired = scrub_output(content)
    if fired:
        from venture_os.decision_log import log_action

        log_action("guardrails", "refuse_output", sources=[], model=None, cost=0, approved_by=None, file=filename,
                   rules=fired)
    path = outputs_dir() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
