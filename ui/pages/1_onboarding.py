"""Founder onboarding: chat on the left, the brief as cards on the right."""

import streamlit as st
from common import api, card, chip, esc, setup, ui_lang

from venture_os.onboarding.brief import FIELDS, label

T = {
    "title": {"en": "Founder brief", "ar": "موجز المؤسس"},
    "sub": {"en": "Tell us about your idea. Nothing starts until you confirm.",
            "ar": "حدّثنا عن فكرتك. لن يبدأ أي شيء قبل تأكيدك."},
    "input": {"en": "Type your answer… (English or Arabic)", "ar": "اكتب إجابتك… (عربي أو إنجليزي)"},
    "attach": {"en": "📎 Attach a document", "ar": "📎 إرفاق مستند"},
    "read": {"en": "Read this document", "ar": "اقرأ المستند"},
    "upload_help": {"en": "Pitch deck, notes or plan (PDF, Word, .txt, .md)",
                    "ar": "عرض تقديمي أو ملاحظات أو خطة (PDF أو Word أو نص)"},
    "required": {"en": "Required", "ar": "مطلوب"},
    "optional": {"en": "Optional", "ar": "اختياري"},
    "progress": {"en": "{n} of {t} required answers", "ar": "{n} من {t} إجابات مطلوبة"},
    "tags": {"en": "Tags (choose research sources)", "ar": "التصنيفات (لاختيار مصادر البحث)"},
    "followups": {"en": "Follow-up questions", "ar": "أسئلة المتابعة"},
    "research": {"en": "Open questions for research", "ar": "أسئلة مفتوحة للبحث"},
    "research_help": {"en": "Discover will look for these; you don't need to answer them.",
                      "ar": "ستبحث مرحلة الاكتشاف عنها، ولا تحتاج للإجابة عليها."},
    "docs": {"en": "Documents read", "ar": "المستندات المقروءة"},
    "confirm": {"en": "✅ Confirm brief", "ar": "✅ تأكيد الموجز"},
    "keep": {"en": "Keep editing", "ar": "متابعة التعديل"},
    "review": {"en": "Review the brief panel, then confirm or type a correction.",
               "ar": "راجع لوحة الموجز، ثم أكّده أو اكتب تصحيحاً."},
    "excluded": {"en": "Product check: not allowed ({cats}). Only digital products; no physical goods, "
                       "financial/crypto, or health/legal advice. The brief can't be confirmed until the idea changes.",
                 "ar": "فحص المنتج: غير مسموح ({cats}). المنتجات الرقمية فقط؛ لا سلع مادية ولا منتجات مالية أو "
                       "عملات رقمية ولا نصائح صحية أو قانونية. لا يمكن تأكيد الموجز حتى تتغير الفكرة."},
    "review_product": {"en": "Product check: allowed only if the product is digital and gives no medical, legal or "
                             "financial advice.",
                       "ar": "فحص المنتج: مسموح فقط إذا كان المنتج رقمياً ولا يقدم نصائح طبية أو قانونية أو مالية."},
    "allowed": {"en": "Product check: ✅ digital product, allowed", "ar": "فحص المنتج: ✅ منتج رقمي، مسموح"},
    "api_down": {"en": "Cannot reach the API: {e}", "ar": "تعذّر الوصول إلى الخادم: {e}"},
    "confirmed": {"en": "Brief confirmed · version {v}", "ar": "تم تأكيد الموجز · النسخة {v}"},
    "edit": {"en": "✏️ Edit brief", "ar": "✏️ تعديل الموجز"},
    "to_pipeline": {"en": "Go to the pipeline →", "ar": "← الانتقال إلى المراحل"},
    "unsaved": {"en": "Editing: changes are saved only when you confirm ('cancel' keeps version {v}).",
                "ar": "تعديل: لن تُحفظ التغييرات إلا بعد التأكيد ('إلغاء' يبقي النسخة {v})."},
    "restart": {"en": "↺ Start over", "ar": "↺ البدء من جديد"},
    "not_answered": {"en": "not answered", "ar": "لم تتم الإجابة"},
}
CATEGORIES = {
    "physical_goods": {"en": "physical goods", "ar": "سلع مادية"},
    "financial": {"en": "financial/crypto", "ar": "منتج مالي أو عملات رقمية"},
    "health_advice": {"en": "health advice", "ar": "نصائح صحية"},
    "legal_advice": {"en": "legal advice", "ar": "نصائح قانونية"},
}
STATUS = {
    "answered": {"en": "answered", "ar": "تمت الإجابة"},
    "from_document": {"en": "from document", "ar": "من المستند"},
    "inferred": {"en": "inferred · check", "ar": "مُستنتج · راجِع"},
    "unknown": {"en": "unknown", "ar": "غير معروف"},
}


def t(key: str, lang: str, **kw) -> str:
    return T[key][lang].format(**kw)


def start_session() -> None:
    choice = st.session_state.get("ui_lang_choice", "auto")
    out = api("POST", "/onboarding/sessions", json={"lang": "ar" if choice == "ar" else "en"})
    st.session_state.sid = out["session_id"]
    st.session_state.chat = [("assistant", out["reply"])]
    st.session_state.last = out


def send(text: str) -> None:
    try:
        out = api("POST", f"/onboarding/sessions/{st.session_state.sid}/messages", json={"text": text})
        st.session_state.chat += [("user", text), ("assistant", out["reply"])]
        st.session_state.last = out
    except RuntimeError as e:
        st.session_state.chat += [("user", text), ("system", f"Error: {e}")]
    st.rerun()


