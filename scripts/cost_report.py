"""Cost per run, measured from decision_log.json (the model_call entries written by llm/client.py).

    python scripts/cost_report.py                    # whole log (commit only the demo run's log)
    python scripts/cost_report.py --log path.json

Prints e.g. "About $0.00 per run (local qwen3:4b-instruct, ~12,345 tokens)". Nothing is estimated: a log
without model calls says so.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from venture_os.decision_log import log_path


def summarize(entries: list[dict]) -> dict:
    per_model: dict[str, dict] = {}
    for e in entries:
        if e.get("action") != "model_call":
            continue
        m = per_model.setdefault(e.get("model") or "unknown", {"calls": 0, "prompt_tokens": 0,
                                                               "completion_tokens": 0, "cost": 0.0})
        m["calls"] += 1
        m["prompt_tokens"] += int(e.get("prompt_tokens") or 0)
        m["completion_tokens"] += int(e.get("completion_tokens") or 0)
        m["cost"] += float(e.get("cost") or 0)
    tokens = sum(m["prompt_tokens"] + m["completion_tokens"] for m in per_model.values())
    cost = sum(m["cost"] for m in per_model.values())
    return {"per_model": per_model, "tokens": tokens, "cost": cost,
            "agent_actions": len(entries), "model_calls": sum(m["calls"] for m in per_model.values())}


def line(summary: dict) -> str:
    if not summary["per_model"]:
        return "About $0.00 per run (no model calls in this log: rule-based run)"
    models = ", ".join(sorted(summary["per_model"]))
    where = "local " if summary["cost"] == 0 else ""
    return f"About ${summary['cost']:.2f} per run ({where}{models}, ~{summary['tokens']:,} tokens)"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Sum tokens and cost per model from decision_log.json")
    p.add_argument("--log", default=None, help="path to decision_log.json (default: DECISION_LOG_PATH)")
    a = p.parse_args(argv)
    path = Path(a.log) if a.log else log_path()
    entries = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    s = summarize(entries)
    print(line(s))
    for model, m in sorted(s["per_model"].items()):
        print(f"  {model}: {m['calls']} calls, {m['prompt_tokens']:,} prompt + {m['completion_tokens']:,} "
              f"completion tokens, ${m['cost']:.2f}")


if __name__ == "__main__":
    main()
