"""Pipeline: Phase 1 Discover (research -> gate -> founder decision), then Phase 2 Validate on the same page once
Discover is approved. Arabic or English (sidebar language; the layout flips right-to-left automatically)."""

import time

import streamlit as st
from common import API, api, phase_bar, setup, ui_lang

L = ui_lang()
T = {
    "title": ("Pipeline · Phase 1 Discover", "المراحل · المرحلة 1: الاكتشاف"),
    "sub": ("Six phases, each ending at a gate the founder approves.",
            "ست مراحل، تنتهي كل منها ببوابة يوافق عليها المؤسس."),
    "how": (("Find opportunities, score them against alternatives, define the market, prepare customer interviews. "
             "Confirming your brief is the go-ahead to research. Nothing is published, sent or spent."),
            ("نبحث عن الفرص، نقيّمها مقابل البدائل، نحدد السوق، ونجهّز مقابلات العملاء. تأكيد الموجز هو الإذن "
             "بالبحث. لا يُنشر ولا يُرسل ولا يُنفق أي شيء.")),
    "api_down": ("Cannot reach the API at {api}: {e}", "تعذّر الوصول إلى الخادم {api}: {e}"),
    "no_brief": ("No confirmed brief yet. Confirm one on the onboarding page first.",
                 "لا يوجد موجز مؤكد بعد. أكّد موجزاً في صفحة الإعداد أولاً."),
    "brief": ("Brief", "الموجز"),
    "session": ("Your founder session (from the onboarding page; needed to decide or add interviews)",
                "جلسة المؤسس (من صفحة الإعداد؛ مطلوبة لاتخاذ القرار أو إضافة المقابلات)"),
    "run": ("Run", "التشغيل"),
    "status": ("**Status:** {s} · **Brief version:** v{v}", "**الحالة:** {s} · **نسخة الموجز:** v{v}"),
    "stale": ("Stale: the brief is now v{v}; a new run starts for it.",
              "قديم: الموجز الآن النسخة {v}؛ يبدأ تشغيل جديد لها."),
    "researching": ("Researching… {n} searches/API calls, {p} pages read.",
                    "جارٍ البحث… {n} عمليات بحث/استدعاء، {p} صفحات مقروءة."),
    "failed": ("the run failed", "فشل التشغيل"),
    "rec": ("**Recommendation: {o}**", "**التوصية: {o}**"),
    "check": ("check", "الفحص"), "target": ("target (set before the run)", "الهدف (محدد قبل التشغيل)"),
    "actual": ("actual", "الفعلي"), "passed": ("passed", "ناجح"),
    "collect": ("**To collect:**", "**المطلوب جمعه:**"),
    "refused": ("Refused a request in the brief ({f}): {m}", "رُفض طلب في الموجز ({f}): {m}"),
    "tabs": (["1 What Discover adds", "2 Opportunities", "3 Idea scores", "4 Market", "5 Interviews", "Critic",
              "Trace"],
             ["1 ما يضيفه الاكتشاف", "2 الفرص", "3 تقييم الأفكار", "4 السوق", "5 المقابلات", "المراجِع", "السجل"]),
    "adds": (("Discover adds: **{i}** opportunities · scores (top: **{top}**, {score}/5) · market: **{c}** competitors, "
             "SOM {som}"), ("يضيف الاكتشاف: **{i}** فرص · تقييمات (الأعلى: **{top}**، {score}/5) · السوق: **{c}** "
             "منافسين، الحصة القابلة للتحقيق {som}")),
    "from_onb": ("From onboarding: brief v{v} · {pt} · still unknown: {u}",
                 "من الإعداد: الموجز النسخة {v} · {pt} · ما زال غير معروف: {u}"),
    "none": ("none", "لا شيء"),
    "built_by": ("{o} · {pt} · built by {b}", "{o} · {pt} · أعدّه {b}"),
    "pain": ("Pain", "المشكلة"), "why_you": ("Why you", "لماذا أنت"),
    "no_quote": ("ASSUMPTION: no quote from a real person yet", "ASSUMPTION: لا يوجد اقتباس من شخص حقيقي بعد"),
    "published": ("published", "نُشر"), "undated": ("undated", "بلا تاريخ"), "retrieved": ("retrieved", "استُرجع"),
    "idea": ("idea", "الفكرة"), "total": ("total", "المجموع"),
    "scores_note": (("(A) = ASSUMPTION: no evidence, capped at 3. Totals are computed in code from "
                    "config/gates/discover.yaml."),
                    "(A) = ASSUMPTION: بلا دليل، الحد الأقصى 3. المجاميع تُحسب بالكود من config/gates/discover.yaml."),
    "segment": ("**Segment:** {s} · **Geography:** {g} · **Beachhead:** {b}",
                "**الشريحة:** {s} · **النطاق الجغرافي:** {g} · **نقطة البداية:** {b}"),
    "name": ("name", "الاسم"), "kind": ("kind", "النوع"), "price": ("price", "السعر"),
    "no_price": ("no sourced price", "لا سعر موثق"), "signal": ("signal", "مؤشر"), "link": ("link", "الرابط"),
    "input": ("input", "المُدخل"), "low": ("low", "الأدنى"), "high": ("high", "الأعلى"), "unit": ("unit", "الوحدة"),
    "basis": ("basis", "الأساس"), "note": ("note", "ملاحظة"), "unknown": ("unknown", "غير معروف"),
    "who": ("**Who:** {w} · **How many:** {n}", "**مَن:** {w} · **كم شخصاً:** {n}"),
    "where": ("**Where to find them:**", "**أين تجدهم:**"),
    "questions": ("**Questions ({l})**", "**الأسئلة ({l})**"), "avoid": ("Avoid: ", "تجنّب: "),
    "enter_iv": ("Enter an interview (your own notes)", "أدخل مقابلة (ملاحظاتك أنت)"),
    "person": ("Person (anonymous label, e.g. 'Freelance designer, Cairo')",
               "الشخص (وصف مجهول، مثل «مصممة مستقلة، القاهرة»)"),
    "date": ("Date", "التاريخ"),
    "notes": ("What they said and did (their words, one point per line)",
              "ما قالوه وفعلوه (كلماتهم، نقطة في كل سطر)"),
    "described": ("They described the problem themselves", "وصفوا المشكلة بأنفسهم"),
    "save_iv": ("Save interview", "حفظ المقابلة"),
    "noise": ("{n} line(s) are noise (compliments, hypotheticals, opinions), not evidence.",
              "{n} سطر/أسطر ضوضاء (مجاملات، افتراضات، آراء)، وليست دليلاً."),
    "noise_tag": ("· noise · ", "· ضوضاء · "),
    "model_review": ("**Model review:** {r}", "**مراجعة النموذج:** {r}"), "judge": (" (judge: {j})", " (الحَكَم: {j})"),
    "your_decision": ("Your decision", "قرارك"), "note_in": ("Note", "ملاحظة"),
    "go": ("Go", "متابعة"), "repeat": ("Repeat", "إعادة"), "pivot": ("Pivot", "تحويل"), "stop": ("Stop", "إيقاف"),
    "pivot_to": ("Pivot to", "التحويل إلى"), "waiver": ("waiver reason", "سبب الاستثناء"),
    "waive": ("Waive interviews", "استثناء المقابلات"), "closed": ("This run is closed.", "هذا التشغيل مُغلق."),
    "waiver_tag": (" (waiver: {w})", " (استثناء: {w})"),
    "validate_later": ("Phase 2 Validate opens here once you approve Discover (Go) for the current brief version.",
                       "تُفتح المرحلة 2 (التحقق) هنا بعد موافقتك (متابعة) على الاكتشاف لنسخة الموجز الحالية."),
}
STATUS = {"running": ("⏳ researching", "⏳ جارٍ البحث"),
          "awaiting_approval": ("🟡 waiting for your decision", "🟡 بانتظار قرارك"), "approved": ("✅ go", "✅ متابعة"),
          "revision_requested": ("🔁 repeat", "🔁 إعادة"), "pivoted": ("↩️ pivot", "↩️ تحويل"),
          "rejected": ("⛔ stop", "⛔ إيقاف"), "failed": ("❌ failed", "❌ فشل")}
