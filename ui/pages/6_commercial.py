"""Phase 4 Commercial setup: price and draft policies (no payments of any kind), ending at the founder's gate.
Uses the stage API only. Steps the Phase 4 agents report as not built are labelled STUBBED. Arabic or English.

render(brief_id, session_id, stage) is also used inside the pipeline page for Phase 4 (after Build), Phase 5 Launch
(after Commercial; posting and sale-to-cash MOCKED) and Phase 6 Operate (after Launch)."""

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
# Per-stage text for the phases that share this view: (title, start note, start button, gate label, label line,
# approved line)
STAGE_T = {
    "commercial": {k: T[v] for k, v in (("title", "title"), ("start_note", "start_note"), ("start", "start"),
                                         ("gate", "gate"), ("label", "legal"), ("approved", "approved"))},
    "launch": {
        "title": ("Phase 5 · Sell, deliver, get paid", "المرحلة 5: البيع والتسليم والتحصيل"),
        "start_note": ("Drafts the store page and launch posts, then runs the MOCKED sale-to-cash test.",
                       "يكتب مسودة صفحة المتجر ومنشورات الإطلاق، ثم يشغّل اختبار البيع إلى التحصيل (MOCKED)."),
        "start": ("▶ Start Phase 5", "▶ ابدأ المرحلة 5"),
        "gate": ("**Launch gate: {o}** · {r}", "**بوابة الإطلاق: {o}** · {r}"),
        "label": ("MOCKED: nothing is posted, sold or charged. Posting needs your approval of the exact text.",
                  "MOCKED: لا يُنشر ولا يُباع ولا يُحصّل أي شيء. النشر يحتاج موافقتك على النص نفسه."),
        "approved": ("Phase 5 approved: Phase 6 Operate is next.", "تمت الموافقة على المرحلة 5: التالية هي المرحلة 6."),
    },
    "operate": {
        "title": ("Phase 6 · Operate and learn", "المرحلة 6: التشغيل والتعلّم"),
        "start_note": ("Writes the persevere-or-pivot memo from logged results only.",
                       "يكتب مذكرة الاستمرار أو التحويل من النتائج المسجلة فقط."),
        "start": ("▶ Start Phase 6", "▶ ابدأ المرحلة 6"),
        "gate": ("**Operate gate: {o}** · {r}", "**بوابة التشغيل: {o}** · {r}"),
        "label": ("Built only from logged results; where there is no data yet it says so.",
                  "مبني فقط على النتائج المسجلة؛ وحيث لا توجد بيانات بعد يُذكر ذلك."),
        "approved": ("Phase 6 approved: the last gate is passed.", "تمت الموافقة على المرحلة 6: تم اجتياز آخر بوابة."),
    },
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


APPROVE_T = {
    "head": ("Your approval of the exact test payloads (MOCKED: no money moves)",
             "موافقتك على بيانات الاختبار نفسها (MOCKED: لا تنتقل أي أموال)"),
    "why": (("The sale-to-cash test runs only after you approve these exact payloads. Changing one character needs "
            "a new approval."), ("لا يعمل اختبار البيع إلى التحصيل إلا بعد موافقتك على هذه البيانات نفسها. تغيير حرف "
                               "واحد يحتاج موافقة جديدة.")),
    "approve": ("Approve", "موافقة"), "approved": ("Approved by you", "وافقت عليها"),
    "then": ("After approving both, run Phase 5 again.", "بعد الموافقة على الاثنين، أعد تشغيل المرحلة 5."),
}


def _launch_approvals(brief_id: str, session_id: str, headers: dict) -> None:
    """Phase 5 needs the founder's approval of the exact MOCKED test order and refund before its test can run."""
    items = api("GET", "/stages/launch/approvals", params={"brief_id": brief_id})
    st.markdown(f"**{APPROVE_T['head'][i]}**")
    st.caption(APPROVE_T["why"][i])
    for it in items:
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"`{it['action']}` · {it['label']} · SHA-256 `{it['content_hash'][:16]}…`")
        c1.json(it["payload"], expanded=False)
        if it["approved"]:
            c2.success(APPROVE_T["approved"][i])
        elif c2.button(APPROVE_T["approve"][i], key=f"appr-{it['action']}-{brief_id}", disabled=not session_id):
            _post("/stages/approvals", headers, brief_id=brief_id, action=it["action"],
                  content_hash=it["content_hash"])
    if not all(it["approved"] for it in items):
        st.caption(APPROVE_T["then"][i])


def render(brief_id: str, session_id: str, stage: str = "commercial") -> None:
    def ts(key, **kw):
        v = STAGE_T[stage][key][i]
        return v.format(**kw) if kw else v

    headers = {"X-Founder-Session": session_id} if session_id else {}
    st.subheader(ts("title"))
    runs = api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": stage})
    if stage == "launch":
        _launch_approvals(brief_id, session_id, headers)
    if not runs:
        st.caption(ts("start_note"))
        if st.button(ts("start"), key=f"{stage}-start-{brief_id}", type="primary"):
            _post(f"/stages/{stage}/runs", brief_id=brief_id)
        return
    run = runs[0]
    c = (run.get("output") or {}).get(stage) or {}
    s = run["status"]
    st.markdown(t("status", s=STATUS[s][i] if s in STATUS else s, v=run["brief_version"])
                + (t("stale") if run.get("stale") else ""))
    if (s in ("rejected", "revision_requested", "pivoted", "failed") or run.get("stale")) and \
            st.button(t("again"), key=f"c-again-{run['id']}"):
        _post(f"/stages/{stage}/runs", brief_id=brief_id)
    if s == "failed":
        st.error(c.get("error", "failed"))
        return
    if s == "running":
        st.info(t("working"))
        st.button(t("refresh"), key=f"c-refresh-{run['id']}")
        return

    if c.get("stubbed"):
        st.warning(t("stubbed", s=", ".join(c["stubbed"])))
    st.caption(ts("label"))
    for name, text in (c.get("files") or {}).items():
        with st.expander(name, expanded=False):
            st.markdown(text)
    g = c.get("gate")
    if g:
        REC.get(g["outcome"], st.info)(ts("gate", o=g["outcome"].upper(), r=g["reason"]))
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
        st.success(ts("approved"))


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
