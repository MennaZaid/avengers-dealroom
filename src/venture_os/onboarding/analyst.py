"""Brief Analyzer: tags the brief and writes idea-specific follow-up questions.

RuleAnalyst needs no model (zero cost) and is always the fallback. LLMAnalyst asks the model, but keeps a
tag only if it is in the fixed vocabulary and a question only if it really is a short question; anything
else falls back to the rules. Country and languages always come from rules, never from the model.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Protocol

from venture_os.onboarding import tags as T
from venture_os.prompts import load_prompt

MAX_FOLLOWUPS = 3

# (condition on tags, English, Arabic). Checked in order; the first MAX_FOLLOWUPS that apply are asked.
_RULE_QUESTIONS: list[tuple[Callable[[dict], bool], str, str]] = [
    (lambda t: True,
     "Have you talked to any potential customers yet? What did they tell you?",
     "هل تحدثت مع عملاء محتملين؟ ماذا قالوا لك؟"),
    (lambda t: "food_beverage" in t["industries"],
     "Who will prepare the food, and do you have (or plan to get) the food-safety licences needed?",
     "من سيحضّر الطعام، وهل لديك (أو تخطط للحصول على) تراخيص سلامة الغذاء المطلوبة؟"),
    (lambda t: "fintech" in t["industries"],
     "Will you hold or move customers' money yourself, or work with a licensed bank or payment provider?",
     "هل ستحتفظ بأموال العملاء أو تنقلها بنفسك، أم ستعمل مع بنك أو مزود دفع مرخص؟"),
    (lambda t: "health" in t["industries"],
     "Will you give medical advice or handle health data? Which licensed professionals will be involved?",
     "هل ستقدم نصائح طبية أو تتعامل مع بيانات صحية؟ ومن المتخصصون المرخصون المشاركون؟"),
    (lambda t: "education" in t["industries"],
     "Who pays: the learner, the parents, or an institution such as a school or employer?",
     "من يدفع: المتعلم، أم الأهل، أم جهة مثل مدرسة أو صاحب عمل؟"),
    (lambda t: "handmade_crafts" in t["industries"] or "manufacturing" in t["industries"],
     "Who makes the products, and roughly how many can you produce per month?",
     "من يصنع المنتجات، وكم قطعة تقريباً يمكنك إنتاجها شهرياً؟"),
    (lambda t: "delivery_logistics" in t["industries"],
     "Will you run your own delivery, or use existing couriers or delivery apps?",
     "هل ستدير التوصيل بنفسك، أم ستستخدم شركات شحن أو تطبيقات توصيل قائمة؟"),
    (lambda t: t["revenue_model"] == "commission" or t["customer_type"] == "b2b2c",
     "How will you get the first sellers or service providers to join before you have customers?",
     "كيف ستقنع أول البائعين أو مقدمي الخدمة بالانضمام قبل أن يكون لديك عملاء؟"),
    (lambda t: t["customer_type"] in ("b2b", "b2g"),
     "Can you name 3-5 organisations that might try it first, and who decides to buy there?",
     "هل يمكنك تسمية 3 إلى 5 جهات قد تجربه أولاً، ومن صاحب قرار الشراء فيها؟"),
    (lambda t: t["revenue_model"] == "unknown",
     "What do you think a customer would pay, and how often (per order, per month...)?",
     "كم تتوقع أن يدفع العميل، وكم مرة (لكل طلب، شهرياً...)؟"),
    (lambda t: True,
     "What do your customers use today to solve this problem, and why would they switch?",
     "ماذا يستخدم عملاؤك اليوم لحل هذه المشكلة، ولماذا سينتقلون إليك؟"),
]


# A question about the market, prices, statistics or law is for research, not for the founder.
RESEARCH_QUESTION = re.compile(
    r"\baverage\b|market size|how big is|statistic|what percentage|how many\b|existing solutions|"
    r"\bregulation|\blaws?\b|legal requirement|government rule|"
    r"متوسط|حجم السوق|إحصا|احصا|ما نسبة|كم عدد|لوائح|قوانين|القانون|متطلبات قانونية|متطلبات الترخيص|متطلبات ترخيص",
    re.IGNORECASE)
# Words that address the founder directly. A question to the founder about their own plans uses them.
_TO_FOUNDER = re.compile(
    r"\byou(r|rs|rself)?\b|لديك|عندك|أنت|انت|هل ست|كيف ست|تخطط|اتخذت|خطتك|فريقك|مشروعك|عملاءك|عملائك|ستضمن|ستقوم",
    re.IGNORECASE)


def is_research_question(q: str) -> bool:
    """True for questions research should answer, not the founder: market facts, numbers, laws, or (in English)
    any question that is not addressed to the founder at all ('How many pharmacies are there in Nairobi?')."""
    to_founder = bool(_TO_FOUNDER.search(q))
    if RESEARCH_QUESTION.search(q) and not to_founder:
        return True
    return not to_founder and not re.search(r"[؀-ۿ]", q)


class Analyst(Protocol):
    def tags(self, fields: dict[str, str | None], lang: str) -> dict[str, tuple[object, str]]: ...

    def questions(self, fields: dict[str, str | None], tags: dict, lang: str
                  ) -> tuple[list[tuple[str, str]], list[str]]:
        """(follow-ups for the founder as (question, source), open questions for the research stage)."""
        ...


class RuleAnalyst:
    """tags() -> {name: (value, "rules")}; followups() -> [(question, "rules")]."""

    def tags(self, fields, lang):
        return {k: (v, "rules") for k, v in T.rule_tags(fields, lang).items()}

    def followups(self, fields, tags, lang):
        tags = {"industries": [], "customer_type": "unknown", "revenue_model": "unknown", **(tags or {})}
        out = []
        for cond, en, ar in _RULE_QUESTIONS:
            if cond(tags) and len(out) < MAX_FOLLOWUPS:
                out.append((ar if lang == "ar" else en, "rules"))
        return out

    def questions(self, fields, tags, lang):
        return self.followups(fields, tags, lang), []


def _brief_text(fields: dict[str, str | None]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in fields.items() if v)


def tags_prompt() -> str:
    """prompts/brief_tagger.md with the allowed values filled in."""
    return load_prompt("brief_tagger", industries=str(sorted(T.ALLOWED["industries"])),
                       customer_types=str(list(T.CUSTOMER_TYPES)), revenue_models=str(list(T.REVENUE_MODELS)))

_QUESTION = re.compile(r"^[^<>{}]{10,300}[?؟]$")


class LLMAnalyst:
    def __init__(self, chat_json: Callable[[list[dict]], str], fallback: RuleAnalyst | None = None,
                 model: str | None = "model"):
        self.chat_json = chat_json
        self.model = model  # recorded in decision_log.json
        self.rules = fallback or RuleAnalyst()

    def _ask(self, system: str, fields) -> dict:
        try:
            raw = json.loads(self.chat_json([
                {"role": "system", "content": system},
                {"role": "user", "content": f"<untrusted>\n{_brief_text(fields)[:20000]}\n</untrusted>"},
            ]))
            return raw if isinstance(raw, dict) else {}
        except Exception:  # noqa: BLE001 - network or JSON failure: rules take over
            return {}

    def tags(self, fields, lang):
        out = self.rules.tags(fields, lang)
        raw = self._ask(tags_prompt(), fields)
        for name in ("industries", "customer_type", "revenue_model"):
            v = T.clean_tag(name, raw.get(name)) if name in raw else None
            if v is not None:
                out[name] = (v, "model")
        if out["industries"][0] == ["other"] and T.rule_tags(fields, lang)["industries"] != ["other"]:
            out["industries"] = (T.rule_tags(fields, lang)["industries"], "rules")  # 'other' says nothing
        if not fields.get("business_model"):  # the founder has not said how it makes money: don't guess
            out["revenue_model"] = ("unknown", "rules")
        return out

    def followups(self, fields, tags, lang):
        return self.questions(fields, tags, lang)[0]

    def questions(self, fields, tags, lang):
        raw = self._ask(load_prompt("followup_questions", lang="Arabic" if lang == "ar" else "English"), fields)
        founder, research = [], []
        for key in ("questions", "research_questions"):
            items = raw.get(key)
            for q in items if isinstance(items, list) else []:
                q = " ".join(str(q).split())
                if not _QUESTION.match(q) or "http" in q.lower() or q in founder or q in research:
                    continue
                # The model sometimes files a research question as a founder question: move it.
                (research if key == "research_questions" or is_research_question(q) else founder).append(q)
        out = [(q, "model") for q in founder[:MAX_FOLLOWUPS]]
        for q, src in self.rules.followups(fields, tags, lang):  # top up with rule questions if few are left
            if len(out) < MAX_FOLLOWUPS and q not in founder:
                out.append((q, src))
        return out, research[:MAX_FOLLOWUPS]
