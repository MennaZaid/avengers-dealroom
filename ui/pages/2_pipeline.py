"""Pipeline: the six phases and their gates. Phase 1 (Discover) is built: it starts once the founder has confirmed
the brief and ends at the founder's gate. Phases 2-6 are shown as STUBBED until they are built."""

import time

import streamlit as st
from common import API, api, phase_bar, setup

STATUS = {"running": "⏳ researching", "awaiting_approval": "🟡 waiting for your decision", "approved": "✅ go",
          "revision_requested": "🔁 repeat", "pivoted": "↩️ pivot", "rejected": "⛔ stop", "failed": "❌ failed"}
REC = {"go": "success", "repeat": "warning", "pivot": "warning", "stop": "error"}
PHASE_STATUS = {0: "Working", 1: "Working", 2: "STUBBED", 3: "STUBBED", 4: "STUBBED", 5: "MOCKED", 6: "STUBBED"}

setup("Pipeline · Phase 1 Discover", "Six phases, each ending at a gate the founder approves.", active_phase=None)
phase_bar(1, status={k: f" · {v}" for k, v in PHASE_STATUS.items()})
st.caption("Sharpen the idea, score it against alternatives, define the market, prepare customer interviews. "
           "Confirming your brief is the go-ahead to research. Nothing is published, sent or spent.")
try:
    briefs = api("GET", "/stages/briefs")
except Exception as e:  # noqa: BLE001
    st.error(f"Cannot reach the API at {API}: {e}")
    st.stop()
if not briefs:
    st.info("No confirmed brief yet. Confirm one on the onboarding page first.")
    st.stop()

labels = {b["brief_id"]: f"{(b['idea'] or 'untitled')[:70]} · {b['country_code'] or '?'} · v{b['version']}"
          for b in briefs}
confirmed = (st.session_state.get("brief") or {}).get("id")
keys = list(labels)
brief_id = st.selectbox("Brief", keys, format_func=labels.get, index=keys.index(confirmed) if confirmed in keys else 0)
latest = next(b["version"] for b in briefs if b["brief_id"] == brief_id)
sid = st.text_input("Your founder session (from the onboarding page; needed to decide or add interviews)",
                    value=st.session_state.get("sid", ""), type="password")
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
    "Run", [r["id"] for r in runs], format_func=lambda i: next(
        f"{r['created_at'][:19]} · brief v{r['brief_version']} · {STATUS.get(r['status'], r['status'])}"
        for r in runs if r["id"] == i)))
research = (run["output"] or {}).get("research") or {}
st.markdown(f"**Status:** {STATUS.get(run['status'], run['status'])} · **Brief version:** v{run['brief_version']}")
if run["stale"]:
    st.warning(f"Stale: the brief is now v{run['latest_brief_version']}; a new run starts for it.")
if run["status"] == "running":
    trace = research.get("trace") or []
    st.info(f"Researching… {sum(e['action'] in ('search', 'api_call') for e in trace)} searches/API calls, "
            f"{sum(e['action'] == 'fetch' for e in trace)} pages read.")
    for e in trace[-8:]:
        st.caption(f"{e['agent']} · {e['action']} · {e.get('query') or e.get('url') or e.get('api') or ''}")
    time.sleep(3)
    st.rerun()
if run["status"] == "failed":
    st.error(research.get("error") or "the run failed")
    st.stop()

gate = research.get("gate") or {}
if gate:
    getattr(st, REC.get(gate["recommendation"], "info"))(
        f"**Recommendation: {gate['recommendation'].upper()}**"
        + (f" → {gate['pivot_to']}" if gate.get("pivot_to") else "") + " — " + " ".join(gate.get("reasons", [])))
    c1, c2 = st.columns([3, 2])
    c1.dataframe([{"check": c["check"], "target (set before the run)": c["target"], "actual": str(c["actual"]),
                   "passed": "✅" if c["passed"] else "❌"} for c in gate.get("checks", [])],
                 hide_index=True, width="stretch")
    if gate.get("collect_next"):
        c2.markdown("**To collect:**\n" + "\n".join(f"- {x}" for x in gate["collect_next"]))
for r in research.get("refused_requests") or []:
    st.warning(f"Refused a request in the brief ({r['field']}): {r['message']}")

