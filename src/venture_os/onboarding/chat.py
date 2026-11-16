"""Onboarding conversation logic. Pure functions on OnboardingState: no database, no network.

Flow: greet -> ask each missing required field -> offer the optional ones -> up to 3 follow-up questions
specific to the idea -> summary with tags -> founder confirms -> brief version 1 is saved.

- Documents can be uploaded at any point; their values are marked "from document".
- "skip" (or "لا أعرف") records a field as unknown, never invented.
- Values the model deduced but the founder did not say (country from a city) are marked "inferred" and
  pointed out, so the founder confirms or corrects them.
- In the summary, corrections work with a label ("budget: 30,000 EGP") or without one
  ("change the budget to 30,000 EGP"); if it is unclear which line is meant, the bot asks.
- After confirming, the founder can still edit ("edit", or just send a correction). Each new "yes" saves the
  next brief version; "cancel" keeps the saved version. The API stores versions; stages pin the version they used.
"""

from __future__ import annotations

import logging
import re

from venture_os import guardrails
from venture_os.decision_log import log_action
from venture_os.onboarding import tags as T
from venture_os.onboarding.analyst import Analyst, RuleAnalyst
from venture_os.onboarding.brief import (
    BY_NAME,
    FIELDS,
    REQUIRED,
    FieldValue,
    FollowUp,
    Message,
    OnboardingState,
    Tag,
    label,
)
from venture_os.onboarding.extract import Extractor
from venture_os.onboarding.money import format_budget, parse_budget

_logger = logging.getLogger(__name__)
ARABIC = re.compile(r"[؀-ۿ]")
SKIP = re.compile(r"^\s*(skip|pass|don'?t know|i don'?t know|not sure|n/?a|تخطي|تخطى|لا أعرف|لا اعرف|مش عارف)\s*[.!]?\s*$",
                  re.IGNORECASE)
YES = re.compile(r"^\s*(yes|y|yeah|yep|confirm|correct|ok|okay|looks good|save|نعم|أكد|اكد|صحيح|تمام|موافق|احفظ|"
                 r"أيوه|ايوه|أيوة|ايوة|اه|آه|صح|مظبوط|مضبوط|اوكي|أوكي)\s*[.!]?\s*$", re.IGNORECASE)
EDIT = re.compile(r"^\s*(edit|change|update|modify|edit brief|تعديل|عدل|تغيير|عايز اغير|عايز أغير)\s*[.!]?\s*$",
                  re.IGNORECASE)
CANCEL = re.compile(r"^\s*(cancel|undo|keep it|never ?mind|إلغاء|الغاء|خلاص|سيبه)\s*[.!]?\s*$", re.IGNORECASE)

OPTIONAL = "__optional__"
FOLLOWUP = "__followup__:"
CONFIRM = "__confirm__:"
# Descriptive fields where 1-3 words picked up in passing ("Pharmacist") are probably incomplete.
# Country, city, budget and time are naturally short, so they are not re-asked.
THIN_FIELDS = {"idea", "problem", "target_customer", "founder_skills"}