REC = {"go": "success", "repeat": "warning", "pivot": "warning", "stop": "error"}
PHASE_STATUS = {0: "Working", 1: "Working", 2: "Working", 3: "Working", 4: "STUBBED", 5: "MOCKED", 6: "STUBBED"}
i = 1 if L == "ar" else 0


def t(key, **kw):
    v = T[key][i]
    return v.format(**kw) if kw else v


def status(s):
    return STATUS[s][i] if s in STATUS else s


setup(t("title"), t("sub"), active_phase=None, lang=L)
phase_bar(1, lang=L, status={k: f" · {v}" for k, v in PHASE_STATUS.items()})
st.caption(t("how"))
try:
    briefs = api("GET", "/stages/briefs")
except Exception as e:  # noqa: BLE001
    st.error(t("api_down", api=API, e=e))
    st.stop()
if not briefs:
    st.info(t("no_brief"))
    st.stop()

labels = {b["brief_id"]: f"{(b['idea'] or 'untitled')[:70]} · {b['country_code'] or '?'} · v{b['version']}"
          for b in briefs}
confirmed = (st.session_state.get("brief") or {}).get("id")
if confirmed not in labels:  # Discover opens only for the brief the founder confirmed in this session
    st.info(t("no_brief"))
    st.page_link("pages/1_onboarding.py", label="→ " + t("brief"))
    st.stop()
