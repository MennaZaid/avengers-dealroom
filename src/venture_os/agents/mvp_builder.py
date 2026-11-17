"""Phase 3, step 4: MVP builder -> one HTML file (outputs/phase3_step5_mvp.html).

Code renders the validated plan into templates/mvp/base.html: one page, data kept in the browser
(localStorage), no network calls, no real payments, no sample data. The plan goes in as JSON and the page puts
every value on screen as text (never as HTML), so nothing in the plan or typed by a user can run as code.
The model writes copy only: one help line per screen (prompts/mvp_builder.md), checked by check_output();
fixed Arabic/English text is used when there is no model.

    html = mvp_builder.run(inputs, reqs, plan)
"""

from __future__ import annotations

import html
import json
import os
import re
from collections.abc import Callable
from pathlib import Path

from venture_os.agents.build_inputs import BuildInputs
from venture_os.agents.mvp_planner import MvpPlan
from venture_os.agents.product_spec import ProductSpec
from venture_os.agents.requirements_mapper import Requirements
from venture_os.decision_log import log_action
from venture_os.guardrails import check_output
from venture_os.outputs import write_output
from venture_os.prompts import load_prompt

AGENT = "mvp_builder"
_DEFAULT_DIR = Path(__file__).resolve().parents[3] / "templates" / "mvp"
_PAYMENT = re.compile(r"\b(pay|payment|price|checkout|fee)\b|دفع|سعر|رسوم", re.IGNORECASE)

TEXTS = {
    "en": {
        "banner": "MVP prototype · data stays on this device · no real payments (MOCKED) · nothing is sent anywhere",
        "footer": "Built by Venture OS from the founder's confirmed brief",
        "save": "Save", "remove": "Remove", "empty": "Nothing here yet.", "search": "Search",
        "result": "Result", "records": "records", "below_min": "below the minimum level",
        "formula": "ASSUMPTION: the result multiplies the number fields; the founder confirms the real formula.",
        "provider_pick": "Provider", "provider_name": "Name", "provider_offer": "What you offer",
        "provider_area": "Area", "provider_join": "Join as a provider",
        "provider_help": "Providers add themselves here. No profiles are pre-filled.",
        "no_providers": "No providers yet. They appear here when they join.",
        "feedback_label": "What should we improve?", "send": "Save feedback",
        "feedback_note": "Feedback is saved on this device only.",
        "product": "Product", "offers": "What you get", "price": "Price", "for": "For", "inside": "Inside",
        "try": "Try it now", "preview": "Live preview", "print": "Print", "download": "Download (sample)",
        "buy": "Buy (MOCKED)", "bought": "Order placed (MOCKED): no money moved, nothing was charged.",
        "deliver": "Get your file (MOCKED delivery)", "delivery": "Delivery",
        "waitlist": "Join the waitlist (MOCKED: nothing is sent)", "email": "Email",
        "joined": "Saved on this device only (MOCKED: no email is sent).", "faq": "Questions",
        "assumption": "ASSUMPTION",
    },
    "ar": {
        "banner": "نموذج أولي (MVP) · البيانات تبقى على هذا الجهاز · لا مدفوعات حقيقية (MOCKED) · لا يُرسل أي شيء",
        "footer": "بناه Venture OS من موجز المؤسس المؤكد",
        "save": "حفظ", "remove": "حذف", "empty": "لا يوجد شيء بعد.", "search": "بحث",
        "result": "النتيجة", "records": "سجلات", "below_min": "أقل من الحد الأدنى",
        "formula": "افتراض: النتيجة هي حاصل ضرب الحقول الرقمية؛ يؤكد المؤسس المعادلة الحقيقية.",
        "provider_pick": "مقدم الخدمة", "provider_name": "الاسم", "provider_offer": "ما تقدمه",
        "provider_area": "المنطقة", "provider_join": "انضم كمقدم خدمة",
        "provider_help": "يضيف مقدمو الخدمة أنفسهم هنا. لا توجد ملفات معبأة مسبقاً.",
        "no_providers": "لا يوجد مقدمو خدمة بعد. سيظهرون هنا عند انضمامهم.",
        "feedback_label": "ما الذي يجب أن نحسّنه؟", "send": "حفظ الرأي",
        "feedback_note": "يُحفظ رأيك على هذا الجهاز فقط.",
        "product": "المنتج", "offers": "ما تحصل عليه", "price": "السعر", "for": "لمن", "inside": "المحتوى",
        "try": "جرّبه الآن", "preview": "معاينة مباشرة", "print": "طباعة", "download": "تحميل (نموذج)",
        "buy": "شراء (MOCKED)", "bought": "تم الطلب (MOCKED): لم تُنقل أي أموال ولم يُخصم شيء.",
        "deliver": "استلم ملفك (تسليم MOCKED)", "delivery": "التسليم",
        "waitlist": "انضم لقائمة الانتظار (MOCKED: لا يُرسل شيء)", "email": "البريد الإلكتروني",
        "joined": "محفوظ على هذا الجهاز فقط (MOCKED: لا يُرسل بريد).", "faq": "أسئلة",
        "assumption": "افتراض (ASSUMPTION)",
    },
}