tabs = st.tabs(["1 Brief", "2 Opportunities", "3 Idea scores", "4 Market", "5 Interviews", "Critic", "Trace"])
claims = {c["id"]: c for c in research.get("claims") or []}


def quote(c):
    st.markdown(f"> {c['quote']}\n\n[{(c.get('title') or c['url'])[:80]}]({c['url']}) · published "
                f"{c.get('published_at') or 'undated'} · retrieved {(c.get('retrieved_at') or '')[:10]}"
                + (f" · ⚠️ {', '.join(c['flags'])}" if c.get("flags") else ""))


with tabs[0]:
    b = research.get("brief") or {}
    st.dataframe([{"field": k, "value": v or "unknown"} for k, v in (b.get("required") or {}).items()],
                 hide_index=True, width="stretch")
    pt = b.get("product_type") or {}
    st.markdown(f"**Product type:** {pt.get('label')} ({pt.get('group')}) — {pt.get('trigger')}")
    if pt.get("clarifying_question"):
        st.warning(pt["clarifying_question"])
with tabs[1]:
    for i in research.get("ideas") or []:
        with st.expander(f"{i['id']} · {i['title']}", expanded=i["origin"] == "starting_idea"):
            st.caption(f"{i['origin']} · {i['product_type']} · built by {i['built_by']}")
            st.markdown(f"{i['description']}\n\n**Pain:** {i['pain']}\n\n**Why you:** {i['why_founder']}")
            cited = [claims[c] for c in i["pain_claim_ids"] if c in claims][:3]
            for c in cited:
                quote(c)
            if not cited:
                st.caption("ASSUMPTION: no quote from a real person yet")
            for a in i.get("assumptions") or []:
                st.caption(a)
with tabs[2]:
    rows = []
    for s in research.get("scores") or []:
        row = {"idea": s["idea_id"], "total": s["total"]}
        row.update({c["criterion"]: f"{c['score']:g}" + (" (A)" if c["basis"] == "ASSUMPTION" else "")
                    for c in s["criteria"]})
        rows.append(row)
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("(A) = ASSUMPTION: no evidence, capped at 3. Totals are computed in code from config/gates/discover.yaml.")
with tabs[3]:
    m = research.get("market") or {}
    if m:
        st.markdown(f"**Segment:** {m['segment']} · **Geography:** {m['geography']} · **Beachhead:** {m['beachhead']}")
        st.dataframe([{"name": c["name"], "kind": c["kind"], "price": c.get("price") or "no sourced price",
                       "signal": c.get("signal"), "link": c["url"]} for c in m["competitors"]], hide_index=True,
                     width="stretch", column_config={"link": st.column_config.LinkColumn()})
        st.code(m["formula"])
        st.dataframe([{"input": i["name"], "low": i["low"], "high": i["high"], "unit": i["unit"],
                       "basis": i["basis"], "note": i["note"]} for i in m["inputs"]], hide_index=True, width="stretch")

        def rng(x):
            return "unknown" if None in x else f"{x[0]:,.0f} – {x[1]:,.0f} {m['currency']}"
        st.markdown(f"**TAM** {rng(m['tam'])} · **SAM** {rng(m['sam'])} · **SOM** {rng(m['som'])}")
