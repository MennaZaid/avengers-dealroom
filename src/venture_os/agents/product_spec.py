"""Phase 3, step 3a: product spec (what the founder sells, what a customer does first, how it reaches them).

The model fills a fixed schema (prompts/product_spec.md); code validates every value: a value must name its source
(a brief field or a Phase 1-2 evidence item) or it is labelled ASSUMPTION; text that breaks a must-never rule is
dropped. Without a model (replay, failure) a minimal spec is derived from the brief fields by rules.
Nothing here is specific to one kind of business: every word shown to a customer comes from the brief.

    spec = product_spec.run(inputs)     # -> ProductSpec; writes outputs/phase3_step3_product_spec.md
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from venture_os.agents.build_inputs import BuildInputs
from venture_os.decision_log import log_action
from venture_os.guardrails import check_output
from venture_os.outputs import write_output
from venture_os.prompts import load_prompt

AGENT = "product_spec"
OfferKind = Literal["digital_download", "interactive_tool", "content_course", "marketplace", "booking_service",
                    "tracker_dashboard", "other"]
KINDS = ("digital_download", "interactive_tool", "content_course", "marketplace", "booking_service",
         "tracker_dashboard", "other")
BRIEF_FIELDS = ("idea", "problem", "target_customer", "supply_side", "business_model", "known_competitors", "city",
                "country", "values", "technical_preferences", "budget")
ASSUMPTION = "ASSUMPTION"

# Generic category words (any language the onboarding supports) -> offer kind. Category words, not businesses.
_KIND_WORDS: dict[str, tuple[str, ...]] = {
    "digital_download": ("template", "download", "pack", "ebook", "e-book", "printable", "toolkit", "bundle",
                         "قالب", "قوالب", "تحميل", "حزمة", "ملف"),
    "content_course": ("course", "lesson", "tutor", "class", "teach", "training", "curriculum", "كورس", "دورة",
                       "دروس", "درس", "تعليم", "منصة دروس", "تدريس"),
    "booking_service": ("booking", "book a", "appointment", "schedul", "reserv", "حجز", "موعد", "مواعيد"),
    "marketplace": ("marketplace", "connect", "match", "platform for", "سوق", "يربط", "تربط", "وسيط"),
    "tracker_dashboard": ("track", "stock", "inventory", "monitor", "dashboard", "تتبع", "مخزون", "متابعة", "جرد"),
    "interactive_tool": ("calculat", "estimat", "quote", "generator", "planner", "حاسبة", "حساب", "تقدير"),
}
_STOP = {"about", "after", "also", "and", "any", "are", "because", "been", "but", "can", "could", "each", "for", "from", "have", "into", "just", "like", "more", "most", "need", "needs", "only", "other", "over", "same", "some", "such", "than", "that", "the", "their", "them", "then", "there", "these", "they", "this", "those", "through", "using", "very", "want", "wants", "what", "when", "where", "which", "while", "who", "will", "with", "without", "would", "your", "you", "our", "people", "online", "simple", "product", "products", "service", "services", "app", "application", "website", "platform", "customers", "customer", "users", "user", "make", "makes", "small", "medium", "business", "businesses"} | {"عايز", "عايزة", "أبي", "اللي", "عشان", "على", "إلى", "الى", "من",
                                                 "في", "مع", "هذا", "هذه", "التي", "الذي", "لكن", "تطبيق", "منصة"}
_PRICE = re.compile(r"(\d[\d,.]*)\s*(usd|egp|sar|aed|kes|eur|gbp|\$|جنيه|ريال|درهم)|(\$|usd|egp)\s*(\d[\d,.]*)",
                    re.IGNORECASE)


class Sourced(BaseModel):
    value: str
    source: str  # "brief:<field>", "item:<id>" or "ASSUMPTION"


class Offer(BaseModel):
    name: Sourced
    contents: Sourced
    for_whom: Sourced
    price: Sourced


class SpecField(BaseModel):
    id: str
    label: str


class ProductSpec(BaseModel):
    brief_id: str
    lang: str = "en"
    offer_kind: OfferKind = "other"
    offers: list[Offer]
    core_verb: str
    core_object: Sourced
    core_result: str
    fields: list[SpecField]  # what the core action asks the customer for (only what it needs)
    delivery: str
    sample_title: Sourced
    sample_lines: list[str]  # may contain {f1}-style slots filled live by the customer's input
    faq: list[tuple[str, str]] = []
    key_terms: list[str] = []
    source: Literal["model", "rules"] = "rules"
    model: str | None = None

    def visible_text(self) -> str:
        """Title, offer names and what the core action works on: the text the relevance check reads.
        (Not the filled-in defaults: a spec whose own names are off-brief must fail.)"""
        return " ".join([self.sample_title.value, self.core_object.value] + [o.name.value for o in self.offers])


# ---------------------------------------------------------------- key terms and relevance (also used by the tester)

def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[^\W\d_]{4,}", text.lower()) if t not in _STOP]


def key_terms(brief_values: dict[str, str], n: int = 8) -> list[str]:
    """Distinctive words of THIS brief (idea weighs most), computed at run time."""
    c: Counter = Counter()
    for name, weight in (("idea", 3), ("target_customer", 2), ("problem", 1), ("business_model", 1)):
        for t in _tokens(brief_values.get(name) or ""):
            c[t] += weight
    return [t for t, _ in c.most_common(n)]


def relevance(terms: list[str], text: str) -> tuple[bool, list[str]]:
    """Pass when at least 2 of the brief's key terms (or all, if fewer) appear in the text."""
    low = text.lower()
    hits = [t for t in terms if t in low]
    return (bool(terms) and len(hits) >= min(2, len(terms))), hits


