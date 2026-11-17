"""Phase 2 Validate: Lean Canvas -> demand test (declared before measuring) -> landing-page draft (MOCKED) ->
the founder's sign-up count -> demand gate -> the founder's decision. Uses the stage API only. Arabic or English.

render(brief_id, session_id) is also shown inside the pipeline page once Discover is approved."""

import streamlit as st
import streamlit.components.v1 as components
from common import api, setup, ui_lang

L = ui_lang()
i = 1 if L == "ar" else 0
T = {
    "title": ("Phase 2 · Validate", "المرحلة 2: التحقق"),
    "sub": ("Lean Canvas, a demand test fixed before measuring, and a MOCKED landing page.",
            "نموذج العمل المختصر، اختبار طلب محدد قبل القياس، وصفحة هبوط تجريبية (MOCKED)."),
    "no_brief": ("Confirm a founder brief first.", "أكّد موجز المؤسس أولاً."),
    "brief": ("Brief", "الموجز"), "session": ("Your founder session", "جلسة المؤسس"),
    "start_note": ("Builds the Lean Canvas, fixes the demand-test target, then drafts the landing page.",
                   "يبني نموذج العمل المختصر، يثبّت هدف اختبار الطلب، ثم يكتب مسودة صفحة الهبوط."),
    "start": ("▶ Start Validate", "▶ ابدأ التحقق"), "again": ("Run Validate again", "أعد تشغيل التحقق"),
    "status": ("**Status:** {s} · brief v{v}", "**الحالة:** {s} · الموجز النسخة {v}"),
    "stale": (" · **Stale**: the brief changed, run Validate again", " · **قديم**: تغيّر الموجز، أعد تشغيل التحقق"),
    "working": ("Working in the background. This page does not wait; refresh to see progress.",
                "يعمل في الخلفية. هذه الصفحة لا تنتظر؛ حدّثها لرؤية التقدم."),
    "refresh": ("Refresh", "تحديث"), "failed": ("failed", "فشل"),
    "canvas": ("Lean Canvas (entries without evidence are labelled ASSUMPTION)",
               "نموذج العمل المختصر (البنود بلا دليل موسومة ASSUMPTION)"),
    "test": ("**Demand test (set before measuring):** {n} {m} in {d} days · declared {at}",
             "**اختبار الطلب (محدد قبل القياس):** {n} {m} خلال {d} يوماً · أُعلن في {at}"),
    "draft": ("Landing-page draft · MOCKED: not published", "مسودة صفحة الهبوط · MOCKED: غير منشورة"),
    "mocked": ("MOCKED: this draft is not published anywhere. Publishing needs your separate approval.",
               "MOCKED: هذه المسودة غير منشورة في أي مكان. النشر يحتاج موافقتك المنفصلة."),
    "signups": ("Waitlist sign-ups (entered by the founder)", "التسجيلات في قائمة الانتظار (يُدخلها المؤسس)"),
    "days": ("Days since the test started", "الأيام منذ بدء الاختبار"),
    "send": ("Send to the demand gate", "أرسل إلى بوابة الطلب"),
    "both": ("Enter both numbers: the count is never filled in for you.",
             "أدخل الرقمين: لا يُملأ العدد نيابةً عنك أبداً."),
    "need_session": ("Enter your founder session to send the count and decide.",
                     "أدخل جلسة المؤسس لإرسال العدد واتخاذ القرار."),
    "gate": ("**Demand gate: {o}** · target {t:g} · actual {a:g} (founder-reported) · {r}",
             "**بوابة الطلب: {o}** · الهدف {t:g} · الفعلي {a:g} (أبلغ عنه المؤسس) · {r}"),
    "rule": ("Rule (fixed before the result): {r}", "القاعدة (محددة قبل النتيجة): {r}"),
    "decided": ("{at} · your decision: {d}", "{at} · قرارك: {d}"), "note": ("Note", "ملاحظة"),
    "go": ("Go: continue to Build", "متابعة: إلى البناء"), "repeat": ("Repeat: run the test again", "إعادة الاختبار"),
    "stop": ("Stop", "إيقاف"),
    "approved": ("Validate approved: Phase 3 Build can start.", "تمت الموافقة على التحقق: يمكن بدء المرحلة 3 (البناء)."),
    "to_build": ("Go to Build →", "← الانتقال إلى البناء"),
}
STAGE_STATUS = {"queued": ("⏳ queued", "⏳ في الانتظار"),
                "lean_canvas": ("⏳ building the Lean Canvas", "⏳ جارٍ بناء نموذج العمل"),
                "landing_page": ("⏳ declaring the demand test and drafting the landing page",
                                 "⏳ إعلان اختبار الطلب وكتابة مسودة صفحة الهبوط"),
                "awaiting_signups": ("🟡 waiting for your sign-up count", "🟡 بانتظار عدد التسجيلات منك"),
                "gated": ("🟡 waiting for your decision", "🟡 بانتظار قرارك"), "failed": ("❌ failed", "❌ فشل"),
                "approved": ("✅ go", "✅ متابعة"), "rejected": ("⛔ stop", "⛔ إيقاف"),
                "revision_requested": ("🔁 repeat", "🔁 إعادة"), "pivoted": ("↩️ pivot", "↩️ تحويل")}