TEXT = {
    "greet": {
        "en": "Hi! I'll help you set up your founder brief. You can type answers or upload documents "
              "(PDF, Word, text) such as a pitch deck or notes, and I'll read them. Nothing starts until you confirm.",
        "ar": "مرحباً! سأساعدك في إعداد ملف المؤسس. يمكنك كتابة الإجابات أو رفع مستندات "
              "(PDF أو Word أو نص) مثل عرض تقديمي أو ملاحظات وسأقرأها. لن يبدأ أي شيء قبل تأكيدك.",
    },
    "optional": {
        "en": "Thanks, I have the essentials. Optional, but helpful: {names}. "
              "Answer any of them one per line, like 'business model: subscription', or type 'skip'.",
        "ar": "شكراً، لدي الأساسيات. معلومات اختيارية مفيدة: {names}. "
              "أجب عن أي منها سطراً لكل معلومة، مثل 'business model: اشتراك'، أو اكتب 'تخطي'.",
    },
    "followup_intro": {
        "en": "A few questions about your idea specifically (type 'skip' for any you can't answer yet):",
        "ar": "بعض الأسئلة الخاصة بفكرتك (اكتب 'تخطي' لأي سؤال لا تعرف إجابته بعد):",
    },
    "summary": {
        "en": "Here is your brief (* = required). Please check it. Reply 'yes' to confirm, or correct a line, "
              "like 'budget: 30,000 EGP' or 'change the city to Giza'.",
        "ar": "هذا ملخص ملفك (* = مطلوب). يرجى مراجعته. اكتب 'نعم' للتأكيد، أو صحح سطراً، "
              "مثل 'الميزانية: 30,000 جنيه' أو 'غير المدينة إلى الجيزة'.",
    },
    "summary_edit": {
        "en": "Reply 'yes' to save these changes as a new version, or 'cancel' to keep version {v}.",
        "ar": "اكتب 'نعم' لحفظ التعديلات كنسخة جديدة، أو 'إلغاء' للإبقاء على النسخة {v}.",
    },
    "confirmed": {
        "en": "Brief confirmed and saved as version 1. You can start the Discover stage now. "
              "You can still change it later: type 'edit' or just send a correction.",
        "ar": "تم تأكيد الملف وحفظه كنسخة أولى. يمكنك الآن بدء مرحلة الاكتشاف. "
              "يمكنك تعديله لاحقاً: اكتب 'تعديل' أو أرسل التصحيح مباشرة.",
    },
    "saved_version": {
        "en": "Saved as version {v} (changed: {names}). Stages that used an older version will be marked stale "
              "and need to be re-checked.",
        "ar": "تم الحفظ كنسخة {v} (تم تغيير: {names}). المراحل التي استخدمت نسخة أقدم ستُعلَّم كقديمة "
              "وتحتاج إلى مراجعة.",
    },
    "no_change": {
        "en": "Nothing changed, so your brief stays at version {v}.",
        "ar": "لم يتغير شيء، لذلك يبقى ملفك على النسخة {v}.",
    },
    "edit_intro": {
        "en": "Sure. This is your confirmed brief (version {v}). Correct any line; nothing changes until you "
              "reply 'yes'.",
        "ar": "بالتأكيد. هذا ملفك المؤكد (النسخة {v}). صحح أي سطر؛ لن يتغير شيء حتى تكتب 'نعم'.",
    },
    "cancelled": {
        "en": "Changes discarded. Your brief stays at version {v}.",
        "ar": "تم تجاهل التعديلات. يبقى ملفك على النسخة {v}.",
    },
    "updated": {"en": "Updated: {names}.", "ar": "تم التحديث: {names}."},
    "which_line": {
        "en": "I'm not sure which line to change. Please name it, like 'budget: 30,000 EGP'.",
        "ar": "لست متأكداً أي سطر تريد تغييره. يرجى ذكره، مثل 'الميزانية: 30,000 جنيه'.",
    },
    "which_of": {
        "en": "That could change {names}. Which one? Reply like '{first}: <new value>'.",
        "ar": "قد يغير ذلك: {names}. أيها تقصد؟ اكتب مثل '{first}: <القيمة الجديدة>'.",
    },
    "bad_tag": {
        "en": "'{value}' is not a valid {name}. Allowed values: {allowed}.",
        "ar": "'{value}' ليست قيمة صحيحة لـ {name}. القيم المسموحة: {allowed}.",
    },
    "inferred_note": {
        "en": "Note: I assumed {items}. That was not stated directly, so please correct it if it's wrong.",
        "ar": "ملاحظة: افترضت {items}. لم يُذكر ذلك صراحة، لذا صححه إن كان خطأ.",
    },
    "doc_found": {
        "en": "I read {doc}. I found: {names}. These are marked 'from document' and you'll confirm them at the end.",
        "ar": "قرأت {doc}. وجدت: {names}. تم تمييزها بأنها 'من المستند' وستؤكدها في النهاية.",
    },
    "doc_none": {
        "en": "I read {doc} but couldn't find brief details in it with confidence.",
        "ar": "قرأت {doc} لكن لم أجد فيه تفاصيل واضحة للملف.",
    },
    "open_head": {
        "en": "Questions for the research stage (you don't need to answer these):",
        "ar": "أسئلة ستبحث عنها مرحلة الاكتشاف (لا تحتاج للإجابة عليها):",
    },
    "confirm_inferred": {
        "en": "I assumed the {label} is \"{value}\" (from \"{quote}\"). Is that right? Reply 'yes', or type the "
              "correct {label}.",
        "ar": "افترضت أن {label}: \"{value}\" (من \"{quote}\"). هل هذا صحيح؟ اكتب 'نعم'، أو اكتب القيمة الصحيحة.",
    },
    "thin_value": {
        "en": "So far I noted {label}: \"{value}\". Reply 'yes' if that's all, or give the full answer:",
        "ar": "سجلت حتى الآن {label}: \"{value}\". اكتب 'نعم' إن كان هذا كل شيء، أو اكتب الإجابة الكاملة:",
    },
    "idea_changed": {
        "en": "Your idea changed, so let me check the parts that described the old one.",
        "ar": "تغيّرت فكرتك، لذا دعني أراجع الأجزاء التي كانت تصف الفكرة السابقة.",
    },
    "recheck": {
        "en": "For the new idea, is the {label} still \"{value}\"? Reply 'yes', or type the new {label}.",
        "ar": "بالنسبة للفكرة الجديدة، هل {label} ما زال \"{value}\"؟ اكتب 'نعم'، أو اكتب القيمة الجديدة.",
    },
    "doc_again": {
        "en": "I already read {doc}, so I didn't read it again.",
        "ar": "قرأت {doc} من قبل، لذلك لم أقرأه مرة أخرى.",
    },
    "confirmed_hint": {
        "en": "Your brief is saved as version {v}. Type 'edit' to change it.",
        "ar": "ملفك محفوظ كنسخة {v}. اكتب 'تعديل' لتغييره.",
    },
    "summary_hint": {
        "en": "Reply 'yes' to confirm the brief, or correct a line.",
        "ar": "اكتب 'نعم' لتأكيد الملف، أو صحح سطراً.",
    },
    "product_head": {"en": "Product check:", "ar": "فحص المنتج:"},
    "product_allowed": {"en": "✅", "ar": "✅"},
    "product_review": {"en": "⚠️", "ar": "⚠️"},
    "product_excluded": {"en": "⛔", "ar": "⛔"},
    "cannot_confirm": {
        "en": "I can't confirm this brief yet.",
        "ar": "لا أستطيع تأكيد هذا الملف بعد.",
    },
    "doc_instructions": {
        "en": "{doc} contains instructions to me; I ignored them and only read it as information.",
        "ar": "يحتوي {doc} على تعليمات موجهة لي؛ تجاهلتها وقرأته كمعلومات فقط.",
    },
    "unknown": {"en": "unknown", "ar": "غير معروف"},
    "doc_tag": {"en": "from document", "ar": "من المستند"},
    "inferred_tag": {"en": "inferred from \"{q}\", please check", "ar": "مستنتج من \"{q}\"، يرجى التحقق"},
    "tags_head": {
        "en": "Tags (used to choose research sources; correct like 'industry: education'):",
        "ar": "التصنيفات (تُستخدم لاختيار مصادر البحث؛ صححها مثل 'industry: education'):",
    },
    "followups_head": {
        "en": "Follow-up answers (correct like 'q1: ...'):",
        "ar": "إجابات الأسئلة الإضافية (صححها مثل 'q1: ...'):",
    },
}

