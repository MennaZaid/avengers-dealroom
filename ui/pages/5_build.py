"""Phase 3 Build: continues from the founder's approved Discover; runs all agents with no approval inside the
stage; ends at the build gate, where the founder decides once (Go / Repeat / Stop). Arabic or English."""

import time

import streamlit as st
import streamlit.components.v1 as components
from common import API, api, phase_bar, setup, ui_lang

L = ui_lang()
T = {
    "title": ("Pipeline · Phase 3 Build", "المراحل · المرحلة 3: البناء"),
    "sub": ("From validated evidence to a tested MVP. One founder decision at the end.",
            "من الأدلة المُتحقق منها إلى نموذج أولي مُختبر. قرار واحد من المؤسس في النهاية."),
    "how": (("Agents: build inputs → requirements → MVP plan → validation → MVP → tests → docs. Nobody approves inside "
            "the stage; the founder decides once at the build gate. Nothing is published, sent or spent."),
            ("الوكلاء: مدخلات البناء ← المتطلبات ← خطة النموذج ← التحقق ← النموذج ← الاختبارات ← الوثائق. لا موافقات "
            "داخل المرحلة؛ يقرر المؤسس مرة واحدة عند بوابة البناء. لا يُنشر ولا يُرسل ولا يُنفق أي شيء.")),
    "api_down": ("Cannot reach the API at {api}: {e}", "تعذّر الوصول إلى الخادم {api}: {e}"),
    "no_brief": ("No confirmed brief yet. Confirm one on the onboarding page first.",
                 "لا يوجد موجز مؤكد بعد. أكّد موجزاً في صفحة الإعداد أولاً."),
    "brief": ("Brief", "الموجز"),
    "session": ("Your founder session (from the onboarding page; needed to decide)",
                "جلسة المؤسس (من صفحة الإعداد؛ مطلوبة لاتخاذ القرار)"),
    "from_p1": ("From Phase 1 (Discover)", "من المرحلة 1 (الاكتشاف)"),
    "p1_none": ("Build starts after you approve Phase 2 (Validate) for brief v{v}.",
                "يبدأ البناء بعد موافقتك على المرحلة 2 (التحقق) للموجز النسخة {v}."),
    "to_p1": ("Go to the Pipeline page (Validate) →", "← الانتقال إلى صفحة المراحل (التحقق)"),
    "p1_rec": ("Discover recommended **{rec}**; you decided **{dec}**", "أوصى الاكتشاف بـ **{rec}**؛ وقرارك: **{dec}**"),
    "p1_claims": (("Discover findings carried into Build: {n} claims ({f} sourced facts). They appear as D1, D2… in "
                  "the build inputs."),
                  ("نتائج الاكتشاف المنقولة إلى البناء: {n} ادعاءات ({f} حقائق موثقة بمصدر). تظهر كـ D1، D2… في "
                  "مدخلات البناء.")),
    "start": ("▶ Start Phase 3 Build", "▶ ابدأ المرحلة 3: البناء"),
    "takes": ("About 6 minutes with the local model on a CPU.", "حوالي 6 دقائق مع النموذج المحلي على المعالج."),
    "status": ("**Status:** {s} · **Brief version:** v{v}", "**الحالة:** {s} · **نسخة الموجز:** v{v}"),
    "stale": ("Stale: the brief is now v{v}. Approve Discover again, then rebuild.",
              "قديم: الموجز الآن النسخة {v}. وافق على الاكتشاف مجدداً ثم أعد البناء."),
    "building": ("Building since {t}: the agents run one after another, about 6 minutes on CPU.",
                 "جارٍ البناء منذ {t}: يعمل الوكلاء واحداً تلو الآخر، حوالي 6 دقائق."),
    "failed": ("the build run failed", "فشل تشغيل البناء"),
    "rec": ("**Recommendation: {o}** — {r}", "**التوصية: {o}** — {r}"),
    "template": ("Template", "القالب"), "tests": ("MVP tests passed", "اختبارات النموذج الناجحة"),
    "rounds": ("Plan rounds", "جولات التخطيط"), "time": ("Time", "الوقت"),
    "mvp_cap": ("The MVP as built: one HTML file, data stays on the device, payments MOCKED.",
                "النموذج كما بُني: ملف HTML واحد، البيانات تبقى على الجهاز، المدفوعات وهمية (MOCKED)."),
    "download": ("⬇ Download the MVP (one HTML file)", "⬇ تنزيل النموذج (ملف HTML واحد)"),
    "no_mvp": ("No MVP was built in this run.", "لم يُبنَ نموذج في هذا التشغيل."),
    "not_written": ("_not written in this run_", "_لم يُكتب في هذا التشغيل_"),
    "decision": ("Your decision", "قرارك"), "note": ("Note", "ملاحظة"),
    "go": ("Go", "متابعة"), "repeat": ("Repeat", "إعادة"), "stop": ("Stop", "إيقاف"),
    "again": ("▶ Build again", "▶ أعد البناء"), "closed": ("This run is closed.", "هذا التشغيل مُغلق."),
    "tabs": (["MVP", "Build inputs", "Requirements", "MVP plan", "Validation", "Tests", "User guide",
              "Evidence summary", "Gate"],
             ["النموذج", "مدخلات البناء", "المتطلبات", "خطة النموذج", "التحقق", "الاختبارات", "دليل المستخدم",
              "ملخص الأدلة", "البوابة"]),
}
STATUS = {"running": ("⏳ building", "⏳ جارٍ البناء"), "awaiting_approval": ("🟡 waiting for your decision",
                                                                         "🟡 بانتظار قرارك"),
          "approved": ("✅ go", "✅ متابعة"), "revision_requested": ("🔁 repeat", "🔁 إعادة"),
          "rejected": ("⛔ stop", "⛔ إيقاف"), "failed": ("❌ failed", "❌ فشل")}
