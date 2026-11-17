"""Phase 2 Validate: the demand test result and its gate. The sign-up count is ENTERED BY THE FOUNDER.

    from venture_os.agents.demand_test import enter_signups
    decision = enter_signups(brief_id, count=12, days_elapsed=14)    # -> outputs/phase2_gate_demand.md

    python -m venture_os.agents.demand_test --brief-id <id> --signups 12 --days 14   (CLI)

- The target comes from the test declared before the landing page was drafted
  (outputs/phase2_step2_demand_test_plan.json); it is never re-declared here.
- The count is recorded with source="founder" and labelled "founder-reported, not verified". The system never
  generates or estimates it. No count -> "repeat" (the test has not been measured), never a made-up number.
- Phase 2 findings go to Phase 3 through evidence.add(): the riskiest assumption (assumption), the demand result
  (founder_stated, with the numbers) and the gate outcome (inferred: derived from the founder's number by a fixed rule).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from venture_os import gates
from venture_os.decision_log import log_action
from venture_os.outputs import outputs_dir

FOUNDER_LABEL = "founder-reported, not verified"


def load_declared_test(brief_id: str) -> gates.DemandTest:
    """The demand test declared by landing_page.run() for this brief. Refuses a test that belongs to another brief."""
    path = outputs_dir() / "phase2_step2_demand_test_plan.json"
    if not path.is_file():
        raise FileNotFoundError("no demand test was declared yet: run the landing page step first")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("brief_id") != str(brief_id):
        raise ValueError("the declared demand test belongs to another brief")
    return gates.DemandTest(**{k: data[k] for k in ("metric", "target", "days", "declared_at")})


def riskiest_from_canvas(brief_id: str) -> str | None:
    """The riskiest assumption written by business_designer (outputs/phase2_step1_lean_canvas.md)."""
    path = outputs_dir() / "phase2_step1_lean_canvas.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.startswith(f"Brief id: {brief_id}"):
        return None
    line = next((ln for ln in text.split("## Riskiest assumption", 1)[-1].splitlines()
                 if ln.startswith("ASSUMPTION: ")), None)
    return line.removeprefix("ASSUMPTION: ").strip() if line else None


def enter_signups(brief_id: str, count: int | None, days_elapsed: int, *, test: gates.DemandTest | None = None,
                  riskiest_assumption: str | None = None, brief_version: int | None = None) -> gates.GateDecision:
    """Record the founder's sign-up count (or its absence), run the demand gate, write evidence for Phase 3.
    This is the function the pipeline page / CLI calls; nothing else may supply `count`."""
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
        raise ValueError("the sign-up count must be a whole number >= 0 entered by the founder")
    if isinstance(days_elapsed, bool) or not isinstance(days_elapsed, int) or days_elapsed < 0:
        raise ValueError("days_elapsed must be a whole number >= 0")
    brief_id = str(brief_id)
    test = test or load_declared_test(brief_id)
    riskiest_assumption = riskiest_assumption or riskiest_from_canvas(brief_id)

    if count is None:
        decision = gates.GateDecision(
            phase=2, gate="demand", outcome="repeat", rule=f"{gates.DEMAND_RULE_TEXT} (declared {test.declared_at})",
            reason=(f"No sign-up count has been entered, so the demand test ({test.target} {test.metric} in "
                    f"{test.days} days) has not been measured. Run the test and enter the real count; nothing "
                    "is assumed in its place."),
            decided_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    else:
        log_action("founder", "enter_signup_count", sources=[], model=None, cost=0, approved_by="founder",
                   brief_id=brief_id, metric=test.metric, target=test.target, actual=count, days_elapsed=days_elapsed,
                   source="founder", label=FOUNDER_LABEL)
        decision = gates.demand_gate(test, count, days_elapsed, source="founder")
        decision = decision.model_copy(update={"reason": f"{decision.reason} The count ({count}) is "
                                                         f"{FOUNDER_LABEL}."})
    gates.record(decision, brief_id, brief_version)
    _write_evidence(brief_id, test, count, days_elapsed, decision, riskiest_assumption)
    return decision


def evidence_items(test: gates.DemandTest, count: int | None, days_elapsed: int, decision: gates.GateDecision,
                   riskiest: str | None) -> list[dict]:
    today = datetime.now(UTC).date().isoformat()
    items = []
    if riskiest:
        items.append({"phase": 2, "kind": "riskiest_assumption", "label": "assumption", "sources": [], "date": today,
                      "text": riskiest, "quote": None})
    if count is not None:
        items.append({"phase": 2, "kind": "demand_result", "label": "founder_stated", "sources": [], "date": today,
                      "quote": None,
                      "text": (f"{count} of {test.target} {test.metric} in {days_elapsed} days "
                               f"(target declared {test.declared_at}; {FOUNDER_LABEL})")})
    items.append({"phase": 2, "kind": "demand_gate", "label": "inferred", "sources": [], "date": today, "quote": None,
                  "text": f"Phase 2 demand gate: {decision.outcome}. {decision.reason}"})
    return items


def _write_evidence(brief_id: str, test, count, days_elapsed, decision, riskiest) -> None:
    items = evidence_items(test, count, days_elapsed, decision, riskiest)
    try:
        from venture_os import evidence  # Menna's module: evidence.add(brief_id, [evidence.Item(...)])
        evidence.add(brief_id, [evidence.Item(**it) for it in items])
        written, note = True, None
    except Exception as e:  # noqa: BLE001 - reported in the log, never hidden; the gate file is already written
        written, note = False, f"{type(e).__name__}: {e}"[:200]
    log_action("demand_test", "write_phase2_evidence", sources=[], model=None, cost=0, approved_by=None,
               brief_id=brief_id, outcome=decision.outcome, written=written, error=note,
               kinds=[it["kind"] for it in items])


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Enter the founder's waitlist sign-up count and run the demand gate.")
    p.add_argument("--brief-id", required=True)
    p.add_argument("--signups", type=int, default=None, help="real count entered by the founder; omit if not run")
    p.add_argument("--days", type=int, required=True, help="days the test has been running")
    a = p.parse_args(argv)
    d = enter_signups(a.brief_id, a.signups, a.days)
    print(f"{d.outcome.upper()}: {d.reason}")


if __name__ == "__main__":
    main()