TAG_LABELS = {"industry": "industries", "industries": "industries", "customer_type": "customer_type",
              "revenue_model": "revenue_model", "country_code": "country_code",
              "languages": "languages", "language": "languages",
              "القطاعات": "industries", "القطاع": "industries", "نوع_العملاء": "customer_type",
              "نموذج_الإيرادات": "revenue_model", "رمز_الدولة": "country_code", "اللغات": "languages"}
TAG_ALLOWED_TEXT = {
    "industries": ", ".join(sorted(T.ALLOWED["industries"])),
    "customer_type": ", ".join(T.CUSTOMER_TYPES),
    "revenue_model": ", ".join(T.REVENUE_MODELS),
    "country_code": "ISO codes such as EG, SA, AE",
    "languages": "en, ar",
}


def _t(key: str, lang: str, **kw) -> str:
    return TEXT[key][lang].format(**kw)


def _label(name: str, lang: str = "en") -> str:
    return label(name, lang)


def _say(state: OnboardingState, text: str) -> str:
    state.messages.append(Message(role="assistant", text=text))
    return text


def start(state: OnboardingState, analyst: Analyst | None = None) -> str:
    q = _next_question(state, analyst or RuleAnalyst())
    return _say(state, _t("greet", state.lang) + "\n\n" + (q or ""))


# ---------- applying values ----------

def _apply(state: OnboardingState, found: dict, status: str, source: str) -> tuple[list[str], list[str]]:
    """Set fields from extracted values. Returns (names set, names that were inferred)."""
    names, inferred = [], []
    for name, item in found.items():
        current = state.get(name)
        st = "inferred" if item.get("inferred") else status
        if current.status == "answered" and st != "answered":
            continue  # the founder's own words beat a document or a deduction
        if st == "inferred" and state.filled(name):
            continue  # a deduction never replaces a value we already have
        new = FieldValue(value=item["value"], status=st, source=source, quote=item.get("quote"))
        if new.value != current.value or new.status != current.status:
            _mark_changed(state, name)
        state.fields[name] = new
        if name in state.skipped:
            state.skipped.remove(name)
        names.append(name)
        if st == "inferred":
            inferred.append(name)
    return names, inferred


def _mark_changed(state: OnboardingState, name: str) -> None:
    state.tags_stale = True
    if name not in state.changed:
        state.changed.append(name)


def _log(agent: str, action: str, **kw) -> None:
    """Write a decision_log.json entry; logging problems never break the chat."""
    try:
        log_action(agent, action, **kw)
    except Exception as e:  # noqa: BLE001
        _logger.warning("decision log write failed: %s", e)


def _extract(extractor: Extractor, state: OnboardingState, text: str, what: str) -> dict:
    """Run the extractor and log the model call (rule-based runs without a model make no entry)."""
    found = extractor.extract(text, kind=_kind(state, what))
    if "supply_side" in found and not (two_sided(state) or _TWO_SIDED.search(text)):
        del found["supply_side"]  # only marketplace / booking ideas have a supply side
    if (model := getattr(extractor, "model", None)) is not None:
        _log("brief_extractor", "extract_fields", model=model, cost=0, source_type=what, fields=sorted(found))
    return found


def _product_check(state: OnboardingState) -> guardrails.ProductCheck:
    """Run the product rules on the brief; log when the result changes."""
    check = guardrails.check_product(_field_values(state))
    if check.as_dict() != state.product_check:
        state.product_check = check.as_dict()
        _log("guardrails", "check_product", outcome=check.status, categories=check.categories)
    return check


_TWO_SIDED = re.compile(
    r"marketplace|\bconnect(s|ing)?\b.{0,40}\b(with|to)\b|\bplatform\b.{0,30}\b(to|for|where)\b.{0,25}"
    r"\b(book|hire|find|order)|\b(book|booking|hire|hiring)\b.{0,30}\b(cleaners?|tutors?|teachers?|drivers?|"
    r"freelancers?|providers?|workers?|artisans?|nann(y|ies)|technicians?|designers?|coaches?)\b|"
    r"يربط|تربط|(منصة|تطبيق|ابلكيشن|أبلكيشن).{0,30}(لحجز|تجمع|يجمع)|"
    r"حجز.{0,15}(عمال|عامل|مدرس|مدرسين|معلم|معلمين|فني|فنيين|سائق|حرفي|حرفيين|مصمم)|"
    r"(?<![\u0600-\u06FF])سوق (إلكتروني|الكتروني|أونلاين|اونلاين)",
    re.IGNORECASE)


def two_sided(state: OnboardingState) -> bool:
    """A marketplace or booking platform: paying customers on one side, providers on the other."""
    text = " ".join(v for k in ("idea", "problem", "target_customer", "business_model")
                    if (v := state.get(k).value))
    tags = {k: v.value for k, v in state.tags.items()}
    return bool(_TWO_SIDED.search(text)) or tags.get("customer_type") == "b2b2c" or (
        tags.get("revenue_model") == "commission" and "platform" in text.lower())


def _parse_budget(state: OnboardingState) -> None:
    code = state.tags.get("country_code")
    state.budget_parsed = parse_budget(state.get("budget").value, code.value if code else None)


