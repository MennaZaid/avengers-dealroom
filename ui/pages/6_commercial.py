"""Phase 4 Commercial setup: price and draft policies (no payments of any kind), ending at the founder's gate.
Uses the stage API only. Steps the Phase 4 agents report as not built are labelled STUBBED. Arabic or English.

render(brief_id, session_id) is also shown inside the pipeline page once Build is approved."""

import streamlit as st
from common import api, setup, ui_lang

L = ui_lang()
i = 1 if L == "ar" else 0
T = {
    "title": ("Phase 4 · Commercial setup", "المرحلة 4: الإعداد التجاري"),
    "sub": ("Price and draft policies (terms, privacy, refunds). No payments of any kind.",
            "التسعير ومسودات السياسات (الشروط، الخصوصية، الاسترداد). لا مدفوعات من أي نوع."),
    "no_brief": ("Confirm a founder brief first.", "أكّد موجز المؤسس أولاً."),
    "brief": ("Brief", "الموجز"), "session": ("Your founder session", "جلسة المؤسس"),
    "start_note": ("Researches sourced prices, sets a price, drafts the policies and checks readiness.",
                   "يبحث عن أسعار موثقة، يحدد سعراً، يكتب مسودات السياسات ويتحقق من الجاهزية."),
    "start": ("▶ Start Commercial setup", "▶ ابدأ الإعداد التجاري"), "again": ("Run again", "أعد التشغيل"),
    "status": ("**Status:** {s} · brief v{v}", "**الحالة:** {s} · الموجز النسخة {v}"),
    "stale": (" · **Stale**: the brief changed, run again", " · **قديم**: تغيّر الموجز، أعد التشغيل"),
    "working": ("Working in the background. Refresh to see progress.", "يعمل في الخلفية. حدّث الصفحة لرؤية التقدم."),
    "refresh": ("Refresh", "تحديث"),
    "stubbed": ("STUBBED (not built yet): {s}", "STUBBED (لم يُبنَ بعد): {s}"),
    "legal": ("Policies are drafts: not legal advice. Review with a qualified lawyer before use.",
              "السياسات مسودات: ليست استشارة قانونية. راجعها مع محامٍ مؤهل قبل الاستخدام."),
    "gate": ("**Commercial gate: {o}** · {r}", "**بوابة الإعداد التجاري: {o}** · {r}"),
    "rule": ("Rule (fixed before the result): {r}", "القاعدة (محددة قبل النتيجة): {r}"),
    "decided": ("{at} · your decision: {d}", "{at} · قرارك: {d}"), "note": ("Note", "ملاحظة"),
    "go": ("Go", "متابعة"), "repeat": ("Repeat", "إعادة"), "pivot": ("Pivot: reshape the idea", "تحويل: إعادة تشكيل الفكرة"),
    "stop": ("Stop", "إيقاف"),
    "approved": ("Commercial setup approved: Phase 5 is next (STUBBED/MOCKED).",
                 "تمت الموافقة على الإعداد التجاري: المرحلة 5 هي التالية (STUBBED/MOCKED)."),
    "need_session": ("Enter your founder session to decide.", "أدخل جلسة المؤسس لاتخاذ القرار."),
}
STATUS = {"queued": ("⏳ queued", "⏳ في الانتظار"), "running": ("⏳ running", "⏳ قيد التشغيل"),
          "awaiting_approval": ("🟡 waiting for your decision", "🟡 بانتظار قرارك"), "approved": ("✅ go", "✅ متابعة"),
          "revision_requested": ("🔁 repeat", "🔁 إعادة"), "pivoted": ("↩️ pivot", "↩️ تحويل"),
          "rejected": ("⛔ stop", "⛔ إيقاف"), "failed": ("❌ failed", "❌ فشل")}
REC = {"go": st.success, "repeat": st.warning, "pivot": st.warning, "stop": st.error}


def t(key, **kw):
    v = T[key][i]
    return v.format(**kw) if kw else v


def _post(path: str, headers: dict | None = None, **body) -> None:
    try:
        api("POST", path, headers=headers or {}, json=body)
        st.rerun()
    except RuntimeError as e:
        st.error(str(e))  # e.g. Build not approved for this brief version


def render(brief_id: str, session_id: str) -> None:
    headers = {"X-Founder-Session": session_id} if session_id else {}
    st.subheader(t("title"))
    runs = api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "commercial"})
    if not runs:
        st.caption(t("start_note"))
        if st.button(t("start"), key=f"c-start-{brief_id}", type="primary"):
            _post("/stages/commercial/runs", brief_id=brief_id)
        return
    run = runs[0]
    c = (run.get("output") or {}).get("commercial") or {}
    s = run["status"]
    st.markdown(t("status", s=STATUS[s][i] if s in STATUS else s, v=run["brief_version"])
                + (t("stale") if run.get("stale") else ""))
    if (s in ("rejected", "revision_requested", "pivoted", "failed") or run.get("stale")) and \
            st.button(t("again"), key=f"c-again-{run['id']}"):
        _post("/stages/commercial/runs", brief_id=brief_id)
    if s == "failed":
        st.error(c.get("error", "failed"))
        return
    if s == "running":
        st.info(t("working"))
        st.button(t("refresh"), key=f"c-refresh-{run['id']}")
        return

    if c.get("stubbed"):
        st.warning(t("stubbed", s=", ".join(c["stubbed"])))
    st.caption(t("legal"))
    for name, text in (c.get("files") or {}).items():
        with st.expander(name, expanded=False):
            st.markdown(text)
    g = c.get("gate")
    if g:
        REC.get(g["outcome"], st.info)(t("gate", o=g["outcome"].upper(), r=g["reason"]))
        st.caption(t("rule", r=g.get("rule")))
    for dec in run.get("decisions") or []:
        st.caption(t("decided", at=dec["created_at"][:19], d=dec["decision"]) + (f": {dec['note']}" if dec["note"] else ""))
    if s == "awaiting_approval" and not run.get("stale"):
        note = st.text_input(t("note"), key=f"cnote-{run['id']}")
        cols = st.columns(4)
        path = f"/stages/runs/{run['id']}/decision"
        if cols[0].button(t("go"), key=f"cgo-{run['id']}", disabled=not session_id):
            _post(path, headers, decision="approve", note=note)
        if cols[1].button(t("repeat"), key=f"crep-{run['id']}", disabled=not session_id):
            _post(path, headers, decision="revise", note=note)
        if cols[2].button(t("pivot"), key=f"cpiv-{run['id']}", disabled=not session_id):
            _post(path, headers, decision="pivot", note=note, pivot_to="onboarding")
        if cols[3].button(t("stop"), key=f"cstop-{run['id']}", disabled=not session_id):
            _post(path, headers, decision="reject", note=note)
        if not session_id:
            st.caption(t("need_session"))
    if s == "approved":
        st.success(t("approved"))


if __name__ == "__main__":  # opened as its own page
    setup(t("title"), t("sub"), lang=L)
    briefs = api("GET", "/stages/briefs")
    if not briefs:
        st.info(t("no_brief"))
        st.stop()
    labels = {b["brief_id"]: f"{(b['idea'] or 'untitled')[:70]} · v{b['version']}" for b in briefs}
    keys = list(labels)
    confirmed = (st.session_state.get("brief") or {}).get("id")
    bid = st.selectbox(t("brief"), keys, format_func=labels.get, index=keys.index(confirmed) if confirmed in keys else 0)
    sid = st.text_input(t("session"), value=st.session_state.get("sid", ""), type="password")
    render(bid, sid)