brief_id = confirmed
st.markdown(f"**{t('brief')}:** {labels[brief_id]}")
latest = next(b["version"] for b in briefs if b["brief_id"] == brief_id)
sid = st.text_input(t("session"), value=st.session_state.get("sid", ""), type="password")
headers = {"X-Founder-Session": sid} if sid else {}
runs = api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "discover"})
if not any(r["brief_version"] == latest for r in runs):  # confirmed brief = approval to research
    try:
        api("POST", "/stages/discover/runs", json={"brief_id": brief_id})
        st.rerun()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

run = runs[0] if len(runs) == 1 else next(r for r in runs if r["id"] == st.selectbox(
    t("run"), [r["id"] for r in runs], format_func=lambda rid: next(
        f"{r['created_at'][:19]} · v{r['brief_version']} · {status(r['status'])}" for r in runs if r["id"] == rid)))
research = (run["output"] or {}).get("research") or {}
st.markdown(t("status", s=status(run["status"]), v=run["brief_version"]))
if run["stale"]:
    st.warning(t("stale", v=run["latest_brief_version"]))
if run["status"] == "running":
    trace = research.get("trace") or []
    st.info(t("researching", n=sum(e["action"] in ("search", "api_call") for e in trace),
              p=sum(e["action"] == "fetch" for e in trace)))
    for e in trace[-8:]:
        st.caption(f"{e['agent']} · {e['action']} · {e.get('query') or e.get('url') or e.get('api') or ''}")
    time.sleep(3)
    st.rerun()
if run["status"] == "failed":
    st.error(research.get("error") or t("failed"))
    st.stop()

gate = research.get("gate") or {}
if gate:
    getattr(st, REC.get(gate["recommendation"], "info"))(
        t("rec", o=gate["recommendation"].upper()) + (f" → {gate['pivot_to']}" if gate.get("pivot_to") else "")
        + " — " + " ".join(gate.get("reasons", [])))
    c1, c2 = st.columns([3, 2])
    c1.dataframe([{t("check"): c["check"], t("target"): c["target"], t("actual"): str(c["actual"]),
                   t("passed"): "✅" if c["passed"] else "❌"} for c in gate.get("checks", [])],
                 hide_index=True, width="stretch")
    if gate.get("collect_next"):
        c2.markdown(t("collect") + "\n" + "\n".join(f"- {x}" for x in gate["collect_next"]))
for r in research.get("refused_requests") or []:
    st.warning(t("refused", f=r["field"], m=r["message"]))

tabs = st.tabs(t("tabs"))
claims = {c["id"]: c for c in research.get("claims") or []}