def _kind(state: OnboardingState, what: str) -> str:
    """Tell the extractor which language to write values in (the founder's)."""
    return f"{what}. Write every value in {'Arabic' if state.lang == 'ar' else 'English'}"


def _inferred_note(state: OnboardingState, names: list[str]) -> str:
    if state.phase == "collecting":  # required ones get their own "is that right?" question instead
        names = [n for n in names if not BY_NAME[n].required]
    if not names:
        return ""
    items = ", ".join(f"{_label(n, state.lang)} = {state.get(n).value} (\"{state.get(n).quote}\")" for n in names)
    return _t("inferred_note", state.lang, items=items) + "\n\n"


def _field_values(state: OnboardingState) -> dict[str, str | None]:
    return {f.name: state.get(f.name).value for f in FIELDS}


def _retag(state: OnboardingState, analyst: Analyst) -> None:
    """Recompute tags from the fields. Tags the founder set by hand are kept."""
    if not state.tags_stale and state.tags:
        return
    for name, (value, basis) in analyst.tags(_field_values(state), state.lang).items():
        current = state.tags.get(name)
        if current and current.basis == "founder":
            continue
        if (current is None or current.value != value) and state.version:
            _mark_changed(state, f"tag:{name}")
        state.tags[name] = Tag(value=value, basis=basis)
    state.tags_stale = False
    _log("brief_tagger", "tag_brief", model=getattr(analyst, "model", None), cost=0,
         tags={k: v.value for k, v in state.tags.items()})


# ---------- questions ----------

def _confirm_question(state: OnboardingState, name: str) -> str:
    v = state.get(name)
    return _t("confirm_inferred", state.lang, label=_label(name, state.lang), value=v.value, quote=v.quote or "")


def _repeat_question(state: OnboardingState) -> str | None:
    """The question we are waiting on, if it still needs an answer (used after a document upload)."""
    a = state.asking or ""
    if a.startswith(FOLLOWUP):
        i = int(a[len(FOLLOWUP):])
        return f"({i + 1}/{len(state.followups)}) {state.followups[i].question}"
    if a.startswith(CONFIRM) and state.get(a[len(CONFIRM):]).status == "inferred":
        return _confirm_question(state, a[len(CONFIRM):])
    if a.startswith(CONFIRM) and a[len(CONFIRM):] in state.thin:
        return BY_NAME[a[len(CONFIRM):]].ask(state.lang)
    return None


def _next_question(state: OnboardingState, analyst: Analyst) -> str | None:
    for name in REQUIRED:
        if name in state.skipped:
            continue
        if not state.filled(name):
            state.asking = name
            return BY_NAME[name].ask(state.lang)
        if state.get(name).status == "inferred":  # deduced, e.g. country from a city: ask, don't assume
            state.asking = f"{CONFIRM}{name}"
            return _confirm_question(state, name)
        if name in state.recheck:  # the idea changed: does this still hold?
            state.asking = f"{CONFIRM}{name}"
            return _t("recheck", state.lang, label=_label(name, state.lang), value=state.get(name).value)
        if name in state.thin:  # picked up in passing, only a few words: ask, showing what we have
            state.asking = f"{CONFIRM}{name}"
            v = state.get(name)
            head = _t("thin_value", state.lang, label=_label(name, state.lang), value=v.value)
            return head + "\n\n" + BY_NAME[name].ask(state.lang)
    if two_sided(state) and not state.filled("supply_side") and "supply_side" not in state.skipped:
        state.asking = "supply_side"
        return BY_NAME["supply_side"].ask(state.lang)
    optional = [f for f in FIELDS if not f.required and not state.filled(f.name) and f.name not in state.skipped
                and f.name != "supply_side"]
    if optional and not state.optional_offered and not state.followups_ready:
        state.asking = OPTIONAL
        state.optional_offered = True
        return _t("optional", state.lang, names=", ".join(_label(f.name, state.lang) for f in optional))
    if not state.followups_ready:
        _retag(state, analyst)
        founder_qs, research_qs = analyst.questions(_field_values(state), _tag_values(state), state.lang)
        state.followups = [FollowUp(question=q, source=src) for q, src in founder_qs]
        state.open_questions = research_qs
        _log("followup_writer", "write_followup_questions", model=getattr(analyst, "model", None), cost=0,
             followups=len(founder_qs), research_questions=len(research_qs))
        state.followups_ready = True
    for i, fu in enumerate(state.followups):
        if not fu.asked:
            fu.asked = True
            state.asking = f"{FOLLOWUP}{i}"
            head = _t("followup_intro", state.lang) + "\n\n" if i == 0 else ""
            return f"{head}({i + 1}/{len(state.followups)}) {fu.question}"
    state.asking = None
    return None


def _tag_values(state: OnboardingState) -> dict:
    return {k: v.value for k, v in state.tags.items()}


def _advance(state: OnboardingState, analyst: Analyst) -> str:
    q = _next_question(state, analyst)
    if q:
        return q
    state.phase = "confirming"
    return summary(state, analyst)


# ---------- summary ----------