# ---------------------------------------------------------------- rules path

def brief_values(inputs: BuildInputs) -> dict[str, str]:
    out = {}
    for i in inputs.items:
        if i.phase == 0 and ":" in i.text:
            name, value = i.text.split(":", 1)
            key = name.strip().replace(" ", "_")
            if key in BRIEF_FIELDS and key not in out:
                out[key] = value.strip()
    return out


def choose_kind(v: dict[str, str]) -> str:
    text = " ".join([v.get("idea", ""), v.get("business_model", ""), v.get("problem", "")]).lower()
    scores = {k: sum(text.count(w) for w in words) for k, words in _KIND_WORDS.items()}
    if v.get("supply_side"):
        scores["booking_service" if scores["booking_service"] else "marketplace"] += 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] else "other"


def _price(inputs: BuildInputs, v: dict[str, str]) -> Sourced:
    for i in inputs.items:  # a sourced price from Validate / Commercial first
        if i.phase in (2, 4) and i.kind == "price" and (m := _PRICE.search(i.text)):
            return Sourced(value=m.group(0).rstrip(",. "), source=f"item:{i.id or i.kind}")
    if v.get("business_model"):  # the founder's own pricing words, whole (one or several prices)
        return Sourced(value=v["business_model"][:120], source="brief:business_model")
    return Sourced(value="to be set by the founder", source=ASSUMPTION)


_T = {  # fixed copy per language; {x} is filled from the brief
    "en": {"verbs": {"digital_download": "Fill in", "interactive_tool": "Enter", "content_course": "Tell us",
                     "marketplace": "Describe", "booking_service": "Choose", "tracker_dashboard": "Add",
                     "other": "Try"},
           "object": "your details in a sample of {idea}",
           "result": "and see your own version build live, ready to print or download",
           "fields": ["Your name", "What you need", "Details"],
           "delivery": {"digital_download": "An instant file download after purchase (MOCKED).",
                        "content_course": "An access link to the material after purchase (MOCKED).",
                        "booking_service": "A booking confirmation on screen (MOCKED: nothing is sent).",
                        "marketplace": "A request saved for providers to answer (MOCKED: nothing is sent).",
                        "tracker_dashboard": "Works in the browser; data stays on this device.",
                        "interactive_tool": "Works in the browser; results can be downloaded.",
                        "other": "A file download after purchase (MOCKED)."},
           "for": "For: {x}", "solves": "Solves: {x}", "faq": [("Who is it for?", "{target}"),
                                                               ("How do I receive it?", "{delivery}"),
                                                               ("What does it cost?", "{price}")]},
    "ar": {"verbs": {"digital_download": "املأ", "interactive_tool": "أدخل", "content_course": "أخبرنا",
                     "marketplace": "صِف", "booking_service": "اختر", "tracker_dashboard": "أضف", "other": "جرّب"},
           "object": "بياناتك في نموذج من {idea}",
           "result": "وشاهد نسختك تُبنى أمامك، جاهزة للطباعة أو التحميل",
           "fields": ["اسمك", "ما تحتاجه", "التفاصيل"],
           "delivery": {"digital_download": "تحميل فوري للملف بعد الشراء (MOCKED).",
                        "content_course": "رابط وصول للمحتوى بعد الشراء (MOCKED).",
                        "booking_service": "تأكيد الحجز على الشاشة (MOCKED: لا يُرسل شيء).",
                        "marketplace": "طلب محفوظ ليرد عليه مقدمو الخدمة (MOCKED: لا يُرسل شيء).",
                        "tracker_dashboard": "يعمل في المتصفح؛ البيانات تبقى على هذا الجهاز.",
                        "interactive_tool": "يعمل في المتصفح؛ يمكن تحميل النتائج.",
                        "other": "تحميل ملف بعد الشراء (MOCKED)."},
           "for": "لمن: {x}", "solves": "يحل: {x}", "faq": [("لمن هذا المنتج؟", "{target}"),
                                                          ("كيف أستلمه؟", "{delivery}"),
                                                          ("كم السعر؟", "{price}")]},
}


