"""Phase 3, step 0: entry check (plain code, no model).

Collects everything the Build stage needs **at the start**, so nothing has to be asked halfway through:
the confirmed brief (as founder-stated / inferred items), Phase 1-2 evidence items, the founder's constraints
(budget, time, skills, values, technical preferences) and what is missing. It does not start the stage if the
product is excluded or the Phase 2 demand gate recommended stop.

    inputs = build_inputs.run(brief)      # writes outputs/phase3_step1_build_inputs.md + a log entry
    if not inputs.can_start: ...          # inputs.stop_reason says why
"""

from __future__ import annotations

from pydantic import BaseModel

from venture_os import evidence
from venture_os.decision_log import log_action, read_log
from venture_os.evidence import LABEL_TEXT, Item
from venture_os.onboarding.money import format_budget
from venture_os.outputs import write_output

AGENT = "build_inputs"
# Brief field -> evidence kind. What the founder said becomes a founder-stated item (or inferred, if deduced).
_FIELD_KIND = {"idea": "idea", "problem": "pain", "target_customer": "customer", "supply_side": "supply",
               "business_model": "revenue", "known_competitors": "competitor", "city": "market",
               "country": "market", "values": "constraint", "technical_preferences": "constraint",
               "budget": "constraint", "time_available": "constraint", "founder_skills": "constraint"}
_CONSTRAINTS = ("budget", "time_available", "founder_skills", "values", "technical_preferences")


class BuildInputs(BaseModel):
    brief_id: str
    brief_version: int
    lang: str = "en"
    items: list[Item]  # every input the agents may use, each with its label
    constraints: dict[str, str | None]  # budget, time, skills, values, technical preferences (None = unknown)
    budget: dict | None = None  # parsed budget {min, max, currency, ...}
    open_questions: list[str] = []  # research questions nobody has answered yet
    phase2_outcome: str | None = None  # the demand gate's recommendation, if Phase 2 ran
    missing: list[str] = []  # told to the founder at the start; the stage labels these parts as assumptions
    can_start: bool = True
    stop_reason: str | None = None

    def by_label(self, label: str) -> list[Item]:
        return [i for i in self.items if i.label == label]


def _brief_items(brief) -> list[Item]:
    items = []
    for name, kind in _FIELD_KIND.items():
        f = brief.fields.get(name) or {}
        value = brief.known(name)
        if value:
            label = "inferred" if f.get("status") == "inferred" or "inferred" in (f.get("source") or "") \
                else "founder_stated"
            items.append(Item(phase=0, kind=kind, text=f"{name.replace('_', ' ')}: {value}", label=label,
                              quote=f.get("quote")))
    for fu in brief.followups or []:
        if fu.get("answer"):
            items.append(Item(phase=0, kind="claim", text=f"{fu['question']} -> {fu['answer']}",
                              label="founder_stated", quote=fu["answer"]))
    return items


def _phase2_outcome(brief_id: str) -> str | None:
    gates = [e for e in read_log() if e.get("brief_id") == brief_id and e.get("action") == "demand_gate"]
    return gates[-1].get("outcome") if gates else None


def collect(brief, extra_items: list[Item] | None = None) -> BuildInputs:
    """Gather the inputs; no files written. `extra_items`: findings handed over directly (e.g. the approved
    Discover run's claims), numbered D1, D2, ..."""
    found = evidence.load(brief.brief_id)
    found += [it.model_copy(update={"id": f"D{i + 1}"}) for i, it in enumerate(extra_items or [])]
    brief_items = _brief_items(brief)
    items = [it.model_copy(update={"id": f"B{i + 1}"}) for i, it in enumerate(brief_items)] + found
    constraints = {c: brief.known(c) for c in _CONSTRAINTS}
    outcome = _phase2_outcome(brief.brief_id)
    lang = (brief.tag("languages") or ["en"])[0] if isinstance(brief.tag("languages"), list) else "en"

    missing = []
    if not any(i.phase == 1 for i in found):
        missing.append("No Phase 1 (Discover) findings: requirements will rest on the founder's statements and "
                       "assumptions, labelled as such.")
    if not any(i.phase == 2 for i in found) and outcome is None:
        missing.append("No Phase 2 (Validate) result: demand is not yet tested, so the MVP tests the main promise "
                       "only.")
    missing += [f"{c.replace('_', ' ')} is unknown: the plan assumes the smallest option."
                for c, v in constraints.items() if v is None and c in ("budget", "time_available", "founder_skills")]

    stop = None
    if not brief.allowed:
        stop = "The product is excluded (only digital products are supported)."
    elif outcome == "stop":
        stop = "The Phase 2 demand gate recommended stop: there is no validated demand to build for."
    return BuildInputs(brief_id=brief.brief_id, brief_version=brief.version, lang=lang, items=items,
                       constraints=constraints, budget=brief.budget, open_questions=list(brief.open_questions),
                       phase2_outcome=outcome, missing=missing, can_start=stop is None, stop_reason=stop)


def to_markdown(inp: BuildInputs) -> str:
    lines = ["# Phase 3, step 1: build inputs", "", f"Brief id: `{inp.brief_id}` (version {inp.brief_version})", ""]
    if not inp.can_start:
        lines += [f"**Stage not started:** {inp.stop_reason}", ""]
    counts = {lab: len(inp.by_label(lab)) for lab in LABEL_TEXT}
    lines += ["**Inputs by label:** " + ", ".join(f"{LABEL_TEXT[k]} {v}" for k, v in counts.items()), "",
              "## Inputs", "", "| Id | Phase | Kind | Label | Input | Source |", "|---|---|---|---|---|---|"]
    for i in inp.items:
        src = ", ".join(i.sources) or (f'"{i.quote}"' if i.quote else "")
        lines.append(f"| {i.id} | {i.phase} | {i.kind} | {LABEL_TEXT[i.label]} | {i.text.replace('|', '/')} | "
                     f"{src.replace('|', '/')} |")
    lines += ["", "## Founder constraints", ""]
    for c, v in inp.constraints.items():
        shown = v or "unknown"
        if c == "budget" and inp.budget:
            shown += f" (= {format_budget(inp.budget)})"
        lines.append(f"- {c.replace('_', ' ')}: {shown}")
    lines += ["", f"**Phase 2 demand gate:** {inp.phase2_outcome or 'not run yet'}", ""]
    if inp.missing:
        lines += ["## Missing at the start", ""] + [f"- {m}" for m in inp.missing] + [""]
    if inp.open_questions:
        lines += ["## Research questions still open", ""] + [f"- {q}" for q in inp.open_questions] + [""]
    return "\n".join(lines)


def run(brief, extra_items: list[Item] | None = None) -> BuildInputs:
    inp = collect(brief, extra_items)
    write_output(3, 1, "build_inputs", to_markdown(inp))
    sources = sorted({u for i in inp.items for u in i.sources})
    log_action(AGENT, "collect_build_inputs", sources=sources, model=None, cost=0, approved_by=None,
               outcome="stop" if not inp.can_start else ("missing_inputs" if inp.missing else "ready"),
               brief_id=inp.brief_id, brief_version=inp.brief_version, items=len(inp.items),
               missing=len(inp.missing))
    return inp