def summary(state: OnboardingState, analyst: Analyst | None = None) -> str:
    _retag(state, analyst or RuleAnalyst())
    _parse_budget(state)
    lang = state.lang
    lines = []
    for f in FIELDS:
        v = state.get(f.name)
        shown = v.value if v.value else _t("unknown", lang)
        if v.status == "inferred":
            tag = f" ({_t('inferred_tag', lang, q=v.quote or '')})"
        elif v.status == "from_document":
            tag = f" ({_t('doc_tag', lang)}: {v.source.split(':', 1)[1]})"
        else:
            tag = ""
        if f.name == "supply_side" and not v.value and not two_sided(state):
            continue
        if f.name == "budget" and state.budget_parsed and format_budget(state.budget_parsed) != v.value:
            tag += f" (= {format_budget(state.budget_parsed)})"
        lines.append(f"- {_label(f.name, lang)}{'*' if f.required else ''}: {shown}{tag}")
    out = _t("summary", lang) + "\n\n" + "\n".join(lines)
    if state.tags:
        out += "\n\n" + _t("tags_head", lang) + "\n" + "\n".join(
            f"- {_label(k, lang)}: {', '.join(v.value) if isinstance(v.value, list) else v.value}"
            for k, v in state.tags.items())
    if state.followups:
        out += "\n\n" + _t("followups_head", lang) + "\n" + "\n".join(
            f"- q{i + 1}. {fu.question} → {fu.answer or _t('unknown', lang)}" for i, fu in enumerate(state.followups))
    if state.open_questions:
        out += "\n\n" + _t("open_head", lang) + "\n" + "\n".join(f"- {q}" for q in state.open_questions)
    check = _product_check(state)
    out += "\n\n" + _t("product_head", lang) + " " + _t(f"product_{check.status}", lang) + " " + check.reason(lang)
    if state.version:
        out += "\n\n" + _t("summary_edit", lang, v=state.version)
    return out


# ---------- parsing founder text ----------

_ALIAS_TO_FIELD = {a.lower(): f.name for f in FIELDS
                   for a in (f.name, _label(f.name), _label(f.name, "ar"), *f.aliases)}


def _field_for_label(label: str) -> str | None:
    key = " ".join(label.lower().split())
    return _ALIAS_TO_FIELD.get(key) or _ALIAS_TO_FIELD.get(key.replace(" ", "_"))


def _tag_for_label(label: str) -> str | None:
    return TAG_LABELS.get("_".join(label.lower().split()))


# A known label followed by ':' '=' or '|' (Word tables), or a follow-up reference like 'q2:', 'q2.', 'q2)'.
# Labels are found anywhere in a line, so 'business model: X budget: Y' typed on one line sets both.
_LABEL_WORDS = set(_ALIAS_TO_FIELD) | set(TAG_LABELS) | {k.replace("_", " ") for k in TAG_LABELS}
LABEL_ANY = re.compile(
    r"(?<!\w)(?:(?P<q>q\s*(?P<qn>\d{1,2}))\s*[:=.)\-]|(?P<label>"
    + "|".join(re.escape(w) for w in sorted(_LABEL_WORDS, key=len, reverse=True))
    + r")\s*[:=|])",
    re.IGNORECASE)


def split_labelled(text: str) -> list[tuple[str, object, str, str]]:
    """[(kind, key, value, quote)] with kind 'field' | 'tag' | 'q'. A value runs to the next label or line end."""
    out = []
    for line in text.splitlines():
        ms = list(LABEL_ANY.finditer(line))
        for i, m in enumerate(ms):
            end = ms[i + 1].start() if i + 1 < len(ms) else len(line)
            value = re.sub(r"\s*\|\s*", ", ", line[m.end():end]).strip(" \t,;،.")
            if not value:
                continue
            quote = line[m.start():end].strip(" \t,;،")
            if m.group("q"):
                out.append(("q", int(m.group("qn")) - 1, value[:1000], quote))
            elif name := _field_for_label(m.group("label")):
                out.append(("field", name, value[:500], quote))
            elif tag := _tag_for_label(m.group("label")):
                out.append(("tag", tag, value, quote))
    return out


def parse_labelled(text: str) -> dict:
    """'budget: 20,000 EGP' or 'الميزانية: 20 ألف' sets that field directly, anywhere in a line. Works with no model."""
    return {key: {"value": value, "quote": quote} for kind, key, value, quote in split_labelled(text)
            if kind == "field"}


def _parse_tag_and_followup_lines(text: str) -> tuple[dict, dict]:
    """Returns ({tag: raw value}, {follow-up index: answer})."""
    parts = split_labelled(text)
    return ({k: v for kind, k, v, _ in parts if kind == "tag"},
            {k: v for kind, k, v, _ in parts if kind == "q"})


_FILLER = re.compile(
    r"^(?:\s*(?:the|my|our|is|are|was|should|be|will|to|from|change|set|update|make|it|actually|please|now|"
    r"هو|هي|إلى|الى|لـ|ل|غير|غيّر|خلي|خليها|خليه|عدل|يكون|تكون|بتاعي|بتاعنا|يبقى|تبقى|بقى)(?=\s|$|[:=,،-])|"
    r"\s*[:=,،-])+",
    re.IGNORECASE)


def _strip_filler(s: str) -> str:
    return _FILLER.sub("", s.strip()).strip(" .،,:-")


def _unlabelled_correction(text: str) -> tuple[list[str], str | None]:
    """Find which field an unlabelled correction names ('change the budget to 30,000 EGP').
    Returns (matching field names, new value or None)."""
    t = text.lower()
    hits: dict[str, str] = {}
    for alias, name in sorted(_ALIAS_TO_FIELD.items(), key=lambda kv: -len(kv[0])):
        if "_" in alias:
            continue
        if T._has(t, alias) and name not in hits:
            hits[name] = alias
    if len(hits) != 1:
        return list(hits), None
    name, alias = next(iter(hits.items()))
    m = re.search(re.escape(alias), t)
    after = _strip_filler(text[m.end():]) if m else ""
    before = _strip_filler(text[:m.start()]) if m else ""
    value = after or before
    return [name], value or None