def _src(v: dict[str, str], name: str, fallback: str) -> Sourced:
    return Sourced(value=v[name][:160], source=f"brief:{name}") if v.get(name) else Sourced(value=fallback,
                                                                                             source=ASSUMPTION)


def from_rules(inputs: BuildInputs) -> ProductSpec:
    v = brief_values(inputs)
    lang = "ar" if inputs.lang == "ar" else "en"
    t = _T[lang]
    kind = choose_kind(v)
    idea = _src(v, "idea", "the product")
    price = _price(inputs, v)
    target = _src(v, "target_customer", "early customers")
    fields = [SpecField(id=f"f{n + 1}", label=lab) for n, lab in enumerate(t["fields"])]
    delivery = t["delivery"][kind]
    lines = [t["for"].format(x=target.value)]
    if v.get("problem"):
        lines.append(t["solves"].format(x=v["problem"][:160]))
    lines += ["{f1}", "{f2}", "{f3}"]
    price_text = price.value + (f" ({ASSUMPTION})" if price.source == ASSUMPTION else "")
    faq = [(q, a.format(target=target.value, delivery=delivery, price=price_text)) for q, a in t["faq"]]
    spec = ProductSpec(brief_id=inputs.brief_id, lang=lang, offer_kind=kind,
                       offers=[Offer(name=idea, contents=_src(v, "business_model", idea.value), for_whom=target,
                                     price=price)],
                       core_verb=t["verbs"][kind], core_object=Sourced(value=t["object"].format(idea=idea.value),
                                                                       source=idea.source),
                       core_result=t["result"], fields=fields, delivery=delivery, sample_title=idea,
                       sample_lines=lines, faq=faq, key_terms=key_terms(v), source="rules")
    return spec


# ---------------------------------------------------------------- model path (validated in code)

def _clean(x, n=160) -> str:
    s = " ".join(str(x or "").split())[:n]
    return "" if not s or check_output(s) else s


def _sourced(raw, valid: set[str]) -> Sourced | None:
    if not isinstance(raw, dict):
        return None
    value = _clean(raw.get("value"))
    if not value:
        return None
    src = str(raw.get("source") or "")
    return Sourced(value=value, source=src if src in valid else ASSUMPTION)  # no known source -> ASSUMPTION