CLOSED = ("approved", "rejected", "pivoted", "revision_requested", "failed")
REC = {"go": st.success, "repeat": st.warning, "pivot": st.warning, "stop": st.error}


def t(key, **kw):
    v = T[key][i]
    return v.format(**kw) if kw else v


def _decide(run_id: str, decision: str, headers: dict, note: str) -> None:
    try:
        api("POST", f"/stages/runs/{run_id}/decision", headers=headers, json={"decision": decision, "note": note})
        st.rerun()
    except RuntimeError as e:
        st.error(str(e))


def _start(brief_id: str) -> None:
    try:
        api("POST", "/stages/validate/runs", json={"brief_id": brief_id})
        st.rerun()
    except RuntimeError as e:
        st.error(str(e))  # e.g. Discover not approved for this brief version


def render(brief_id: str, session_id: str) -> None:
    headers = {"X-Founder-Session": session_id} if session_id else {}
    st.subheader(t("title"))
    runs = api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "validate"})
    if not runs:
        st.caption(t("start_note"))
        if st.button(t("start"), key=f"start-{brief_id}", type="primary"):
            _start(brief_id)
        return
    run = runs[0]
    v = (run.get("output") or {}).get("validate") or {}
    state = run["status"] if run["status"] in CLOSED else v.get("status", run["status"])
    label = STAGE_STATUS[state][i] if state in STAGE_STATUS else state
    st.markdown(t("status", s=label, v=run["brief_version"]) + (t("stale") if run.get("stale") else ""))
    again = state in ("rejected", "revision_requested", "pivoted", "failed") or run.get("stale")
    if again and st.button(t("again"), key=f"again-{run['id']}"):
        _start(brief_id)
    if state == "failed":
        st.error(v.get("error", t("failed")))
        return
    if state in ("queued", "lean_canvas", "landing_page"):
        st.info(t("working"))
        st.button(t("refresh"), key=f"refresh-{run['id']}")
        return

    with st.expander(t("canvas"), expanded=False):
        st.markdown(v.get("canvas_md") or "")
    d = v.get("demand_test") or {}
    st.markdown(t("test", n=d.get("target"), m=d.get("metric"), d=d.get("days"), at=d.get("declared_at")))
    with st.expander(t("draft"), expanded=False):
        st.warning(t("mocked"))
        components.html(v.get("draft_html") or "", height=520, scrolling=True)

    if run["status"] in ("running", "awaiting_approval") and not run.get("stale"):
        with st.form(f"signups-{run['id']}"):
            c1, c2 = st.columns(2)
            actual = c1.number_input(t("signups"), min_value=0, step=1, value=None)
            days = c2.number_input(t("days"), min_value=0, step=1, value=None)
            if st.form_submit_button(t("send"), disabled=not session_id):
                if actual is None or days is None:
                    st.error(t("both"))
                else:
                    try:
                        api("POST", f"/stages/runs/{run['id']}/signups", headers=headers,
                            json={"actual": int(actual), "days_elapsed": int(days)})
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))
        if not session_id:
            st.caption(t("need_session"))

    g = v.get("gate")
    if g:
        REC.get(g["outcome"], st.info)(t("gate", o=g["outcome"].upper(), t=g.get("target") or 0,
                                         a=g.get("actual") or 0, r=g["reason"]))
        st.caption(t("rule", r=g.get("rule")))
    for dec in run.get("decisions") or []:
        st.caption(t("decided", at=dec["created_at"][:19], d=dec["decision"]) + (f": {dec['note']}" if dec["note"] else ""))
    if run["status"] == "awaiting_approval" and not run.get("stale"):
        note = st.text_input(t("note"), key=f"vnote-{run['id']}")
        c1, c2, c3 = st.columns(3)
        if c1.button(t("go"), key=f"vgo-{run['id']}", disabled=not session_id):
            _decide(run["id"], "approve", headers, note)
        if c2.button(t("repeat"), key=f"vrep-{run['id']}", disabled=not session_id):
            _decide(run["id"], "revise", headers, note)
        if c3.button(t("stop"), key=f"vstop-{run['id']}", disabled=not session_id):
            _decide(run["id"], "reject", headers, note)
    if run["status"] == "approved":
        st.success(t("approved"))
        st.page_link("pages/5_build.py", label=t("to_build"))


if __name__ == "__main__":  # opened as its own page
    setup(t("title"), t("sub"), lang=L)
    briefs = api("GET", "/stages/briefs")
    if not briefs:
        st.info(t("no_brief"))
        st.stop()
    labels = {b["brief_id"]: f"{(b['idea'] or 'untitled')[:70]} · v{b['version']}" for b in briefs}
    bid = (st.session_state.get("brief") or {}).get("id")
    if bid not in labels:  # only the brief the founder confirmed in this session; never a stored or sample brief
        st.info(t("no_brief"))
        st.page_link("pages/1_onboarding.py", label="→ " + t("brief"))
        st.stop()
    st.markdown(f"**{t('brief')}:** {labels[bid]}")
    sid = st.text_input(t("session"), value=st.session_state.get("sid", ""), type="password")
    render(bid, sid)