# ---------- message handling ----------

_SKIP_WORDS = ("skip", "pass", "تخطي", "تخطى")


def _one_edit_apart(a: str, b: str) -> bool:
    """True if a and b differ by at most one inserted, deleted or replaced character."""
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] or a[i + 1:] == b[i:] or a[i:] == b[i + 1:]


def is_skip(text: str) -> bool:
    """'skip', 'لا أعرف'... and one-letter typos of a skip word ('تخطس', 'skp')."""
    if SKIP.match(text):
        return True
    word = text.strip(" .!").lower()
    return " " not in word and any(_one_edit_apart(word, w) for w in _SKIP_WORDS)


def handle_message(state: OnboardingState, text: str, extractor: Extractor, analyst: Analyst | None = None) -> str:
    analyst = analyst or RuleAnalyst()
    text = re.sub(r"(?m)^\s*>\s?", "", text).strip()  # quote markers left over from copy-pasting
    first_answer = all(m.role != "founder" for m in state.messages)
    if first_answer and ARABIC.search(text):
        state.lang = "ar"
    refusal = guardrails.check_request(text)
    text = guardrails.redact(text)  # card numbers and passwords are never stored
    state.messages.append(Message(role="founder", text=text))
    if refusal:  # a must-never request: refuse, change nothing, repeat what we were waiting for
        _log("guardrails", "refuse_request", outcome="refused", rule=refusal.rule)
        return _say(state, refusal.message(state.lang) + "\n\n" + _pending(state, analyst))

    if state.phase == "confirmed":
        if YES.match(text):
            return _say(state, _t("no_change", state.lang, v=state.version))
        state.phase = "confirming"
        state.changed = []
        if EDIT.match(text):
            return _say(state, _t("edit_intro", state.lang, v=state.version) + "\n\n" + summary(state, analyst))
        reply = _correct(state, text, extractor, analyst)
        return _say(state, reply)

    if state.phase == "confirming":
        if YES.match(text):
            return _say(state, _confirm(state, analyst))
        if CANCEL.match(text) and state.saved is not None:
            _restore(state, state.saved)
            _log("founder", "cancel_edit", approved_by="founder", version=state.version)
            return _say(state, _t("cancelled", state.lang, v=state.version))
        return _say(state, _correct(state, text, extractor, analyst))

    # collecting
    if CANCEL.match(text) and state.saved is not None:  # editing a confirmed brief (e.g. after an idea change)
        _restore(state, state.saved)
        _log("founder", "cancel_edit", approved_by="founder", version=state.version)
        return _say(state, _t("cancelled", state.lang, v=state.version))
    if is_skip(text):
        if state.asking == OPTIONAL:
            state.skipped += [f.name for f in FIELDS if not f.required and not state.filled(f.name)]
        elif state.asking and state.asking.startswith(CONFIRM):
            name = state.asking[len(CONFIRM):]
            state.skipped.append(name)  # keeps what we have; an inferred value stays flagged in the summary
            if name in state.thin:
                state.thin.remove(name)
            if name in state.recheck:
                state.recheck.remove(name)
        elif state.asking and not state.asking.startswith(FOLLOWUP):
            state.skipped.append(state.asking)
        return _say(state, _advance(state, analyst))

    if state.asking and state.asking.startswith(CONFIRM):
        _answer_confirm(state, state.asking[len(CONFIRM):], text)
        return _say(state, _advance(state, analyst))

    found = parse_labelled(text)
    asked = state.asking
    # Values the model picks up in passing never replace a field we already have (e.g. a follow-up answer
    # "Pharmacists themselves..." must not overwrite the target customer). Labels ("budget: ...") still do.
    model_found = {k: v for k, v in _extract(extractor, state, text, "founder message").items()
                   if k not in found and (k == asked or not state.filled(k))}
    direct = bool(asked) and asked != OPTIONAL and not asked.startswith(FOLLOWUP)
    other_required = [k for k in model_found if k != asked and BY_NAME[k].required and not state.filled(k)]
    # A paragraph that also describes another descriptive field (idea, problem, customers, skills) is split by
    # the model; an answer that only mentions a country, city or budget in passing is still a focused answer.
    focused = not any(k in THIN_FIELDS for k in other_required)
    if direct and not found and focused and (asked in model_found or not model_found):
        # A focused answer to the question we asked: keep the founder's own words (the model's shorter version
        # can drop details, e.g. "a part-time programmer friend"). Optional fields are not filled from it
        # ("no programmer on the team" is not a technical preference; the optional question comes next anyway);
        # a required one mentioned in passing is kept as inferred and asked about.
        model_found.pop(asked, None)
        found[asked] = {"value": text[:500], "quote": text[:500]}
        model_found = {k: v for k, v in model_found.items() if BY_NAME[k].required}
        for v in model_found.values():
            v["inferred"] = True
    found.update(model_found)
    already = {k for k in model_found if state.filled(k)}
    _, inferred = _apply(state, found, "answered", "chat")
    for k, v in model_found.items():  # required fields picked up in passing with only a few words
        if (k != asked and k in THIN_FIELDS and k not in already and k not in state.thin
                and state.get(k).status == "answered" and len(str(v["value"]).split()) <= 3):
            state.thin.append(k)
    if asked and asked.startswith(FOLLOWUP):
        state.followups[int(asked[len(FOLLOWUP):])].answer = text[:1000]
    elif asked and asked != OPTIONAL and asked not in found and not state.filled(asked) and not found:
        # No model, or the model found nothing: the answer is to the question we asked.
        state.fields[asked] = FieldValue(value=text[:500], status="answered", source="chat", quote=text[:500])
    return _say(state, _inferred_note(state, inferred) + _advance(state, analyst))