DECISION = {"approve": ("go", "متابعة"), "revise": ("repeat", "إعادة"), "reject": ("stop", "إيقاف"),
            "pivot": ("pivot", "تحويل"), "waive": ("go (waiver)", "متابعة (استثناء)")}
REC = {"go": "success", "repeat": "warning", "pivot": "warning", "stop": "error"}
i = 1 if L == "ar" else 0


def t(key, **kw):
    v = T[key][i]
    return v.format(**kw) if isinstance(v, str) else v


setup(t("title"), t("sub"))
phase_bar(3, status={0: " · Working", 1: " · Working", 2: " · STUBBED", 3: " · Working", 4: " · STUBBED",
                     5: " · MOCKED", 6: " · STUBBED"})
st.caption(t("how"))
try:
    briefs = api("GET", "/stages/briefs")
except RuntimeError as e:
    st.error(t("api_down", api=API, e=e))
    st.stop()
if not briefs:
    st.info(t("no_brief"))
    st.stop()

labels = {b["brief_id"]: f"{(b['idea'] or 'untitled')[:70]} · {b['country_code'] or '?'} · v{b['version']}"
          for b in briefs}
confirmed = (st.session_state.get("brief") or {}).get("id")
if confirmed not in labels:  # only the brief confirmed in this session goes down the pipeline, never older ideas
    st.info(t("no_brief"))
    st.page_link("pages/1_onboarding.py", label=t("brief"))
    st.stop()
brief_id = confirmed
st.markdown(f"**{t('brief')}:** {labels[brief_id]}")
latest = next(b["version"] for b in briefs if b["brief_id"] == brief_id)
sid = st.text_input(t("session"), value=st.session_state.get("sid", ""), type="password")
headers = {"X-Founder-Session": sid} if sid else {}

# ---------- what Phase 1 handed over ----------
discover = [r for r in api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "discover"})
            if r["brief_version"] == latest]
approved = next((r for r in discover if r["status"] == "approved"), None)
validated = any(r["brief_version"] == latest and r["status"] == "approved"
                for r in api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "validate"}))
st.subheader(t("from_p1"))
if not (approved and validated):
    st.info(t("p1_none", v=latest))
    st.page_link("pages/2_pipeline.py", label=t("to_p1"))
    st.stop()