if "sid" not in st.session_state:
    try:
        start_session()
    except Exception as e:  # noqa: BLE001
        st.error(t("api_down", ui_lang(), e=e))
        st.stop()

founder_spoke = any(role == "user" for role, _ in st.session_state.chat)
choice = st.session_state.get("ui_lang_choice", "auto")
if not founder_spoke and choice in ("en", "ar") and st.session_state.last.get("lang") != choice:
    start_session()  # greeting in the language the founder just picked
last = st.session_state.last
lang = ui_lang()  # interface language: sidebar choice, else the conversation's language
talk = last.get("lang", "en")  # the conversation's language (words sent to the bot)
st.session_state.model_label = "Model: " + str(last.get("model", ""))
st.session_state.brief = {"id": last.get("brief_id"), "version": last.get("version"), "phase": last["phase"]}
setup(t("title", lang), t("sub", lang), active_phase=0, lang=lang)

chat_col, brief_col = st.columns([3, 2], gap="large")

# ---------------- chat ----------------
with chat_col:
    box = st.container(height=560, border=True)
    with box:
        for role, text in st.session_state.chat:
            if role == "system":
                st.caption(text)
            else:
                with st.chat_message("assistant" if role == "assistant" else "user",
                                     avatar="🧭" if role == "assistant" else "👤"):
                    st.markdown(text)

    phase = last["phase"]
    if phase == "confirming":
        st.info(t("review", lang))
        c1, c2 = st.columns(2)
        if c1.button(t("confirm", lang), type="primary", use_container_width=True):
            send("نعم" if talk == "ar" else "yes")
    elif phase == "confirmed":
        st.success(t("confirmed", lang, v=last.get("version", 1)))
        c1, c2 = st.columns(2)
        c1.page_link("pages/2_pipeline.py", label=t("to_pipeline", lang))
        if c2.button(t("edit", lang), use_container_width=True):
            send("تعديل" if talk == "ar" else "edit")
    if last.get("unsaved_changes"):
        st.warning(t("unsaved", lang, v=last.get("version", 0)))

    with st.popover(t("attach", lang), use_container_width=False):
        up = st.file_uploader(t("upload_help", lang), type=["pdf", "docx", "txt", "md"],
                              label_visibility="visible")
        if up is not None and st.button(t("read", lang), type="primary"):
            try:
                out = api("POST", f"/onboarding/sessions/{st.session_state.sid}/documents",
                          files={"file": (up.name, up.getvalue())})
                st.session_state.chat += [("system", f"📄 {up.name}"), ("assistant", out["reply"])]
                st.session_state.last = out
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))

    prompt = st.chat_input(t("input", lang))
    if prompt:
        send(prompt)

# ---------------- brief ----------------
with brief_col:
    fields = last.get("fields", {})
    req = [f for f in FIELDS if f.required]
    done = sum(1 for f in req if fields.get(f.name, {}).get("status") in ("answered", "from_document", "inferred"))
    st.progress(done / len(req), text=t("progress", lang, n=done, t=len(req)))

    check = last.get("product_check") or {}
    if check.get("status") == "excluded":
        cats = "، ".join(CATEGORIES.get(c, {}).get(lang, c) for c in check.get("categories", []))
        st.error(t("excluded", lang, cats=cats))
    elif check.get("status") == "review":
        st.warning(t("review_product", lang))
    elif check.get("status") == "allowed":
        st.caption(t("allowed", lang))

    def render(group: list) -> None:
        html_cards = []
        for f in group:
            v = fields.get(f.name, {})
            status = v.get("status", "unknown")
            html_cards.append(card(label(f.name, lang), v.get("value"),
                                   chip(STATUS.get(status, STATUS["unknown"])[lang], status), lang))
        st.markdown("".join(html_cards), unsafe_allow_html=True)

    tab_req, tab_opt, tab_more = st.tabs([t("required", lang), t("optional", lang), "···"])
    with tab_req:
        render(req)
    with tab_opt:
        render([f for f in FIELDS if not f.required])
    with tab_more:
        tags = last.get("tags", {})
        if tags:
            st.markdown(f'<div class="vos-section">{esc(t("tags", lang))}</div>', unsafe_allow_html=True)
            chips = []
            for k, v in tags.items():
                val = ", ".join(v["value"]) if isinstance(v["value"], list) else v["value"]
                chips.append(chip(f"{label(k, lang)}: {val}", "tag"))
            st.markdown("".join(chips), unsafe_allow_html=True)
        fups = last.get("followups", [])
        if fups:
            st.markdown(f'<div class="vos-section">{esc(t("followups", lang))}</div>', unsafe_allow_html=True)
            for i, f in enumerate(fups, 1):
                st.markdown(card(f"q{i}. {f['question']}", f.get("answer") or t("not_answered", lang), "", lang),
                            unsafe_allow_html=True)
        if last.get("open_questions"):
            st.markdown(f'<div class="vos-section">{esc(t("research", lang))}</div>', unsafe_allow_html=True)
            st.caption(t("research_help", lang))
            for q in last["open_questions"]:
                st.markdown(f"- {q}")
        if last.get("documents"):
            st.markdown(f'<div class="vos-section">{esc(t("docs", lang))}</div>', unsafe_allow_html=True)
            for d in last["documents"]:
                st.markdown(f"📄 {d}")
    if st.button(t("restart", lang)):
        start_session()
        st.rerun()
