"""Phase 3, step 2: MVP planner.

The template (booking, directory, tracker, library, calculator) follows the product spec's offer kind; each template
has fixed screens and flows, so the plan always holds together. The model (prompts/mvp_planner.md) only fills
the title, tagline, the main record's form fields and which requirements each screen covers; code checks every
value. If the model is unavailable or its answer is unusable, a fixed per-template plan is used.

The MVP is a single HTML file: data stays in the browser, no outside calls, no real payments, no sample data
(nothing fake to pass off as real users, listings or reviews).

    plan = mvp_planner.run(inputs, requirements)
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from venture_os.agents.build_inputs import BuildInputs
from venture_os.agents.requirements_mapper import Requirements
from venture_os.decision_log import log_action
from venture_os.guardrails import check_output
from venture_os.outputs import write_output
from venture_os.prompts import load_prompt

AGENT = "mvp_planner"
TemplateName = Literal["booking", "directory", "tracker", "library", "calculator"]
FIELD_TYPES = ("text", "textarea", "number", "date", "time", "select", "checkbox")
MAX_FIELDS = 8
_FORBIDDEN_FIELD = re.compile(r"password|passcode|pin\b|card|cvv|iban|كلمة السر|كلمة المرور|بطاقة|كارت|diagnos|تشخيص"
                              r"|review|rating|testimonial|تقييم|مراجعة|شهادة", re.IGNORECASE)

# Fixed screens per template: id -> (English name, Arabic name). "add" is the form for the main record.
TEMPLATES: dict[str, dict] = {
    "booking": {"screens": {"home": ("Services", "الخدمات"), "add": ("Book", "احجز"),
                            "list": ("My bookings", "حجوزاتي"), "providers": ("Providers", "مقدمو الخدمة"),
                            "feedback": ("Feedback", "رأيك")},
                "flows": [["home", "add", "list"], ["providers", "home"], ["list", "feedback"]]},
    "directory": {"screens": {"home": ("Browse", "تصفح"), "add": ("Add a listing", "أضف عرضاً"),
                              "list": ("My listings", "عروضي"), "feedback": ("Feedback", "رأيك")},
                  "flows": [["home"], ["add", "list"], ["list", "feedback"]]},
    "tracker": {"screens": {"home": ("Dashboard", "لوحة المتابعة"), "add": ("Add a record", "أضف سجلاً"),
                            "list": ("Records", "السجلات"), "feedback": ("Feedback", "رأيك")},
                "flows": [["add", "list", "home"], ["home", "feedback"]]},
    "library": {"screens": {"home": ("Library", "المكتبة"), "add": ("Add an item", "أضف عنصراً"),
                            "list": ("Saved", "المحفوظات"), "feedback": ("Feedback", "رأيك")},
                "flows": [["home", "list"], ["add", "home"], ["home", "feedback"]]},
    "calculator": {"screens": {"home": ("Calculator", "الحاسبة"), "list": ("Saved results", "النتائج المحفوظة"),
                               "feedback": ("Feedback", "رأيك")},
                   "flows": [["home", "list"], ["home", "feedback"]]},
}
# Fixed fields per template (fallback and safe defaults): (English label, Arabic label, type)
_DEFAULT_FIELDS = {
    "booking": [("Service", "الخدمة", "text"), ("Date", "التاريخ", "date"), ("Time", "الوقت", "time"),
                ("Area", "المنطقة", "text"), ("Notes", "ملاحظات", "textarea")],
    "directory": [("Name", "الاسم", "text"), ("What is offered", "ما المعروض", "textarea"),
                  ("Area", "المنطقة", "text"), ("How to contact", "طريقة التواصل", "text")],
    "tracker": [("Item", "العنصر", "text"), ("Quantity", "الكمية", "number"), ("Date", "التاريخ", "date"),
                ("Minimum level", "الحد الأدنى", "number"), ("Notes", "ملاحظات", "textarea")],
    "library": [("Title", "العنوان", "text"), ("Topic", "الموضوع", "text"), ("Level", "المستوى", "text"),
                ("Description", "الوصف", "textarea")],
    "calculator": [("Amount", "المبلغ", "number"), ("Quantity", "الكمية", "number"), ("Notes", "ملاحظات", "textarea")],
}


class Field(BaseModel):
    id: str
    label: str
    type: Literal["text", "textarea", "number", "date", "time", "select", "checkbox"] = "text"
    required: bool = False
    options: list[str] = []
    requirement: str | None = None


class MvpPlan(BaseModel):
    brief_id: str
    lang: str = "en"
    template: TemplateName
    title: str
    tagline: str = ""
    item_name: str = ""
    fields: list[Field]
    screens: dict[str, str]  # screen id -> name in the product's language
    flows: list[list[str]]
    screen_requirements: dict[str, list[str]] = {}
    out_of_scope: list[str] = []
    assumptions: list[str] = []
    fit: list[str] = []  # how the plan fits budget, time, skills, values
    source: Literal["model", "rules"] = "rules"
    model: str | None = None


# Offer kind (decided by the product spec, i.e. by the model) -> which fixed screens support the product screen.
KIND_TEMPLATE = {"tracker_dashboard": "tracker", "booking_service": "booking", "marketplace": "directory",
                 "interactive_tool": "calculator", "content_course": "library", "digital_download": "library"}


def choose_template(offer_kind: str | None = None) -> str:
    """No keyword matching: the template follows the offer kind from the product spec; unknown -> directory."""
    return KIND_TEMPLATE.get(offer_kind or "", "directory")


def _screens(template: str, lang: str) -> dict[str, str]:
    i = 1 if lang == "ar" else 0
    return {sid: names[i] for sid, names in TEMPLATES[template]["screens"].items()}


def _fit(inputs: BuildInputs) -> list[str]:
    c = inputs.constraints
    notes = ["One HTML file, no server and no hosting cost: fits any budget"
             + (f" (budget: {c['budget']})." if c.get("budget") else " (budget unknown).")]
    skills = (c.get("founder_skills") or "").lower()
    if not re.search(r"cod|program|develop|python|javascript|برمج|مبرمج", skills):
        notes.append("No programming needed to run or change the copy: the founder edits text, not code.")
    if c.get("values"):
        notes.append(f"Values respected: data stays on the user's device; nothing is sold or sent ({c['values']}).")
    if c.get("technical_preferences"):
        notes.append(f"Technical preference considered: {c['technical_preferences']} (the page works offline in a "
                     "phone or tablet browser).")
    return notes


def from_rules(inputs: BuildInputs, reqs: Requirements, template: str) -> MvpPlan:
    ar = inputs.lang == "ar"
    must = [r.id for r in reqs.items if r.priority == "must" and r.type == "feature"] or [r.id for r in reqs.items][:1]
    fields = [Field(id=f"f{n + 1}", label=ar_l if ar else en, type=typ, required=n < 2,
                    requirement=must[0] if must else None)
              for n, (en, ar_l, typ) in enumerate(_DEFAULT_FIELDS[template])]
    idea = next((i.text.split(":", 1)[-1].strip() for i in inputs.items if i.kind == "idea"), "")
    screens = _screens(template, inputs.lang)
    return MvpPlan(brief_id=inputs.brief_id, lang=inputs.lang, template=template,
                   title=(idea[:60] or ("منتج تجريبي" if ar else "MVP")), tagline=idea[:140],
                   item_name="سجل" if ar else "record", fields=fields, screens=screens,
                   flows=TEMPLATES[template]["flows"],
                   screen_requirements={"add" if "add" in screens else "home": must},
                   out_of_scope=["Real payments (MOCKED only)", "User accounts and logins", "Sending emails or messages"],
                   assumptions=["Early users will try a simple one-page version before a full app."],
                   fit=_fit(inputs), source="rules")


def _clean_fields(raw_fields, req_ids: set[str]) -> list[Field]:
    out = []
    for f in raw_fields if isinstance(raw_fields, list) else []:
        if not isinstance(f, dict):
            continue
        label = " ".join(str(f.get("label") or "").split())[:60]
        ftype = f.get("type") if f.get("type") in FIELD_TYPES else "text"
        if not label or _FORBIDDEN_FIELD.search(label) or check_output(label):
            continue
        options = [str(o)[:40] for o in f.get("options") or [] if str(o).strip()][:6]
        if ftype == "select" and len(options) < 2:
            ftype, options = "text", []
        req = str(f.get("requirement")) if str(f.get("requirement")) in req_ids else None
        out.append(Field(id=f"f{len(out) + 1}", label=label, type=ftype, required=bool(f.get("required")),
                         options=options if ftype == "select" else [], requirement=req))
        if len(out) == MAX_FIELDS:
            break
    return out


def _texts(items, limit=6, length=160) -> list[str]:
    return [t for t in (" ".join(str(x).split())[:length] for x in (items if isinstance(items, list) else []))
            if t and not check_output(t)][:limit]


def from_model(inputs: BuildInputs, reqs: Requirements, template: str,
               chat_json: Callable[[list[dict]], str], feedback: list[str] | None = None) -> MvpPlan | None:
    screens = _screens(template, inputs.lang)
    req_lines = [f"{r.id} | {r.priority} | {r.type} | {r.statement}" for r in reqs.items]
    if feedback:  # problems the validator found in the previous plan
        req_lines += ["", "Fix these problems from the previous plan:"] + [f"- {f}" for f in feedback]
    raw = json.loads(chat_json([
        {"role": "system", "content": load_prompt(
            "mvp_planner", template=template, screens=", ".join(f"{k} ({v})" for k, v in screens.items()),
            lang="Arabic" if inputs.lang == "ar" else "English")},
        {"role": "user", "content": "<untrusted>\n" + "\n".join(req_lines) + "\n</untrusted>"},
    ]))
    if not isinstance(raw, dict):
        return None
    req_ids = {r.id for r in reqs.items}
    fields = _clean_fields(raw.get("fields"), req_ids)
    if len(fields) < 2:
        return None
    sr = {sid: [r for r in v if r in req_ids] for sid, v in (raw.get("screen_requirements") or {}).items()
          if sid in screens and isinstance(v, list)}
    title = " ".join(str(raw.get("title") or "").split())[:60]
    tagline = " ".join(str(raw.get("tagline") or "").split())[:160]
    if not title or check_output(title + " " + tagline):
        return None
    return MvpPlan(brief_id=inputs.brief_id, lang=inputs.lang, template=template, title=title, tagline=tagline,
                   item_name=" ".join(str(raw.get("item_name") or "").split())[:30], fields=fields, screens=screens,
                   flows=TEMPLATES[template]["flows"], screen_requirements=sr,
                   out_of_scope=_texts(raw.get("out_of_scope")) or ["Real payments (MOCKED only)"],
                   assumptions=_texts(raw.get("assumptions")), fit=_fit(inputs), source="model")


def to_markdown(plan: MvpPlan, reqs: Requirements) -> str:
    rq = {r.id: r for r in reqs.items}
    lines = ["# Phase 3, step 3: MVP plan", "", f"Brief id: `{plan.brief_id}`", "",
             f"**{plan.title}**: {plan.tagline}", "",
             (f"Template: **{plan.template}** (follows the product spec's offer kind). Drafted by: "
             f"{'model ' + (plan.model or '') if plan.source == 'model' else 'fixed rules (no model)'}."), "",
             "## Screens", ""]
    for sid, name in plan.screens.items():
        cov = ", ".join(plan.screen_requirements.get(sid, [])) or "-"
        lines.append(f"- **{name}** (`{sid}`): covers {cov}")
    lines += ["", "## Flows", ""] + [" -> ".join(plan.screens[s] for s in flow) for flow in plan.flows]
    lines += ["", f"## Main record: {plan.item_name or '-'}", "", "| Field | Type | Required | Requirement |",
              "|---|---|---|---|"]
    for f in plan.fields:
        t = f.type + (f" ({', '.join(f.options)})" if f.options else "")
        r = f"{f.requirement} ({rq[f.requirement].priority})" if f.requirement in rq else "-"
        lines.append(f"| {f.label} | {t} | {'yes' if f.required else 'no'} | {r} |")
    lines += ["", "## Fits the founder's constraints", ""] + [f"- {n}" for n in plan.fit]
    lines += ["", "## Out of scope", ""] + [f"- {x}" for x in plan.out_of_scope]
    if plan.assumptions:
        lines += ["", "## Assumptions (not checked)", ""] + [f"- ASSUMPTION: {a}" for a in plan.assumptions]
    return "\n".join(lines) + "\n"


def run(inputs: BuildInputs, reqs: Requirements, chat_json: Callable[[list[dict]], str] | None = None,
        model: str | None = None, feedback: list[str] | None = None, offer_kind: str | None = None) -> MvpPlan:
    """`feedback`: problems found by the validator in the previous round (logged; the plan is redone)."""
    if chat_json is None:
        from venture_os.config import Settings
        from venture_os.llm.client import chat_json as live_chat
        from venture_os.llm.client import live_enabled
        if live_enabled():
            chat_json, model = live_chat, model or Settings().llm_model_extract
    template = choose_template(offer_kind)
    plan = None
    if chat_json is not None:
        try:
            plan = from_model(inputs, reqs, template, chat_json, feedback)
        except Exception:  # noqa: BLE001 - model down or bad JSON: rules take over
            plan = None
    if plan is None:
        plan = from_rules(inputs, reqs, template)
    else:
        plan.model = model
    write_output(3, 3, "mvp_plan", to_markdown(plan, reqs))
    log_action(AGENT, "plan_mvp", sources=[], model=plan.model, cost=0, approved_by=None, outcome=plan.source,
               brief_id=inputs.brief_id, template=plan.template, fields=len(plan.fields),
               revision=bool(feedback), feedback=feedback or [])
    return plan
