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
MAX_FACTS = 60
_PHASE = {1: "Discover", 2: "Validate", 4: "Commercial"}
_LABEL_ORDER = {"evidenced": 0, "founder_stated": 1, "inferred": 2, "assumption": 3}
BLOCKS = ("hero", "core", "offers", "delivery", "waitlist", "faq")  # the page's fixed, tested blocks


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
    blocks: list[str] = list(BLOCKS)  # block order on the page, chosen by the model
    key_terms: list[str] = []
    facts: int = 0  # brief fields + Discover / Validate / Commercial items given to the model
    source: Literal["model", "rules"] = "rules"
    model: str | None = None

    def visible_text(self) -> str:
        """Title, offer names and what the core action works on: the text the relevance check reads.
        (Not the filled-in defaults: a spec whose own names are off-brief must fail.)"""
        return " ".join([self.sample_title.value, self.core_object.value] + [o.name.value for o in self.offers])


# ---------------------------------------------------------------- key terms and relevance (also used by the tester)
# No word lists: the terms are the brief's own longest words (long words are the distinctive ones in any language).

def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]{4,}", text.lower())


def key_terms(brief_values: dict[str, str], n: int = 8) -> list[str]:
    """Distinctive words of THIS brief, computed at run time: the idea's longest words first, then the customer's."""
    out: list[str] = []
    for name in ("idea", "target_customer"):
        for t in sorted(dict.fromkeys(_tokens(brief_values.get(name) or "")), key=len, reverse=True):
            if t not in out:
                out.append(t)
            if len(out) == n:
                return out
    return out


def relevance(terms: list[str], text: str) -> tuple[bool, list[str]]:
    """Pass when at least 2 of the brief's key terms (or all, if fewer) appear in the text."""
    low = text.lower()
    hits = [t for t in terms if t in low]
    return (bool(terms) and len(hits) >= min(2, len(terms))), hits


# ---------------------------------------------------------------- rules path: the founder's own words, nothing guessed

def brief_values(inputs: BuildInputs) -> dict[str, str]:
    out = {}
    for i in inputs.items:
        if i.phase == 0 and ":" in i.text:
            name, value = i.text.split(":", 1)
            key = name.strip().replace(" ", "_")
            if key in BRIEF_FIELDS and key not in out:
                out[key] = value.strip()
    return out


def _price(inputs: BuildInputs, v: dict[str, str]) -> Sourced:
    for i in inputs.items:  # a price item from Validate / Commercial first, in its own words
        if i.phase in (2, 4) and i.kind == "price":
            return Sourced(value=i.text[:120], source=f"item:{i.id or i.kind}")
    if v.get("business_model"):  # the founder's own pricing words
        return Sourced(value=v["business_model"][:120], source="brief:business_model")
    return Sourced(value="-", source=ASSUMPTION)


# Page chrome only (labels of the fixed blocks, per page language). No product words: those come from the brief.
_CHROME = {
    "en": {"verb": "Try", "result": "and see a live preview", "field": "Your input", "for": "For", "solves": "Solves",
           "delivery": "Delivery is MOCKED in this prototype: nothing is sent or charged.",
           "who": "Who is it for?", "cost": "What does it cost?"},
    "ar": {"verb": "جرّب", "result": "وشاهد معاينة مباشرة", "field": "مدخلاتك", "for": "لمن", "solves": "يحل",
           "delivery": "التسليم MOCKED في هذا النموذج: لا يُرسل شيء ولا يُخصم شيء.",
           "who": "لمن هذا المنتج؟", "cost": "كم السعر؟"},
}


def _src(v: dict[str, str], name: str, fallback: str) -> Sourced:
    return Sourced(value=v[name][:160], source=f"brief:{name}") if v.get(name) else Sourced(value=fallback,
                                                                                             source=ASSUMPTION)


def from_rules(inputs: BuildInputs) -> ProductSpec:
    """No model: no category guess (offer_kind 'other'); every product word is the founder's own."""
    v = brief_values(inputs)
    t = _CHROME["ar" if inputs.lang == "ar" else "en"]
    idea = _src(v, "idea", "-")
    price = _price(inputs, v)
    target = _src(v, "target_customer", "-")
    lines = [f"{t['for']}: {target.value}"] + ([f"{t['solves']}: {v['problem'][:160]}"] if v.get("problem") else [])
    faq = [(t["who"], target.value)] + ([(t["cost"], price.value)] if price.source != ASSUMPTION else [])
    return ProductSpec(brief_id=inputs.brief_id, lang="ar" if inputs.lang == "ar" else "en", offer_kind="other",
                       offers=[Offer(name=idea, contents=_src(v, "problem", idea.value), for_whom=target,
                                     price=price)],
                       core_verb=t["verb"], core_object=idea, core_result=t["result"],
                       fields=[SpecField(id="f1", label=t["field"])], delivery=t["delivery"], sample_title=idea,
                       sample_lines=lines + ["{f1}"], faq=faq, key_terms=key_terms(v), source="rules")



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
    phase_items = sorted((i for i in inputs.items if i.id and i.phase in (1, 2, 4)),
                         key=lambda i: (_LABEL_ORDER.get(i.label, 9), i.phase))  # sourced evidence first
    facts += [f"item:{i.id} ({_PHASE[i.phase]}, {i.kind}, {i.label}) = {i.text[:240]}"
              + (f" [{i.sources[0]}]" if i.sources else "") for i in phase_items][:MAX_FACTS]
    n_facts = len(facts)
    if feedback:
        facts += ["", "The previous spec failed these checks; fix them:"] + [f"- {f}" for f in feedback]
    raw = json.loads(chat_json([
        {"role": "system", "content": load_prompt("product_spec", kinds=", ".join(KINDS), blocks=", ".join(BLOCKS),
                                                  lang="Arabic" if inputs.lang == "ar" else "English")},
        {"role": "user", "content": "<untrusted>\n" + "\n".join(facts) + "\n</untrusted>"},
    ]))
    if not isinstance(raw, dict):
        return None
    kind = raw.get("offer_kind") if raw.get("offer_kind") in KINDS else base.offer_kind
    order = [b for b in dict.fromkeys(raw.get("blocks") or []) if b in BLOCKS]
    blocks = order + [b for b in BLOCKS if b not in order]  # every block once; the model picks the order
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
    if not offers or obj is None or not fields:  # the model must write the offer and the core action itself
        return None
    return ProductSpec(brief_id=inputs.brief_id, lang=base.lang, offer_kind=kind, offers=offers or base.offers,
                       core_verb=_clean(core.get("verb"), 30) or base.core_verb, core_object=obj or base.core_object,
                       core_result=_clean(core.get("result")) or base.core_result, fields=fields or base.fields,
                       delivery=_clean(raw.get("delivery")) or base.delivery, sample_title=title or base.sample_title,
                       sample_lines=lines or base.sample_lines, faq=faq or base.faq, blocks=blocks,
                       key_terms=base.key_terms, facts=n_facts,
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
