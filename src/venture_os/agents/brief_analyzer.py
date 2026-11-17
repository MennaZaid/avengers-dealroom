"""Brief analyzer, Discover side (step 1): the confirmed brief as Discover reads it, plus the product type.

Onboarding (onboarding/chat.py, analyst.py) collects and confirms the brief. Here Discover:
- maps it to the six fields the official brief requires: idea, skills, budget, time_available,
  target_market (who + where), values. Unknown stays unknown and is listed; nothing is filled in.
- classifies the product type with plain-code keyword rules (English + Arabic) first, then, only if the rules
  can't decide and a model is on, the model (accepted only from the fixed list and with a quote from the brief).
  Excluded categories come from guardrails.check_product (shared with onboarding).
"""

from __future__ import annotations

import json
from collections.abc import Callable

from pydantic import BaseModel

from venture_os.guardrails import check_product
from venture_os.onboarding.tags import _has
from venture_os.prompts import load_prompt

DIGITAL_TYPES: dict[str, tuple[str, ...]] = {  # most specific first
    "template_or_asset": ("template", "notion", "cv template", "resume template", "theme", "icon pack", "preset",
                          "printable", "spreadsheet template", "قالب", "قوالب", "تمبلت", "تمبليت", "نموذج سيرة"),
    "online_course": ("course", "online course", "tutorial", "workshop", "bootcamp", "lessons", "كورس", "كورسات",
                      "دورة", "دورات", "شرح أونلاين", "دروس أونلاين"),
    "ebook_or_guide": ("ebook", "e-book", "guide", "handbook", "playbook", "كتاب إلكتروني", "دليل"),
    "browser_extension": ("browser extension", "chrome extension", "extension", "add-on", "إضافة للمتصفح", "إضافة كروم"),
    "api_or_dev_tool": ("api", "sdk", "developer tool", "cli", "library for developers", "للمطورين", "أداة مطورين"),
    "community_or_membership": ("community", "membership", "newsletter", "discord", "مجتمع", "عضوية", "نشرة"),
    "mobile_app": ("mobile app", "android", "ios", "iphone", "app", "تطبيق", "أبلكيشن", "ابلكيشن", "موبايل"),
    "web_app": ("web app", "website", "web platform", "online platform", "موقع", "منصة إلكترونية"),
    "saas": ("saas", "software", "platform", "dashboard", "tool", "system", "crm", "erp", "برنامج", "منصة", "نظام",
             "أداة"),
}
# Borderline words guardrails.BORDERLINE doesn't list yet (Arabic plurals): digital, but ask before continuing.
EXTRA_BORDERLINE = {"health": ("العيادات", "عيادات", "المرضى", "مرضى", "الصيدليات", "hospital", "مستشفى")}
EXCLUDED_MAP = {"physical_goods": "physical_goods", "financial": "financial_investment_crypto",
                "health_advice": "health_advice", "legal_advice": "legal_advice"}
REQUIRED = {  # official brief field -> our brief fields
    "idea": ("idea",), "skills": ("founder_skills",), "budget": ("budget",), "time_available": ("time_available",),
    "target_market": ("target_customer", "country", "city"), "values": ("values",),
}


class ProductType(BaseModel):
    label: str                      # a digital subtype | an excluded category | "ambiguous"
    group: str                      # digital_product | excluded | ambiguous
    trigger: str                    # the rule or quote that decided it
    decided_by: str                 # "rules" | model id | "onboarding product_check"
    clarifying_question: str | None = None


class DiscoverBrief(BaseModel):
    brief_id: str
    version: int
    required: dict[str, str | None]  # the six official fields (None = unknown)
    unknown: list[str]
    optional: dict[str, str | None]
    tags: dict
    budget_parsed: dict | None = None
    product_type: ProductType
    open_questions: list[str] = []


def _known(fields: dict, name: str) -> str | None:
    f = fields.get(name) or {}
    v = f.get("value")
    return v if f.get("status", "unknown") != "unknown" and isinstance(v, str) and v.strip() else None


def classify(fields: dict, product_check: dict | None = None, model: Callable | None = None,
             model_id: str | None = None) -> ProductType:
    values = {k: _known(fields, k) for k in fields}
    pc = product_check if (product_check or {}).get("status") else check_product(values).as_dict()
    if pc["status"] == "excluded":
        cat = EXCLUDED_MAP.get(pc["categories"][0], pc["categories"][0])
        return ProductType(label=cat, group="excluded", trigger=f"matched: {', '.join(pc.get('matched') or [])}",
                           decided_by="guardrails.check_product")
    text = " ".join(v for k in ("idea", "technical_preferences", "business_model") if (v := values.get(k)))
    if pc["status"] == "allowed":
        about = " ".join(v for k in ("idea", "problem", "business_model") if (v := values.get(k))).lower()
        extra = {cat: [w for w in words if _has(about, w)] for cat, words in EXTRA_BORDERLINE.items()}
        if any(extra.values()):
            pc = {"status": "review", "categories": [c for c, w in extra.items() if w],
                  "matched": [w for ws in extra.values() for w in ws]}
    for label, words in DIGITAL_TYPES.items():
        hit = next((w for w in words if _has(text.lower(), w)), None)
        if hit:
            if pc["status"] == "review":  # e.g. booking software for clinics: digital, but ask once
                return ProductType(
                    label="ambiguous", group="ambiguous", decided_by="rules",
                    trigger=f"digital ('{hit}') but touches {', '.join(pc.get('categories') or [])} "
                            f"({', '.join(pc.get('matched') or [])})",
                    clarifying_question="Does the product itself give medical, legal or financial advice, or move "
                                        "money? If it only helps run the business (bookings, stock, scheduling), "
                                        "it can continue.")
            return ProductType(label=label, group="digital_product", trigger=f"keyword '{hit}'", decided_by="rules")
    if model is not None:
        try:
            data = json.loads(model([{"role": "system", "content": load_prompt("brief_analyzer")},
                                     {"role": "user", "content": f"<untrusted>{text}</untrusted>"}]))
            label, quote = data.get("product_type"), str(data.get("quote") or "")
            if (label in DIGITAL_TYPES or label == "other_digital") and quote and quote.lower() in text.lower():
                return ProductType(label=label, group="digital_product", trigger=f"quote '{quote}'",
                                   decided_by=model_id or "model")
        except Exception:  # noqa: BLE001, S110 - a failed model call leaves the label ambiguous
            pass
    return ProductType(label="ambiguous", group="ambiguous", trigger="no digital product named in the brief",
                       decided_by="rules",
                       clarifying_question="What exactly is the digital product you would sell: an app, software, "
                                           "a template, an online course, a guide, a community...?")


def analyze(brief: dict, model: Callable | None = None, model_id: str | None = None) -> DiscoverBrief:
    fields = brief.get("fields") or {}
    required = {}
    for name, srcs in REQUIRED.items():
        parts = [v for s in srcs if (v := _known(fields, s))]
        required[name] = ", ".join(parts) if parts else None
    optional = {k: _known(fields, k) for k in fields if not any(k in s for s in REQUIRED.values())}
    return DiscoverBrief(
        brief_id=str(brief.get("brief_id")), version=int(brief.get("version") or 0), required=required,
        unknown=[k for k, v in required.items() if v is None], optional=optional, tags=brief.get("tags") or {},
        budget_parsed=brief.get("budget"), open_questions=list(brief.get("open_questions") or []),
        product_type=classify(fields, brief.get("product_check"), model, model_id))
