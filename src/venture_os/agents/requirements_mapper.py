"""Phase 3, step 1: evidence -> MVP requirements.

The model drafts requirements and cites input ids (prompts/mvp_requirements.md). Code then decides what they
rest on:
- unknown ids are removed; a requirement with no valid id is an ASSUMPTION;
- the label comes from the strongest cited input (evidenced > founder-stated > inferred > assumption);
- priority is capped by that label: "must" needs evidenced or founder-stated input, inferred-only is at most
  "should", assumption-only is at most "could";
- generated text goes through guardrails.check_output().
If no model is available or its answer is unusable, fixed rules derive requirements from the inputs.

    reqs = requirements_mapper.run(inputs)            # inputs from build_inputs.run(brief)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from venture_os.agents.build_inputs import BuildInputs
from venture_os.decision_log import log_action
from venture_os.evidence import LABEL_TEXT
from venture_os.guardrails import check_output
from venture_os.outputs import write_output
from venture_os.prompts import load_prompt

AGENT = "requirements_mapper"
STRENGTH = {"evidenced": 3, "founder_stated": 2, "inferred": 1, "assumption": 0}
MAX_PRIORITY = {3: "must", 2: "must", 1: "should", 0: "could"}
ORDER = {"must": 0, "should": 1, "could": 2}
MAX_REQUIREMENTS = 7


class Requirement(BaseModel):
    id: str
    statement: str
    type: Literal["feature", "constraint", "quality"] = "feature"
    priority: Literal["must", "should", "could"] = "should"
    evidence: list[str] = []  # input ids (B.. from the brief, E.. from Phase 1-2)
    label: Literal["evidenced", "founder_stated", "inferred", "assumption"] = "assumption"
    capped: bool = False  # priority was lowered because the evidence was weaker than the model claimed


class Requirements(BaseModel):
    brief_id: str
    items: list[Requirement]
    source: Literal["model", "rules"]
    model: str | None = None


def _label_and_cap(statement: str, rtype: str, priority: str, refs: list[str], labels: dict[str, str]
                   ) -> Requirement | None:
    refs = [r for r in dict.fromkeys(refs) if r in labels]
    strength = max((STRENGTH[labels[r]] for r in refs), default=0)
    label = next(k for k, v in STRENGTH.items() if v == strength)
    cap = MAX_PRIORITY[strength]
    priority = priority if priority in ORDER else "should"
    capped = ORDER[priority] < ORDER[cap]
    if rtype not in ("feature", "constraint", "quality"):
        rtype = "feature"
    statement = " ".join(str(statement).split())[:300]
    if not statement or check_output(statement):
        return None
    return Requirement(id="", statement=statement, type=rtype, priority=cap if capped else priority,
                       evidence=refs, label=label, capped=capped)


def _number(reqs: list[Requirement]) -> list[Requirement]:
    reqs = sorted(reqs, key=lambda r: (ORDER[r.priority], -STRENGTH[r.label]))[:MAX_REQUIREMENTS]
    return [r.model_copy(update={"id": f"R{i + 1}"}) for i, r in enumerate(reqs)]


def from_model(inputs: BuildInputs, chat_json: Callable[[list[dict]], str]) -> list[Requirement]:
    lines = [f"{i.id} | {LABEL_TEXT[i.label]} | {i.kind} | {i.text}" for i in inputs.items]
    lines += [f"constraint | {k.replace('_', ' ')}: {v}" for k, v in inputs.constraints.items() if v]
    lang = "Arabic" if inputs.lang == "ar" else "English"
    raw = json.loads(chat_json([
        {"role": "system", "content": load_prompt("mvp_requirements", lang=lang)},
        {"role": "user", "content": "<untrusted>\n" + "\n".join(lines)[:15000] + "\n</untrusted>"},
    ]))
    labels = {i.id: i.label for i in inputs.items}
    out = []
    for r in (raw or {}).get("requirements", []) if isinstance(raw, dict) else []:
        if isinstance(r, dict):
            req = _label_and_cap(r.get("statement", ""), r.get("type", "feature"), r.get("priority", "should"),
                                 [str(x) for x in r.get("evidence") or []], labels)
            if req:
                out.append(req)
    return out


def from_rules(inputs: BuildInputs) -> list[Requirement]:
    """Deterministic fallback: one requirement per kind of input, each citing that input."""
    ar = inputs.lang == "ar"
    labels = {i.id: i.label for i in inputs.items}
    first = {k: next((i for i in inputs.items if i.kind == k), None) for k in ("idea", "customer", "pain", "supply")}
    out = []

    def add(text_en, text_ar, rtype, priority, refs):
        req = _label_and_cap(text_ar if ar else text_en, rtype, priority, [r.id for r in refs if r], labels)
        if req:
            out.append(req)

    idea, customer, pain, supply = first["idea"], first["customer"], first["pain"], first["supply"]
    if idea:
        what = idea.text.split(":", 1)[-1].strip()
        add(f"The core flow of the idea works end to end: {what}", f"المسار الأساسي للفكرة يعمل من البداية للنهاية: {what}",
            "feature", "must", [idea, customer])
    if pain:
        add(f"The product directly addresses the problem: {pain.text.split(':', 1)[-1].strip()}",
            f"المنتج يعالج المشكلة مباشرة: {pain.text.split(':', 1)[-1].strip()}", "feature", "must", [pain])
    if supply:
        add("Providers can create a profile and list what they offer",
            "يستطيع مقدمو الخدمة إنشاء ملف تعريفي وعرض ما يقدمونه", "feature", "must", [supply])
    add("A simple way for early users to give feedback inside the product",
        "طريقة بسيطة ليعطي المستخدمون الأوائل رأيهم داخل المنتج", "feature", "should", [])
    def about(field):
        return [i for i in inputs.items if i.kind == "constraint" and i.text.startswith(field.replace("_", " "))]

    if inputs.constraints.get("values"):
        add(f"The product respects the founder's values: {inputs.constraints['values']}",
            f"المنتج يحترم قيم المؤسس: {inputs.constraints['values']}", "constraint", "must", about("values"))
    if inputs.constraints.get("technical_preferences"):
        add(f"Technical preference: {inputs.constraints['technical_preferences']}",
            f"تفضيل تقني: {inputs.constraints['technical_preferences']}", "constraint", "should",
            about("technical_preferences"))
    add("No real payments: any payment step is clearly labelled MOCKED",
        "لا مدفوعات حقيقية: أي خطوة دفع موسومة بوضوح MOCKED", "constraint", "must", [idea])
    return out


def to_markdown(reqs: Requirements) -> str:
    lines = ["# Phase 3, step 2: MVP requirements", "", f"Brief id: `{reqs.brief_id}`", "",
             (f"Drafted by: {'model ' + (reqs.model or '') if reqs.source == 'model' else 'fixed rules (no model)'}. "
             "Labels and priority caps are set by code from the cited inputs (see step 1)."), "",
             "| Id | Requirement | Type | Priority | Rests on | Inputs |", "|---|---|---|---|---|---|"]
    for r in reqs.items:
        pr = r.priority + (" (lowered: weak evidence)" if r.capped else "")
        lines.append(f"| {r.id} | {r.statement.replace('|', '/')} | {r.type} | {pr} | {LABEL_TEXT[r.label]} | "
                     f"{', '.join(r.evidence) or '-'} |")
    return "\n".join(lines) + "\n"


def run(inputs: BuildInputs, chat_json: Callable[[list[dict]], str] | None = None,
        model: str | None = None) -> Requirements:
    """chat_json=None: use the configured model if live, else rules."""
    if chat_json is None:
        from venture_os.config import Settings
        from venture_os.llm.client import chat_json as live_chat
        from venture_os.llm.client import live_enabled
        if live_enabled():
            chat_json, model = live_chat, model or Settings().llm_model_extract
    items, source = [], "rules"
    if chat_json is not None:
        try:
            items, source = from_model(inputs, chat_json), "model"
        except Exception:  # noqa: BLE001 - model down or bad JSON: rules take over
            items = []
    if len(items) < 2:
        items, source = from_rules(inputs), "rules"
    reqs = Requirements(brief_id=inputs.brief_id, items=_number(items), source=source,
                        model=model if source == "model" else None)
    write_output(3, 2, "requirements", to_markdown(reqs))
    log_action(AGENT, "map_evidence_to_requirements", sources=[], model=reqs.model, cost=0, approved_by=None,
               outcome=source, brief_id=inputs.brief_id, requirements=len(reqs.items),
               evidenced=sum(r.label == "evidenced" for r in reqs.items),
               assumptions=sum(r.label == "assumption" for r in reqs.items))
    return reqs