def templates_dir() -> Path:
    return Path(os.environ.get("TEMPLATES_DIR", _DEFAULT_DIR))


def _help_lines(plan: MvpPlan, reqs: Requirements, chat_json) -> dict[str, str]:
    rq = {r.id: r.statement for r in reqs.items}
    screens = {sid: {"name": name, "covers": [rq[r] for r in plan.screen_requirements.get(sid, []) if r in rq]}
               for sid, name in plan.screens.items()}
    raw = json.loads(chat_json([
        {"role": "system", "content": load_prompt("mvp_builder", lang="Arabic" if plan.lang == "ar" else "English")},
        {"role": "user", "content": "<untrusted>\n" + json.dumps({"product": plan.title, "screens": screens},
                                                                 ensure_ascii=False)[:8000] + "\n</untrusted>"},
    ]))
    out = {}
    for sid, line in (raw.get("help") or {}).items() if isinstance(raw, dict) else []:
        line = " ".join(str(line).split())[:160]
        if sid in plan.screens and line and not check_output(line):
            out[sid] = line
    return out


def spec_config(spec: ProductSpec | None) -> dict | None:
    """The product spec as page data: text slots only (the page shows them as text, never as HTML)."""
    if spec is None:
        return None
    return {"kind": spec.offer_kind,
            "offers": [{"name": o.name.value, "contents": o.contents.value, "for": o.for_whom.value,
                        "price": o.price.value, "price_assumed": o.price.source == "ASSUMPTION"} for o in spec.offers],
            "core": {"verb": spec.core_verb, "object": spec.core_object.value, "result": spec.core_result,
                     "fields": [f.model_dump() for f in spec.fields]},
            "sample_title": spec.sample_title.value, "sample_lines": spec.sample_lines, "delivery": spec.delivery,
            "faq": [list(x) for x in spec.faq], "blocks": spec.blocks,
            "source": spec.source, "facts": spec.facts}


def config(plan: MvpPlan, help_lines: dict[str, str], brief_version: int, spec: ProductSpec | None = None) -> dict:
    texts = dict(TEXTS["ar" if plan.lang == "ar" else "en"])
    texts["help"] = help_lines
    fields = [f.model_dump() | {"mocked": bool(_PAYMENT.search(f.label))} for f in plan.fields]
    screens = ({"product": texts["product"]} | plan.screens) if spec is not None else plan.screens
    title = spec.sample_title.value[:60] if spec is not None else plan.title
    tagline = (f"{spec.core_verb} {spec.core_object.value} {spec.core_result}"[:200] if spec is not None
               else plan.tagline)
    return {"brief_id": plan.brief_id, "brief_version": brief_version, "lang": plan.lang, "template": plan.template,
            "title": title, "tagline": tagline, "screens": screens, "fields": fields,
            "screen_requirements": plan.screen_requirements, "texts": texts, "spec": spec_config(spec)}


def render(cfg: dict) -> str:
    page = (templates_dir() / "base.html").read_text(encoding="utf-8")
    # JSON inside <script>: escape "<" so no value can close the script tag
    data = json.dumps(cfg, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (page.replace("__CONFIG_JSON__", data)
            .replace("__LANG__", "ar" if cfg["lang"] == "ar" else "en")
            .replace("__DIR__", "rtl" if cfg["lang"] == "ar" else "ltr")
            .replace("__TITLE__", html.escape(cfg["title"])))


def run(inputs: BuildInputs, reqs: Requirements, plan: MvpPlan,
        chat_json: Callable[[list[dict]], str] | None = None, model: str | None = None,
        spec: ProductSpec | None = None) -> str:
    if chat_json is None:
        from venture_os.config import Settings
        from venture_os.llm.client import chat_json as live_chat
        from venture_os.llm.client import live_enabled
        if live_enabled():
            chat_json, model = live_chat, model or Settings().llm_model_extract
    help_lines, used = {}, None
    if chat_json is not None:
        try:
            help_lines, used = _help_lines(plan, reqs, chat_json), model
        except Exception:  # noqa: BLE001 - copy is optional
            help_lines, used = {}, None
    page = render(config(plan, help_lines, inputs.brief_version, spec))
    write_output(3, 5, "mvp", page, ext="html")
    log_action(AGENT, "build_mvp", sources=[], model=used, cost=0, approved_by=None, outcome="built",
               brief_id=inputs.brief_id, template=plan.template,
               offer_kind=spec.offer_kind if spec else None, bytes=len(page.encode("utf-8")))
    return page
