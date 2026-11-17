"""Rehearsal: load a founder brief from evals/briefs/ and run Discover on it for real (live web and APIs).

Usage: python scripts/run_demo_brief.py evals/briefs/3_weak_chatbot_wrapper.json [--api http://localhost:8010]

The brief is stored as a confirmed brief version whose change note says it is a rehearsal brief from evals/
(fictional persona), with an onboarding session that owns it; the session id is printed so the founder can
decide at the gate in the UI. The run itself goes through the API like any other: nothing in outputs/ is written
by hand. Needs the API, Postgres and SearXNG running.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import psycopg

from venture_os.config import Settings


def load(path: Path) -> tuple[str, str]:
    b = json.loads(path.read_text(encoding="utf-8"))
    bid, sid = str(uuid.uuid4()), str(uuid.uuid4())
    with psycopg.connect(Settings().database_url) as c:  # owner connection: rehearsal setup only
        c.execute("INSERT INTO briefs (id) VALUES (%s)", (bid,))
        c.execute("INSERT INTO brief_versions (brief_id, version, fields, tags, followups, open_questions, "
                  "product_check, budget, change_note) VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s)",
                  (bid, json.dumps(b["fields"]), json.dumps(b["tags"]), json.dumps(b["followups"]),
                   json.dumps(b["open_questions"]), json.dumps(b["product_check"]), json.dumps(b["budget"]),
                   f"Rehearsal brief from evals/briefs/{path.name} (fictional persona)"))
        c.execute("INSERT INTO onboarding_sessions (id, state, brief_id) VALUES (%s, %s, %s)",
                  (sid, json.dumps({"note": "rehearsal brief, no chat"}), bid))
    return bid, sid


def main() -> None:
    path = Path(sys.argv[1])
    api = sys.argv[sys.argv.index("--api") + 1] if "--api" in sys.argv else "http://localhost:8010"
    bid, sid = load(path)
    run = httpx.post(f"{api}/stages/discover/runs", json={"brief_id": bid}, timeout=60).json()
    print(f"brief {bid}\nfounder session {sid}\nrun {run['id']} started")
    t0 = time.monotonic()
    while True:
        run = httpx.get(f"{api}/stages/runs/{run['id']}", timeout=60).json()
        if run["status"] != "running":
            break
        time.sleep(5)
    r = run["output"]["research"]
    print(f"status {run['status']} after {time.monotonic() - t0:.0f}s")
    if r.get("gate"):
        g = r["gate"]
        print(f"recommendation {g['recommendation'].upper()}" + (f" -> {g['pivot_to']}" if g.get("pivot_to") else ""))
        for reason in g["reasons"]:
            print(f"  - {reason}")
        for c in g["checks"]:
            print(f"  {'PASS' if c['passed'] else 'fail'} {c['check']}: {c['actual']} (target {c['target']})")
    print(f"claims {len(r.get('claims') or [])}, ideas {len(r.get('ideas') or [])}, "
          f"competitors {len((r.get('market') or {}).get('competitors') or [])}")


if __name__ == "__main__":
    main()