def quote(c):
    st.markdown(f"> {c['quote']}\n\n[{(c.get('title') or c['url'])[:80]}]({c['url']}) · {t('published')} "
                f"{c.get('published_at') or t('undated')} · {t('retrieved')} {(c.get('retrieved_at') or '')[:10]}"
                + (f" · ⚠️ {', '.join(c['flags'])}" if c.get("flags") else ""))


def rng(m, x):
    return t("unknown") if None in x else f"{x[0]:,.0f} – {x[1]:,.0f} {m['currency']}"


with tabs[0]:
    ideas, scores, m = research.get("ideas") or [], research.get("scores") or [], research.get("market") or {}
    top = max(scores, key=lambda s: s["total"]) if scores else None
    top_title = next((x["title"] for x in ideas if top and x["id"] == top["idea_id"]), "-")
    st.markdown(t("adds", i=len(ideas), top=top_title, score=top["total"] if top else "-",
                  c=len(m.get("competitors") or []), som=rng(m, m["som"]) if m else t("unknown")))
    b = research.get("brief") or {}
    pt = b.get("product_type") or {}
    st.caption(t("from_onb", v=b.get("version", run["brief_version"]), pt=pt.get("label") or "-",
                 u=", ".join(b.get("unknown") or []) or t("none")))
    if pt.get("clarifying_question"):
        st.warning(pt["clarifying_question"])
with tabs[1]:
    for idea in research.get("ideas") or []:
        with st.expander(f"{idea['id']} · {idea['title']}", expanded=idea["origin"] == "starting_idea"):
            st.caption(t("built_by", o=idea["origin"], pt=idea["product_type"], b=idea["built_by"]))
            st.markdown(f"{idea['description']}\n\n**{t('pain')}:** {idea['pain']}\n\n**{t('why_you')}:** "
                        f"{idea['why_founder']}")
            cited = [claims[c] for c in idea["pain_claim_ids"] if c in claims][:3]
            for c in cited:
                quote(c)
            if not cited:
                st.caption(t("no_quote"))
            for a in idea.get("assumptions") or []:
                st.caption(a)
with tabs[2]:
    rows = []
    for s in research.get("scores") or []:
        row = {t("idea"): s["idea_id"], t("total"): s["total"]}
        row.update({c["criterion"]: f"{c['score']:g}" + (" (A)" if c["basis"] == "ASSUMPTION" else "")
                    for c in s["criteria"]})
        rows.append(row)
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption(t("scores_note"))
with tabs[3]:
    m = research.get("market") or {}
    if m:
        st.markdown(t("segment", s=m["segment"], g=m["geography"], b=m["beachhead"]))
        st.dataframe([{t("name"): c["name"], t("kind"): c["kind"], t("price"): c.get("price") or t("no_price"),
                       t("signal"): c.get("signal"), t("link"): c["url"]} for c in m["competitors"]], hide_index=True,
                     width="stretch", column_config={t("link"): st.column_config.LinkColumn()})
        st.code(m["formula"])
        st.dataframe([{t("input"): x["name"], t("low"): x["low"], t("high"): x["high"], t("unit"): x["unit"],
                       t("basis"): x["basis"], t("note"): x["note"]} for x in m["inputs"]], hide_index=True,
                     width="stretch")
        st.markdown(f"**TAM** {rng(m, m['tam'])} · **SAM** {rng(m, m['sam'])} · **SOM** {rng(m, m['som'])}")
