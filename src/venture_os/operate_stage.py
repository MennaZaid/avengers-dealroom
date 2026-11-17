"""Phase 6 Operate and learn: the persevere-or-pivot memo, built ONLY from logged results.

    from venture_os.operate_stage import run_operate_stage
    result = run_operate_stage(brief_id, brief_version)    # -> StageResult(decision, files, stubbed)

No approval inside the stage; the founder decides on its gate through POST /stages/runs/{id}/decision.
Support and analytics have no integrations: they are STUBBED and the memo says "no data yet".
"""

from __future__ import annotations

from venture_os.agents import operator
from venture_os.launch_stage import StageResult


def run_operate_stage(brief_id: str, brief_version: int | None = None) -> StageResult:
    d = operator.run(str(brief_id))  # memo + phase 6 gate (operate), from decision_log.json and outputs/ only
    return StageResult(decision=d, files=["phase6_step1_pivot_memo.md", "phase6_gate_operate.md"],
                       stubbed=["support (no support integration)", "analytics (no analytics integration)"])