gate1 = ((approved.get("output") or {}).get("research") or {}).get("gate") or {}
last = (approved.get("decisions") or [{}])[-1]
st.markdown(t("p1_rec", rec=str(gate1.get("recommendation", "-")).upper(),
              dec=DECISION.get(last.get("decision"), (last.get("decision", "-"),) * 2)[i])
            + (f" — _{last['note']}_" if last.get("note") else ""))
try:
    claims = api("GET", f"/stages/runs/{approved['id']}/claims")
    st.caption(t("p1_claims", n=len(claims), f=sum(c["type"] == "fact" and bool(c.get("url")) for c in claims)))
except RuntimeError:
    pass

# ---------- this stage ----------
runs = api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "build"})
current = [r for r in runs if r["brief_version"] == latest]
st.divider()
if not current:
    if st.button(t("start"), type="primary"):
        try:
            api("POST", "/stages/build/runs", json={"brief_id": brief_id})
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
    st.caption(t("takes"))
    st.stop()

run = current[0]
build = (run["output"] or {}).get("build") or {}
st.markdown(t("status", s=STATUS.get(run["status"], (run["status"],) * 2)[i], v=run["brief_version"]))
if run["stale"]:
    st.warning(t("stale", v=run["latest_brief_version"]))
if run["status"] == "running":
    st.info(t("building", t=run["created_at"][:19].replace("T", " ")))
    time.sleep(5)
    st.rerun()
if run["status"] == "failed":
    st.error(build.get("error") or t("failed"))
    st.stop()

gate = build.get("gate") or {}
if gate:
    getattr(st, REC.get(gate["outcome"], "info"))(t("rec", o=gate["outcome"].upper(), r=gate["reason"]))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("template"), build.get("template") or "-")
    c2.metric(t("tests"), f"{int(gate.get('actual') or 0)} / {int(gate.get('target') or 0)}")
    c3.metric(t("rounds"), build.get("plan_rounds", 0))
    c4.metric(t("time"), f"{build.get('seconds', 0):.0f} s")

files = build.get("files") or {}
mvp = files.get("phase3_step5_mvp.html")
tabs = st.tabs(t("tabs"))
with tabs[0]:
    if mvp:
        st.caption(t("mvp_cap"))
        st.download_button(t("download"), mvp, file_name="mvp.html", mime="text/html")
        components.html(mvp, height=640, scrolling=True)
    else:
        st.info(t("no_mvp"))
names = ["phase3_step1_build_inputs.md", "phase3_step2_requirements.md", "phase3_step3_mvp_plan.md",
         "phase3_step4_validation.md", "phase3_step6_test_report.md", "phase3_step7_user_guide.md",
         "phase3_step8_evidence_summary.md", "phase3_gate_build.md"]
for tab, name in zip(tabs[1:], names, strict=True):
    with tab:
        st.markdown(files.get(name) or t("not_written"))

st.divider()
st.subheader(t("decision"))
for d in run["decisions"]:
    st.caption(f"{d['created_at'][:19]} · {DECISION.get(d['decision'], (d['decision'],) * 2)[i]}"
               + (f": {d['note']}" if d["note"] else ""))
if run["status"] == "revision_requested" and st.button(t("again"), type="primary"):
    try:
        api("POST", "/stages/build/runs", json={"brief_id": brief_id})
        st.rerun()
    except RuntimeError as e:
        st.error(str(e))
if run["status"] in ("awaiting_approval", "revision_requested"):
    note = st.text_area(t("note"), key=f"note-{run['id']}")
    cols = st.columns(3)

    def send(decision):
        try:
            api("POST", f"/stages/runs/{run['id']}/decision", headers=headers, json={"decision": decision, "note": note})
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
    if cols[0].button(t("go"), width="stretch"):
        send("approve")
    if cols[1].button(t("repeat"), width="stretch"):
        send("revise")
    if cols[2].button(t("stop"), width="stretch"):
        send("reject")
else:
    st.caption(t("closed"))
