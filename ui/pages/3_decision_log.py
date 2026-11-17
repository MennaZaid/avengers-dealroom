"""Decision log and outputs for THIS conversation only, as recorded by the pipeline.

Entries come from the API (GET /onboarding/sessions/{id}/log), filtered by this session's id and, once the
brief is confirmed, its brief id (later stages log under it). Other sessions and test runs are never shown.
"""

import json

import streamlit as st
from common import api, setup, ui_lang

T = {
    "title": ("Decision log & outputs", "سجل القرارات والمخرجات"),
    "sub": ("Every agent action and founder approval in this session, as recorded by the pipeline.",
            "كل إجراء قام به الوكلاء وكل موافقة من المؤسس في هذه الجلسة، كما سجّلها النظام."),
    "no_session": (("No session yet. Start a founder brief on the onboarding page; this page then shows only that "
                   "session's actions."),
                   "لا توجد جلسة بعد. ابدأ موجز المؤسس في صفحة الإعداد؛ ستعرض هذه الصفحة إجراءات تلك الجلسة فقط."),
    "unavailable": ("Decision log unavailable: {e}", "سجل القرارات غير متاح: {e}"),
    "session": ("Session", "الجلسة"), "brief": ("brief", "الموجز"),
    "actions": ("Actions logged", "الإجراءات المسجلة"), "model_calls": ("Model calls", "استدعاءات النموذج"),
    "approvals": ("Founder approvals", "موافقات المؤسس"), "cost": ("Cost (USD)", "التكلفة (دولار)"),
    "tab_log": ("Decision log", "سجل القرارات"), "tab_out": ("Outputs", "المخرجات"),
    "no_entries": ("No actions logged in this session yet.", "لم تُسجل أي إجراءات في هذه الجلسة بعد."),
    "agent": ("Agent", "الوكيل"), "raw": ("Raw JSON", "JSON الخام"),
    "no_outputs": ("No outputs for this session yet. Confirming the brief writes the first one.",
                   "لا توجد مخرجات لهذه الجلسة بعد. تأكيد الموجز يكتب أول ملف."),
    "file": ("File", "الملف"),
    "cols": (("time", "agent", "action", "model", "approved by", "outcome", "sources"),
             ("الوقت", "الوكيل", "الإجراء", "النموذج", "وافق عليه", "النتيجة", "المصادر")),
}
lang = ui_lang()
i = 1 if lang == "ar" else 0


def t(key: str, **kw):
    v = T[key][i]
    return v.format(**kw) if isinstance(v, str) else v


setup(t("title"), t("sub"), lang=lang)

sid = st.session_state.get("sid")
if not sid:
    st.info(t("no_session"))
    st.stop()

try:
    entries = api("GET", f"/onboarding/sessions/{sid}/log")
    outputs = api("GET", f"/onboarding/sessions/{sid}/outputs")
except RuntimeError as e:
    st.error(t("unavailable", e=e))
    st.stop()

brief_id = (st.session_state.get("last") or {}).get("brief_id")
st.caption(f"{t('session')} `{sid}`" + (f" · {t('brief')} `{brief_id}`" if brief_id else ""))

m1, m2, m3, m4 = st.columns(4)
m1.metric(t("actions"), len(entries))
m2.metric(t("model_calls"), sum(1 for e in entries if e.get("model")))
m3.metric(t("approvals"), sum(1 for e in entries if e.get("approved_by") == "founder"))
m4.metric(t("cost"), f"${sum(float(e.get('cost') or 0) for e in entries):.2f}")

tab_log, tab_out = st.tabs([t("tab_log"), t("tab_out")])
with tab_log:
    if not entries:
        st.info(t("no_entries"))
    else:
        agents = sorted({e["agent"] for e in entries})
        pick = st.multiselect(t("agent"), agents, default=agents)
        c = t("cols")
        rows = [{c[0]: e["timestamp"], c[1]: e["agent"], c[2]: e["action"], c[3]: e.get("model") or "—",
                 c[4]: e.get("approved_by") or "—", c[5]: e.get("outcome") or "",
                 c[6]: len(e.get("sources") or [])} for e in reversed(entries) if e["agent"] in pick]
        st.dataframe(rows, hide_index=True, width="stretch")
        with st.expander(t("raw")):
            st.json(entries[-20:])

with tab_out:
    if not outputs:
        st.info(t("no_outputs"))
    else:
        names = [o["name"] for o in outputs]
        name = st.selectbox(t("file"), names)
        text = outputs[names.index(name)]["text"]
        if name.endswith(".md"):
            st.markdown(text)
        elif name.endswith(".json"):
            st.json(json.loads(text))
        else:
            st.code(text)
