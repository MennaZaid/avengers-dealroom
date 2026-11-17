"""Phase 6 Operate and learn: persevere-or-pivot memo (STUBBED), built ONLY from logged results.

Reads decision_log.json (gate outcomes, the founder's sign-up count) and outputs/payment_test_log.md. A metric
without real data says "no data yet". Support and analytics are STUBBED (no integrations).
-> outputs/phase6_step1_pivot_memo.md, then the phase 6 gate (recommends only).
"""

from __future__ import annotations

from venture_os.agents import stubbed
from venture_os.decision_log import read_log
from venture_os.outputs import outputs_dir

NO_DATA = "no data yet"


def run(brief_id: str):
    log = [e for e in read_log() if e.get("brief_id") == str(brief_id)]
    gates_seen: dict[str, str] = {}
    for e in log:
        if e.get("agent") == "gate" and e.get("outcome") and e["action"].endswith("_gate"):
            gates_seen[f"phase {e.get('phase', '?')} {e['action'].removesuffix('_gate')}"] = e["outcome"]
    signups = next((e for e in reversed(log) if e["action"] == "enter_signup_count"), None)
    pay_log = outputs_dir() / "payment_test_log.md"
    pay = pay_log.is_file() and pay_log.read_text(encoding="utf-8").startswith(f"Brief id: {brief_id}")

    metrics = [
        ("Waitlist sign-ups (founder-reported, not verified)",
         f"{signups['actual']} of target {signups['target']}" if signups else NO_DATA),
        ("Payment and delivery test (MOCKED)", "see outputs/payment_test_log.md" if pay else NO_DATA),
        ("Support requests (STUBBED: no support integration)", NO_DATA),
        ("Product usage analytics (STUBBED: no analytics integration)", NO_DATA),
    ]
    outcomes = set(gates_seen.values())
    if "stop" in outcomes:
        rec, outcome = "Do not persevere: a gate recommended stop. Pivot back or stop.", "stop"
    elif "pivot" in outcomes:
        rec, outcome = "Pivot: a gate recommended changing the customer, problem or offer.", "pivot"
    elif not signups or not gates_seen:
        rec, outcome = "Not enough logged results to decide: run the demand test and record its gate.", "repeat"
    elif outcomes == {"go"}:
        rec, outcome = "Persevere: every recorded gate recommended go. Keep measuring.", "go"
    else:
        rec, outcome = "Repeat the weak step before deciding.", "repeat"

    md = stubbed.header(brief_id, "Phase 6, step 1: persevere-or-pivot memo")
    md += ["Built only from decision_log.json and outputs/ of this brief; nothing is estimated.", "",
           "| Metric | Value |", "|---|---|"] + [f"| {m} | {stubbed.cell(v)} |" for m, v in metrics]
    md += ["", "| Gate | Recommendation |", "|---|---|"]
    md += [f"| {g} | {o} |" for g, o in gates_seen.items()] or ["| (none recorded) | no data yet |"]
    md += ["", f"**Recommendation:** {rec}", "", "The founder decides; this memo only recommends.", ""]
    stubbed.write_checked(6, 1, "pivot_memo", "\n".join(md) + "\n")
    stubbed.log_step("operator", "persevere_or_pivot_memo", brief_id, recommendation=outcome)
    return stubbed.record_gate(6, "operate", outcome, rec,
                               "any stop -> stop; any pivot -> pivot; missing results -> repeat; all go -> go",
                               brief_id)