def from_model(inputs: BuildInputs, chat_json: Callable[[list[dict]], str],
               feedback: list[str] | None = None) -> ProductSpec | None:
    base = from_rules(inputs)
    v = brief_values(inputs)
    valid = {f"brief:{k}" for k in v} | {f"item:{i.id}" for i in inputs.items if i.id and i.phase in (1, 2, 4)}
    facts = [f"brief:{k} = {val}" for k, val in v.items()]
    facts += [f"item:{i.id} = {i.text[:200]}" for i in inputs.items if i.id and i.phase in (1, 2, 4)][:20]
    if feedback:
        facts += ["", "The previous spec failed these checks; fix them:"] + [f"- {f}" for f in feedback]
    raw = json.loads(chat_json([
        {"role": "system", "content": load_prompt("product_spec", kinds=", ".join(KINDS),
                                                  lang="Arabic" if inputs.lang == "ar" else "English")},
        {"role": "user", "content": "<untrusted>\n" + "\n".join(facts) + "\n</untrusted>"},
    ]))
    if not isinstance(raw, dict):
        return None
    kind = raw.get("offer_kind") if raw.get("offer_kind") in KINDS else base.offer_kind
    offers = []
    for o in raw.get("offers") or []:
        if not isinstance(o, dict):
            continue
        parts = {k: _sourced(o.get(k), valid) for k in ("name", "contents", "for_whom", "price")}
        if parts["name"] is None:
            continue
        parts = {k: p or getattr(base.offers[0], k) for k, p in parts.items()}
        offers.append(Offer(**parts))
        if len(offers) == 4:
            break
    core = raw.get("core_action") if isinstance(raw.get("core_action"), dict) else {}
    obj = _sourced({"value": core.get("object"), "source": core.get("source")}, valid)
    fields = [SpecField(id=f"f{n + 1}", label=lab) for n, lab in
              enumerate([c for c in (_clean(f, 40) for f in (raw.get("fields") or [])) if c][:5])]
    lines = [c for c in (_clean(x, 200) for x in (raw.get("sample_lines") or [])) if c][:8]
    title = _sourced(raw.get("sample_title"), valid)
    faq = [(q, a) for q, a in ((_clean(f.get("q")), _clean(f.get("a"), 240)) for f in (raw.get("faq") or [])
                               if isinstance(f, dict)) if q and a][:5]
    return ProductSpec(brief_id=inputs.brief_id, lang=base.lang, offer_kind=kind, offers=offers or base.offers,
                       core_verb=_clean(core.get("verb"), 30) or base.core_verb, core_object=obj or base.core_object,
                       core_result=_clean(core.get("result")) or base.core_result, fields=fields or base.fields,
                       delivery=_clean(raw.get("delivery")) or base.delivery, sample_title=title or base.sample_title,
                       sample_lines=lines or base.sample_lines, faq=faq or base.faq, key_terms=base.key_terms,
                       source="model")


def to_markdown(spec: ProductSpec) -> str:
    def s(x: Sourced) -> str:
        return f"{x.value} _(source: {x.source})_"
    lines = ["# Phase 3, step 3: product spec", "", f"Brief id: `{spec.brief_id}`", "",
             (f"Offer kind: **{spec.offer_kind}**. Drafted by: "
             f"{'model ' + (spec.model or '') if spec.source == 'model' else 'fixed rules (no model)'}."), "",
             "## Offers", ""]
    for o in spec.offers:
        lines += [f"- **{s(o.name)}**", f"  - Inside: {s(o.contents)}", f"  - For: {s(o.for_whom)}",
                  f"  - Price: {s(o.price)}"]
    lines += ["", "## Core action (first 60 seconds)", "",
              f"{spec.core_verb} {s(spec.core_object)} {spec.core_result}", "",
              "Asks for: " + ", ".join(f.label for f in spec.fields), "", "## Delivery", "", spec.delivery, "",
              "## Sample content", "", f"**{s(spec.sample_title)}**", ""] + [f"- {x}" for x in spec.sample_lines]
    lines += ["", "## Key terms from the brief (relevance check)", "", ", ".join(spec.key_terms) or "-"]
    return "\n".join(lines) + "\n"


def run(inputs: BuildInputs, chat_json: Callable[[list[dict]], str] | None = None, model: str | None = None,
        feedback: list[str] | None = None) -> ProductSpec:
    if chat_json is None:
        from venture_os.config import Settings
        from venture_os.llm.client import chat_json as live_chat
        from venture_os.llm.client import live_enabled
        if live_enabled():
            chat_json, model = live_chat, model or Settings().llm_model_extract
    spec = None
    if chat_json is not None:
        try:
            spec = from_model(inputs, chat_json, feedback)
        except Exception:  # noqa: BLE001 - model down or bad JSON: rules take over
            spec = None
        if spec is not None and not relevance(spec.key_terms, spec.visible_text())[0]:
            spec = None  # never keep a spec that is not about this brief
    if spec is None:
        spec = from_rules(inputs)
    else:
        spec.model = model
    write_output(3, 3, "product_spec", to_markdown(spec))
    log_action(AGENT, "spec_product", sources=[], model=spec.model, cost=0, approved_by=None, outcome=spec.source,
               brief_id=inputs.brief_id, offer_kind=spec.offer_kind, offers=len(spec.offers),
               revision=bool(feedback), assumptions=sum(o.price.source == ASSUMPTION for o in spec.offers))
    return spec
