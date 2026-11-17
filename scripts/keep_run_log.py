"""Keep only one demo run's entries in decision_log.json (entries unchanged, same order).

    python scripts/keep_run_log.py <brief_id> <founder_session_id> [--write]

Window: from the brief's confirm_brief entry to the last entry in the file. Inside it, an entry is kept when it
belongs to this brief (its brief_id, or the run_id of one of this brief's stage runs) or carries no brief at all
(model calls and stage steps logged without one). Entries for any other brief are dropped and listed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg

from venture_os.config import Settings

REQUIRED = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")


def main() -> None:
    brief = sys.argv[1]
    path = Path("decision_log.json")
    log = json.loads(path.read_text(encoding="utf-8"))
    with psycopg.connect(Settings().database_url) as conn:
        runs = {str(r[0]) for r in conn.execute("SELECT id FROM stage_runs WHERE brief_id = %s", (brief,))}
    session = sys.argv[2]
    start = next(i for i, e in enumerate(log) if e.get("action") == "confirm_brief"
                 and (e.get("brief_id") == brief or e.get("session_id") == session))
    kept, dropped = [], []
    for e in log[start:]:
        other_brief = e.get("brief_id") not in (None, brief) or e.get("session_id") not in (None, session)
        other_run = e.get("run_id") is not None and str(e["run_id"]) not in runs
        (dropped if other_brief or other_run else kept).append(e)
    print(f"before {len(log)} | before window {start} | in window {len(log) - start} | kept {len(kept)} | "
          f"dropped in window {len(dropped)}")
    for e in dropped[:20]:
        print("  dropped:", e["timestamp"], e["agent"], e["action"], e.get("brief_id") or e.get("run_id"))
    missing = [e for e in kept if any(k not in e for k in REQUIRED)]
    print("kept entries missing a required key:", len(missing))
    print("window:", kept[0]["timestamp"], "->", kept[-1]["timestamp"])
    if "--write" in sys.argv:
        path.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("written")


if __name__ == "__main__":
    main()