with tabs[4]:
    ip = research.get("interview_plan") or {}
    if ip:
        st.markdown(f"**Who:** {ip['who']} · **How many:** {ip['how_many']}")
        st.markdown("**Where to find them:**\n" + "\n".join(f"- {w}" for w in ip["where_to_find"]))
        for lang, g in ip["guides"].items():
            st.markdown(f"**Questions ({lang})**\n" + "\n".join(f"{n}. {q}" for n, q in enumerate(g["questions"], 1)))
            st.caption("Avoid: " + " · ".join(g["avoid"]))
        st.info(ip["results_rule"])
    st.subheader("Enter an interview (your own notes)")
    with st.form("interview", clear_on_submit=True):
        person = st.text_input("Person (anonymous label, e.g. 'Freelance designer, Cairo')")
        held = st.date_input("Date")
        notes = st.text_area("What they said and did (their words, one point per line)")
        problem = st.checkbox("They described the problem themselves", value=True)
        if st.form_submit_button("Save interview"):
            try:
                out = api("POST", "/stages/discover/interviews", headers=headers, json={
                    "brief_id": brief_id, "person": person, "held_on": str(held), "notes": notes,
                    "describes_problem": problem})
                for n in out["interview"]["tagged"]:
                    (st.success if n["counts"] else st.caption)(f"{', '.join(n['tags'])}: {n['text']}")
                if out["noise"]:
                    st.warning(f"{len(out['noise'])} line(s) are noise (compliments, hypotheticals, opinions), "
                               "not evidence.")
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))
    for iv in api("GET", "/stages/discover/interviews", params={"brief_id": brief_id}):
        with st.expander(f"{iv['person']} · {iv['held_on'] or ''}"):
            for n in iv["tagged"]:
                st.markdown(("✅ " if n["counts"] else "· noise · ") + f"`{', '.join(n['tags'])}` {n['text']}")
with tabs[5]:
    cr = research.get("critic") or {}
    st.markdown(f"**Model review:** {cr.get('model_review', '')}" +
                (f" (judge: {cr['judge_model']})" if cr.get("judge_model") else ""))
    for f in cr.get("findings") or []:
        st.markdown(f"- **{f['kind']}**: {f['detail']}")
with tabs[6]:
    st.dataframe([{k: e.get(k) for k in ("at", "agent", "action", "api", "query", "url", "results", "reason", "error")}
                  for e in research.get("trace", [])], hide_index=True, width="stretch")

st.divider()
st.subheader("Your decision")
for d in run["decisions"]:
    st.caption(f"{d['created_at'][:19]} · {d['decision']}" + (f" → {d['pivot_to']}" if d.get("pivot_to") else "")
               + (f": {d['note']}" if d["note"] else "") + (f" (waiver: {d['waiver_reason']})" if d.get("waiver_reason")
                                                           else ""))
if run["status"] in ("awaiting_approval", "revision_requested"):
    note = st.text_area("Note", key=f"note-{run['id']}")
    ideas = [i["id"] for i in research.get("ideas") or [] if i["id"] != "I0"] + ["onboarding"]
    cols = st.columns(5)

    def send(decision, **kw):
        try:
            api("POST", f"/stages/runs/{run['id']}/decision", headers=headers,
                json={"decision": decision, "note": note, **kw})
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
    if cols[0].button("Go", width="stretch"):
        send("approve")
    if cols[1].button("Repeat", width="stretch"):
        send("revise")
    pivot_to = cols[2].selectbox("Pivot to", ideas, label_visibility="collapsed")
    if cols[2].button("Pivot", width="stretch"):
        send("pivot", pivot_to=pivot_to)
    if cols[3].button("Stop", width="stretch"):
        send("reject")
    reason = cols[4].text_input("Waiver reason", label_visibility="collapsed", placeholder="waiver reason")
    if cols[4].button("Waive interviews", width="stretch"):
        send("waive", waiver_reason=reason)
else:
    st.caption("This run is closed.")

st.divider()
st.subheader("Phase 2 · Demand test (waitlist)")
st.caption("Enter the real number of waitlist sign-ups from your landing page. The target was fixed before the "
           "test started; the system never fills in or estimates this number.")
not_run = st.checkbox("I haven't run the test yet", key=f"notrun-{brief_id}")
dcols = st.columns(2)
signups = dcols[0].number_input("Sign-ups so far", min_value=0, step=1, disabled=not_run, key=f"signups-{brief_id}")
days = dcols[1].number_input("Days since the test started", min_value=0, step=1, key=f"days-{brief_id}")
if st.button("Send to the demand gate", disabled=not sid):
    try:
        out = api("POST", "/stages/validate/demand", headers=headers,
                  json={"brief_id": brief_id, "count": None if not_run else int(signups), "days_elapsed": int(days)})
        getattr(st, REC.get(out["outcome"], "info"))(f"**{out['outcome'].upper()}**: {out['reason']}")
        st.caption("Written to outputs/phase2_gate_demand.md. This is a recommendation; you decide.")
    except RuntimeError as e:
        st.error(str(e))
if not sid:
    st.caption("Enter your founder session above to send the count.")
