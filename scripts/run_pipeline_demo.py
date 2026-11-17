"""Demo run: one founder brief through the whole pipeline, Discover -> Validate -> Build -> Commercial setup.

Usage:
  python scripts/run_pipeline_demo.py evals/briefs/3_weak_chatbot_wrapper.json [--api http://localhost:8010]
  python scripts/run_pipeline_demo.py --brief-id <id> [--api ...]        # continue an existing brief

Every run goes through the stage API like the UI. The script NEVER decides and never enters a number: at each
gate it prints the recommendation and waits until the founder decides in the UI (Pipeline page), and in
Validate it waits until the founder enters the real sign-up count. It stops when the founder says anything other
than go. Needs the API, Postgres and SearXNG running; outputs/ and decision_log.json are written by the API.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_demo_brief import load  # stores a rehearsal brief + the founder session that owns it)

STAGES = ("discover", "validate", "build", "commercial")
WAITING = {"running", "queued"}
POLL = 5


def _get(api: str, path: str, **params):
    return httpx.get(f"{api}{path}", params=params, timeout=60).json()


def _latest(api: str, brief_id: str, stage: str) -> dict | None:
    runs = _get(api, "/stages/runs", brief_id=brief_id, stage=stage)
    if not isinstance(runs, list):
        raise SystemExit(f"[{stage}] API error: {runs}")
    return runs[0] if runs else None


def _gate(stage: str, run: dict) -> dict:
    out = run.get("output") or {}
    if stage == "discover":
        g = (out.get("research") or {}).get("gate") or {}
        return {"outcome": g.get("recommendation"), "reason": " ".join(g.get("reasons") or [])}
    g = (out.get(stage) or {}).get("gate") or {}
    return {"outcome": g.get("outcome"), "reason": g.get("reason")}


def _wait(api: str, run_id: str, until, note: str) -> dict:
    t0, said = time.monotonic(), False
    while True:
        run = _get(api, f"/stages/runs/{run_id}")
        if until(run):
            return run
        if run["status"] == "failed":
            raise SystemExit(f"  run failed: {run.get('output')}")
        if not said:
            print(f"  {note}")
            said = True
        time.sleep(POLL)
        if time.monotonic() - t0 > 4 * 3600:
            raise SystemExit("  gave up after 4 hours")


def run_stage(api: str, brief_id: str, stage: str) -> bool:
    """Start (or continue) one stage, wait for its gate and the founder's decision. True = founder said go."""
    run = _latest(api, brief_id, stage)
    if run is None or run.get("stale") or run["status"] in ("rejected", "revision_requested", "pivoted", "failed"):
        r = httpx.post(f"{api}/stages/{stage}/runs", json={"brief_id": brief_id}, timeout=60)
        if r.status_code != 201:
            print(f"[{stage}] refused: {r.json().get('detail', r.text)}")
            return False
        run = r.json()
        print(f"[{stage}] started run {run['id']}")
    else:
        print(f"[{stage}] continuing run {run['id']} ({run['status']})")
    t0 = time.monotonic()
    if stage == "validate":
        run = _wait(api, run["id"], lambda r: ((r["output"] or {}).get("validate") or {}).get("status")
                    in ("awaiting_signups", "gated") or r["status"] != "running",
                    "building the Lean Canvas, declaring the demand test, drafting the landing page (MOCKED)...")
        t = ((run["output"] or {}).get("validate") or {}).get("demand_test") or {}
        print(f"  demand test declared before measuring: {t.get('target')} {t.get('metric')} in {t.get('days')} days")
        run = _wait(api, run["id"], lambda r: r["status"] != "running",
                    "WAITING FOR THE FOUNDER: enter the real sign-up count on the Pipeline page (never filled in here)")
    else:
        run = _wait(api, run["id"], lambda r: r["status"] != "running", "working...")
    g = _gate(stage, run)
    print(f"  gate after {time.monotonic() - t0:.0f}s: {str(g['outcome']).upper()} - {g['reason']}")
    run = _wait(api, run["id"], lambda r: r["status"] not in ("awaiting_approval", "running"),
                "WAITING FOR THE FOUNDER'S DECISION on the Pipeline page (Go / Repeat / Pivot / Stop)")
    d = (run.get("decisions") or [{}])[-1]
    print(f"  founder decided: {d.get('decision')}" + (f" ({d['note']})" if d.get("note") else "")
          + f" -> {run['status']}")
    return run["status"] == "approved"


def main() -> None:
    args = sys.argv[1:]
    api = args[args.index("--api") + 1] if "--api" in args else "http://localhost:8010"
    if "--brief-id" in args:
        brief_id = args[args.index("--brief-id") + 1]
        print(f"brief {brief_id} (existing; use the founder session that confirmed it)")
    else:
        brief_id, session = load(Path(args[0]))
        print(f"brief {brief_id}\nfounder session {session}  <- paste this on the Pipeline page to decide")
    for stage in STAGES:
        if not run_stage(api, brief_id, stage):
            print(f"pipeline ends at {stage}: the founder did not choose go (or the stage was refused).")
            return
    print("Phases 1-4 approved by the founder. Phase 5 (sell/deliver) is MOCKED and Phase 6 STUBBED.")


if __name__ == "__main__":
    main()