_YES_PREFIX = re.compile(r"^\s*(yes|yeah|yep|correct|right|نعم|أيوه|ايوه|أيوة|ايوة|صح|صحيح|مظبوط|مضبوط)\b[\s,.!:-]*",
                         re.IGNORECASE)
_NO_PREFIX = re.compile(r"^\s*(no|nope|not really|wrong|لا|لأ|مش)\b[\s,.!:-]*", re.IGNORECASE)


def _answer_confirm(state: OnboardingState, name: str, text: str) -> None:
    """Reply to 'I assumed X; is that right?' (or 'so far I have X'): yes keeps it, anything else is the value."""
    if name in state.thin:
        state.thin.remove(name)
    if name in state.recheck:
        state.recheck.remove(name)
    v = state.get(name)
    rest = _YES_PREFIX.sub("", text, count=1) if _YES_PREFIX.match(text) else None
    if YES.match(text) or rest == "":
        state.fields[name] = v.model_copy(update={"status": "answered",
                                                  "source": f"{v.source} (inferred, confirmed by founder)"})
        return
    value = rest if rest else (_NO_PREFIX.sub("", text, count=1) or text)
    state.fields[name] = FieldValue(value=value[:500], status="answered", source="chat", quote=text[:500])


def _pending(state: OnboardingState, analyst: Analyst) -> str:
    """What the founder should answer next, without moving the conversation on."""
    if state.phase == "confirmed":
        return _t("confirmed_hint", state.lang, v=state.version)
    if state.phase == "confirming":
        return _t("summary_hint", state.lang)
    if state.asking in BY_NAME:
        return BY_NAME[state.asking].ask(state.lang)
    if state.asking == OPTIONAL:
        missing = [f for f in FIELDS if not f.required and not state.filled(f.name) and f.name not in state.skipped]
        return _t("optional", state.lang, names=", ".join(_label(f.name, state.lang) for f in missing))
    return _repeat_question(state) or _advance(state, analyst)


def already_read(state: OnboardingState, filename: str, analyst: Analyst | None = None) -> str:
    """The same file was uploaded again: say so, don't read it twice, and repeat the pending question."""
    nxt = summary(state, analyst) if state.phase != "collecting" else (
        _repeat_question(state) or (BY_NAME[state.asking].ask(state.lang) if state.asking in BY_NAME else "")
        or _advance(state, analyst or RuleAnalyst()))
    return _say(state, _t("doc_again", state.lang, doc=filename) + "\n\n" + nxt)


def _correct(state: OnboardingState, text: str, extractor: Extractor, analyst: Analyst) -> str:
    """A correction while reviewing the summary (before or after the first confirmation)."""
    tag_lines, answers = _parse_tag_and_followup_lines(text)
    updated: list[str] = []
    for name, raw in tag_lines.items():
        value = T.clean_tag(name, raw)
        if value is None:
            return _t("bad_tag", state.lang, value=raw, name=_label(name, state.lang), allowed=TAG_ALLOWED_TEXT[name])
        state.tags[name] = Tag(value=value, basis="founder")
        if state.version:
            _mark_changed(state, f"tag:{name}")
        updated.append(_label(name, state.lang))
    for i, ans in answers.items():
        if 0 <= i < len(state.followups):
            state.followups[i].answer = ans
            _mark_changed(state, f"q{i + 1}")
            updated.append(f"q{i + 1}")

    found = parse_labelled(text)
    if not found and not updated:
        found = _extract(extractor, state, text, "founder correction")
    if not found and not updated:
        names, value = _unlabelled_correction(text)
        if len(names) == 1 and value:
            found = {names[0]: {"value": value[:500], "quote": text[:500]}}
        elif len(names) > 1:
            labels = [_label(n, state.lang) for n in names]
            return _t("which_of", state.lang, names=", ".join(labels), first=labels[0])
        else:
            return _t("which_line", state.lang)
    old_idea = state.get("idea").value
    if found:
        for name, item in found.items():
            if state.get(name).value != item["value"] or state.get(name).status != "answered":
                _mark_changed(state, name)
            st = "inferred" if item.get("inferred") else "answered"
            state.fields[name] = FieldValue(value=item["value"], status=st, source="chat", quote=item.get("quote"))
            if name in state.skipped:
                state.skipped.remove(name)
            updated.append(_label(name, state.lang))
    if "idea" in found and state.get("idea").value != old_idea:
        return _t("updated", state.lang, names=", ".join(updated)) + "\n\n" + _idea_changed(state, found, analyst)
    return _t("updated", state.lang, names=", ".join(updated)) + "\n\n" + summary(state, analyst)


def _idea_changed(state: OnboardingState, found: dict, analyst: Analyst) -> str:
    """The idea changed in the summary: re-ask what described the old idea and rewrite the follow-ups."""
    state.recheck = [n for n in ("problem", "target_customer") if state.filled(n) and n not in found]
    for n in state.recheck:
        if n in state.skipped:
            state.skipped.remove(n)
    state.followups, state.followups_ready, state.open_questions = [], False, []
    state.tags_stale = True
    state.phase, state.asking = "collecting", None
    _log("brief_analyzer", "idea_changed", recheck=list(state.recheck))
    return _t("idea_changed", state.lang) + "\n\n" + _advance(state, analyst)


