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

import re

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

ARABIC = re.compile(r"[؀-ۿ]")
SKIP = re.compile(r"^\s*(skip|pass|don'?t know|i don'?t know|not sure|n/?a|تخطي|تخطى|لا أعرف|لا اعرف|مش عارف)\s*[.!]?\s*$",
                  re.IGNORECASE)
YES = re.compile(r"^\s*(yes|y|confirm|correct|ok|okay|looks good|save|نعم|أكد|اكد|صحيح|تمام|موافق|احفظ)\s*[.!]?\s*$",
                 re.IGNORECASE)
EDIT = re.compile(r"^\s*(edit|change|update|modify|edit brief|تعديل|عدل|تغيير|عايز اغير|عايز أغير)\s*[.!]?\s*$",
                  re.IGNORECASE)
CANCEL = re.compile(r"^\s*(cancel|undo|keep it|never ?mind|إلغاء|الغاء|خلاص|سيبه)\s*[.!]?\s*$", re.IGNORECASE)

OPTIONAL = "__optional__"
FOLLOWUP = "__followup__:"
CONFIRM = "__confirm__:"

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
    "doc_again": {
        "en": "I already read {doc}, so I didn't read it again.",
        "ar": "قرأت {doc} من قبل، لذلك لم أقرأه مرة أخرى.",
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
        if name in state.thin:  # picked up in passing, only a few words: ask, showing what we have
            state.asking = f"{CONFIRM}{name}"
            v = state.get(name)
            head = _t("thin_value", state.lang, label=_label(name, state.lang), value=v.value)
            return head + "\n\n" + BY_NAME[name].ask(state.lang)
    optional = [f for f in FIELDS if not f.required and not state.filled(f.name) and f.name not in state.skipped]
    if optional and state.asking != OPTIONAL and not state.followups_ready:
        state.asking = OPTIONAL
        return _t("optional", state.lang, names=", ".join(_label(f.name, state.lang) for f in optional))
    if not state.followups_ready:
        _retag(state, analyst)
        founder_qs, research_qs = analyst.questions(_field_values(state), _tag_values(state), state.lang)
        state.followups = [FollowUp(question=q, source=src) for q, src in founder_qs]
        state.open_questions = research_qs
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
    r"هو|هي|إلى|الى|غير|غيّر|خلي|خليها|خليه|عدل|يكون|تكون|بتاعي|بتاعنا|يبقى|تبقى|بقى)(?=\s|$|[:=,،-])|\s*[:=,،-])+",
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

def handle_message(state: OnboardingState, text: str, extractor: Extractor, analyst: Analyst | None = None) -> str:
    analyst = analyst or RuleAnalyst()
    text = text.strip()
    first_answer = all(m.role != "founder" for m in state.messages)
    if first_answer and ARABIC.search(text):
        state.lang = "ar"
    state.messages.append(Message(role="founder", text=text))

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
            return _say(state, _t("cancelled", state.lang, v=state.version))
        return _say(state, _correct(state, text, extractor, analyst))

    # collecting
    if SKIP.match(text):
        if state.asking == OPTIONAL:
            state.skipped += [f.name for f in FIELDS if not f.required and not state.filled(f.name)]
        elif state.asking and state.asking.startswith(CONFIRM):
            name = state.asking[len(CONFIRM):]
            state.skipped.append(name)  # keeps what we have; an inferred value stays flagged in the summary
            if name in state.thin:
                state.thin.remove(name)
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
    model_found = {k: v for k, v in extractor.extract(text, kind=_kind(state, "founder message")).items()
                   if k not in found and (k == asked or not state.filled(k))}
    direct = bool(asked) and asked != OPTIONAL and not asked.startswith(FOLLOWUP)
    other_required = [k for k in model_found if k != asked and BY_NAME[k].required and not state.filled(k)]
    if direct and not found and not other_required and (asked in model_found or not model_found):
        # A focused answer to the question we asked: keep the founder's own words (the model's shorter version
        # can drop details, e.g. "a part-time programmer friend"). The model only fills *other* fields, and
        # optional ones picked up from an answer to a different question are flagged for the founder to check.
        model_found.pop(asked, None)
        found[asked] = {"value": text[:500], "quote": text[:500]}
        for v in model_found.values():
            v["inferred"] = True
    found.update(model_found)
    already = {k for k in model_found if state.filled(k)}
    _, inferred = _apply(state, found, "answered", "chat")
    for k, v in model_found.items():  # required fields picked up in passing with only a few words
        if (k != asked and BY_NAME[k].required and k not in already and k not in state.thin
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
    v = state.get(name)
    rest = _YES_PREFIX.sub("", text, count=1) if _YES_PREFIX.match(text) else None
    if YES.match(text) or rest == "":
        state.fields[name] = v.model_copy(update={"status": "answered",
                                                  "source": f"{v.source} (inferred, confirmed by founder)"})
        return
    value = rest if rest else (_NO_PREFIX.sub("", text, count=1) or text)
    state.fields[name] = FieldValue(value=value[:500], status="answered", source="chat", quote=text[:500])


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
        found = extractor.extract(text, kind=_kind(state, "founder correction"))
    if not found and not updated:
        names, value = _unlabelled_correction(text)
        if len(names) == 1 and value:
            found = {names[0]: {"value": value[:500], "quote": text[:500]}}
        elif len(names) > 1:
            labels = [_label(n, state.lang) for n in names]
            return _t("which_of", state.lang, names=", ".join(labels), first=labels[0])
        else:
            return _t("which_line", state.lang)
    if found:
        for name, item in found.items():
            if state.get(name).value != item["value"] or state.get(name).status != "answered":
                _mark_changed(state, name)
            st = "inferred" if item.get("inferred") else "answered"
            state.fields[name] = FieldValue(value=item["value"], status=st, source="chat", quote=item.get("quote"))
            if name in state.skipped:
                state.skipped.remove(name)
            updated.append(_label(name, state.lang))
    return _t("updated", state.lang, names=", ".join(updated)) + "\n\n" + summary(state, analyst)


def _confirm(state: OnboardingState, analyst: Analyst) -> str:
    _retag(state, analyst)
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
    state.phase = "confirmed"
    state.changed = []
    state.tags_stale = False


def handle_document(state: OnboardingState, filename: str, text: str, extractor: Extractor,
                    analyst: Analyst | None = None) -> str:
    analyst = analyst or RuleAnalyst()
    if state.phase == "confirmed":  # a new document after confirming starts an edit
        state.phase = "confirming"
        state.changed = []
    state.documents.append(filename)
    state.messages.append(Message(role="system", text=f"Founder uploaded {filename}"))
    found = parse_labelled(text)  # works with no model: lines like "Budget: 40,000 EGP"
    found.update({k: v for k, v in extractor.extract(text, kind=_kind(state, f"uploaded document {filename}")).items()
                  if k not in found})
    names, inferred = _apply(state, found, "from_document", f"document:{filename}")
    head = (_t("doc_found", state.lang, doc=filename, names=", ".join(_label(n, state.lang) for n in names))
            if names else _t("doc_none", state.lang, doc=filename))
    if state.phase == "confirming":
        nxt = summary(state, analyst)
    else:  # don't skip the question we were waiting on (a follow-up or an "is that right?")
        nxt = _repeat_question(state) or _advance(state, analyst)
    return _say(state, head + "\n\n" + _inferred_note(state, inferred) + nxt)