with tabs[4]:
    ip = research.get("interview_plan") or {}
    if ip:
        st.markdown(t("who", w=ip["who"], n=ip["how_many"]))
        st.markdown(t("where") + "\n" + "\n".join(f"- {w}" for w in ip["where_to_find"]))
        for lang, g in ip["guides"].items():
            st.markdown(t("questions", l=lang) + "\n" + "\n".join(f"{n}. {q}" for n, q in enumerate(g["questions"], 1)))
            st.caption(t("avoid") + " · ".join(g["avoid"]))
        st.info(ip["results_rule"])
    st.subheader(t("enter_iv"))
    with st.form("interview", clear_on_submit=True):
        person = st.text_input(t("person"))
        held = st.date_input(t("date"))
        notes = st.text_area(t("notes"))
        problem = st.checkbox(t("described"), value=True)
        if st.form_submit_button(t("save_iv")):
            try:
                out = api("POST", "/stages/discover/interviews", headers=headers, json={
                    "brief_id": brief_id, "person": person, "held_on": str(held), "notes": notes,
                    "describes_problem": problem})
                for n in out["interview"]["tagged"]:
                    (st.success if n["counts"] else st.caption)(f"{', '.join(n['tags'])}: {n['text']}")
                if out["noise"]:
                    st.warning(t("noise", n=len(out["noise"])))
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))
    for iv in api("GET", "/stages/discover/interviews", params={"brief_id": brief_id}):
        with st.expander(f"{iv['person']} · {iv['held_on'] or ''}"):
            for n in iv["tagged"]:
                st.markdown(("✅ " if n["counts"] else t("noise_tag")) + f"`{', '.join(n['tags'])}` {n['text']}")
with tabs[5]:
    cr = research.get("critic") or {}
    st.markdown(t("model_review", r=cr.get("model_review", "")) +
                (t("judge", j=cr["judge_model"]) if cr.get("judge_model") else ""))
    for f in cr.get("findings") or []:
        st.markdown(f"- **{f['kind']}**: {f['detail']}")
with tabs[6]:
    st.dataframe([{k: e.get(k) for k in ("at", "agent", "action", "api", "query", "url", "results", "reason", "error")}
                  for e in research.get("trace", [])], hide_index=True, width="stretch")

st.divider()
st.subheader(t("your_decision"))
for d in run["decisions"]:
    st.caption(f"{d['created_at'][:19]} · {d['decision']}" + (f" → {d['pivot_to']}" if d.get("pivot_to") else "")
               + (f": {d['note']}" if d["note"] else "")
               + (t("waiver_tag", w=d["waiver_reason"]) if d.get("waiver_reason") else ""))
if run["status"] in ("awaiting_approval", "revision_requested"):
    note = st.text_area(t("note_in"), key=f"note-{run['id']}")
    pivot_ideas = [x["id"] for x in research.get("ideas") or [] if x["id"] != "I0"] + ["onboarding"]
    cols = st.columns(5)

    def send(decision, **kw):
        try:
            api("POST", f"/stages/runs/{run['id']}/decision", headers=headers,
                json={"decision": decision, "note": note, **kw})
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
    if cols[0].button(t("go"), width="stretch"):
        send("approve")
    if cols[1].button(t("repeat"), width="stretch"):
        send("revise")
    pivot_to = cols[2].selectbox(t("pivot_to"), pivot_ideas, label_visibility="collapsed")
    if cols[2].button(t("pivot"), width="stretch"):
        send("pivot", pivot_to=pivot_to)
    if cols[3].button(t("stop"), width="stretch"):
        send("reject")
    reason = cols[4].text_input(t("waiver"), label_visibility="collapsed", placeholder=t("waiver"))
    if cols[4].button(t("waive"), width="stretch"):
        send("waive", waiver_reason=reason)
else:
    st.caption(t("closed"))

st.divider()
if run["status"] == "approved" and not run.get("stale"):
    # Phase 2 Validate (same render as pages/4_validate.py), shown once Discover is approved for this brief version
    import importlib.util
    from pathlib import Path

    _spec = importlib.util.spec_from_file_location("validate_page", Path(__file__).with_name("4_validate.py"))
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _mod.render(brief_id, sid)
    # Phase 4 Commercial (same render as pages/6_commercial.py), shown once the founder approved Build (page 5)
    builds = api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "build"})
    if builds and builds[0]["status"] == "approved" and not builds[0].get("stale"):
        st.divider()
        _spec4 = importlib.util.spec_from_file_location("commercial_page", Path(__file__).with_name("6_commercial.py"))
        _mod4 = importlib.util.module_from_spec(_spec4)
        _spec4.loader.exec_module(_mod4)
        _mod4.render(brief_id, sid)
else:
    st.caption(t("validate_later"))