def _confirm(state: OnboardingState, analyst: Analyst) -> str:
    _retag(state, analyst)
    _parse_budget(state)
    check = _product_check(state)
    if check.status == "excluded":
        _log("guardrails", "block_confirmation", outcome="excluded", categories=check.categories)
        return _t("cannot_confirm", state.lang) + " " + check.reason(state.lang)
    for f in FIELDS:
        v = state.get(f.name)
        if not state.filled(f.name):
            state.fields[f.name] = FieldValue(status="unknown")
        elif v.status == "inferred":
            # The summary flagged it and the founder said yes: now it is confirmed, but keep where it came from.
            state.fields[f.name] = v.model_copy(update={"status": "answered", "source": f"{v.source} (inferred, "
                                                                                       "confirmed by founder)"})
            _mark_changed(state, f.name)
    if state.version and not state.changed:
        state.phase = "confirmed"
        return _t("no_change", state.lang, v=state.version)
    changed = [_label(c.removeprefix("tag:"), state.lang) for c in state.changed]
    state.last_changes = list(state.changed)
    _log("founder", "confirm_brief", approved_by="founder", version=state.version + 1,
         changed=list(state.changed), product_check=check.status)
    state.version += 1
    state.phase = "confirmed"
    state.saved = state.snapshot()
    state.changed = []
    if state.version == 1:
        return _t("confirmed", state.lang)
    return _t("saved_version", state.lang, v=state.version, names=", ".join(changed))


def _restore(state: OnboardingState, saved: dict) -> None:
    state.fields = {k: FieldValue.model_validate(v) for k, v in saved["fields"].items()}
    state.tags = {k: Tag.model_validate(v) for k, v in saved["tags"].items()}
    state.followups = [FollowUp.model_validate(f) for f in saved["followups"]]
    state.open_questions = list(saved.get("open_questions", []))
    state.product_check = dict(saved.get("product_check", {}))
    state.budget_parsed = saved.get("budget")
    state.recheck, state.thin = [], []
    state.phase = "confirmed"
    state.changed = []
    state.tags_stale = False


def handle_document(state: OnboardingState, filename: str, text: str, extractor: Extractor,
                    analyst: Analyst | None = None) -> str:
    analyst = analyst or RuleAnalyst()
    was_confirmed = state.phase == "confirmed"
    if was_confirmed:  # a new document after confirming starts an edit (if it changes anything)
        state.phase = "confirming"
        state.changed = []
    state.documents.append(filename)
    _log("brief_extractor", "read_document", document=filename)
    injected = guardrails.check_request(text)
    if injected:
        _log("guardrails", "ignore_document_instructions", document=filename, rule=injected.rule)
    state.messages.append(Message(role="system", text=f"Founder uploaded {filename}"))
    found = parse_labelled(text)  # works with no model: lines like "Budget: 40,000 EGP"
    found.update({k: v for k, v in _extract(extractor, state, text, f"uploaded document {filename}").items()
                  if k not in found})
    names, inferred = _apply(state, found, "from_document", f"document:{filename}")
    head = (_t("doc_found", state.lang, doc=filename, names=", ".join(_label(n, state.lang) for n in names))
            if names else _t("doc_none", state.lang, doc=filename))
    if injected:
        head += "\n\n" + _t("doc_instructions", state.lang, doc=filename)
    if was_confirmed and not names:
        state.phase = "confirmed"
        nxt = _t("no_change", state.lang, v=state.version)
    elif state.phase == "confirming":
        nxt = summary(state, analyst)
    else:  # don't skip the question we were waiting on (a follow-up or an "is that right?")
        nxt = _repeat_question(state) or _advance(state, analyst)
    return _say(state, head + "\n\n" + _inferred_note(state, inferred) + nxt)


def brief_markdown(state: OnboardingState, brief_id: str | None = None) -> str:
    """The confirmed brief as Markdown for outputs/phase1_step0_founder_brief.md (written from a real run)."""
    status = {"answered": "founder", "from_document": "founder document", "inferred": "inferred (not confirmed)",
              "unknown": "unknown"}
    lines = [f"# Founder brief (version {state.version})", ""]
    if brief_id:
        lines += [f"Brief id: `{brief_id}`", ""]
    lines += ["Values are the founder's own statements, not verified market facts. Unknown fields stay unknown.", "",
              "| Field | Value | Source |", "|---|---|---|"]
    for f in FIELDS:
        v = state.get(f.name)
        src = status.get(v.status, v.status) + (f" ({v.source})" if v.status == "from_document" else "")
        if "inferred" in v.source and v.status == "answered":
            src = f'inferred from "{v.quote}", confirmed by founder'
        value = (v.value or "unknown").replace("|", "/").replace("\n", " ")
        lines.append(f"| {_label(f.name)}{' *' if f.required else ''} | {value} | {src} |")
    if state.budget_parsed:
        lines += ["", f"**Budget (parsed from the founder's words):** {format_budget(state.budget_parsed)}"]
    check = state.product_check or {}
    lines += ["", f"**Product check:** {check.get('status', 'not run')}"
              + (f" ({', '.join(check.get('categories', []))})" if check.get("categories") else ""), "",
              "## Tags", ""]
    lines += [f"- {_label(k)}: {', '.join(v.value) if isinstance(v.value, list) else v.value} ({v.basis})"
              for k, v in state.tags.items()]
    if state.followups:
        lines += ["", "## Follow-up answers", ""]
        lines += [f"- {fu.question} -> {fu.answer or 'unknown'}" for fu in state.followups]
    if state.open_questions:
        lines += ["", "## Open questions for Discover (not answered yet)", ""]
        lines += [f"- {q}" for q in state.open_questions]
    return "\n".join(lines) + "\n"
