"""DealRoom VC copilot UI. Run: streamlit run dealroom_app.py"""
import json, sys, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT))
import streamlit as st
import yaml
import dealroom  # loads .env
from dealroom import dossier, analyst, research

DATA, OUT = ROOT / "data", ROOT / "outputs" / "dealroom"
APPROVALS = OUT / "approvals.json"
st.set_page_config(page_title="DealRoom VC Copilot", layout="wide")
st.title("DealRoom VC Copilot")
st.caption("USD 1,000,000 simulated fund · evidence from decks, videos and cited web research · every ticket needs a human decision")

room = dossier.build()
evidence, scores, rules, res, vals, alloc = dossier.load()
order = sorted(vals, key=lambda n: -vals[n]["weighted"])
tabs = st.tabs(["Portfolio", "Startups", "Research", "Analyst chat", "Approve tickets", "Rules"])

with tabs[0]:
    c1, c2, c3 = st.columns(3)
    c1.metric("Proposed deployment", f"${sum(alloc.values()):,}")
    c2.metric("Startups funded", f"{len(alloc)} of {len(vals)}")
    c3.metric("Reserve", f"${rules['reserve_usd']:,}")
    st.dataframe([{"Startup": n, "Score": vals[n]["weighted"], "Blended pre-money": f"${vals[n]['blended_premoney']:,.0f}",
                   "Their ask": f"${evidence[n]['ask_usd']:,}" if evidence[n].get("ask_usd") else "not stated",
                   "Ticket": f"${alloc[n]:,}" if n in alloc else "PASS",
                   "Stake": f"{alloc[n] / (vals[n]['blended_premoney'] + alloc[n]):.1%}" if n in alloc else "-"} for n in order],
                 hide_index=True, use_container_width=True)
    st.download_button("Download full data room (markdown)", room, "data_room.md")

with tabs[1]:
    name = st.selectbox("Startup", order)
    st.markdown("#### Edit scores (1 = far below a typical pre-seed, 3 = typical, 5 = far above)")
    cols = st.columns(len(dossier.CRITERIA))
    new = {c: cols[i].slider(c, 1, 5, int(scores[name][c]), key=f"{name}-{c}") for i, c in enumerate(dossier.CRITERIA)}
    why = st.text_area("Reasoning", scores[name]["why"], key=f"{name}-why")
    if st.button("Save scores"):
        scores[name] = {**new, "why": why}
        (DATA / "scores.yaml").write_text(yaml.safe_dump(scores, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
        st.success("Saved. Portfolio recomputed."); st.rerun()
    st.markdown((OUT / f"dossier_{name}.md").read_text(encoding="utf-8"))

with tabs[2]:
    st.write("The research agent writes 6 targeted web searches per startup (market, competitors, regulation, checkable claims), "
             "reads the results and records a verdict with the URLs it relied on. Free: SearXNG + Groq/Fanar.")
    pick = st.multiselect("Startups to (re)research", order)
    if st.button("Run research", disabled=not pick):
        for n in pick:
            with st.spinner(f"Researching {n}..."):
                out = research.research(n, evidence[n])
                (DATA / "research").mkdir(exist_ok=True)
                (DATA / "research" / f"{n}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        st.rerun()
    for n in order:
        fs = res.get(n, {}).get("findings", [])
        counts = {v: sum(f.get("verdict") == v for f in fs) for v in ("supported", "contradicted", "context", "unverified")}
        st.write(f"**{n}**: " + (", ".join(f"{k} {v}" for k, v in counts.items()) if fs else "not researched"))

with tabs[3]:
    st.write("Ask anything about the startups, the portfolio or the pitch. Name a startup to load its full deck and transcript.")
    if "chat" not in st.session_state:
        st.session_state.chat = []
    for m in st.session_state.chat:
        st.chat_message(m["role"]).markdown(m["content"])
    if q := st.chat_input("e.g. What would a judge attack in our Blaze ticket?"):
        st.chat_message("user").markdown(q)
        with st.spinner("Thinking..."):
            try:
                a = analyst.answer(q, st.session_state.chat)
            except Exception as exc:
                a = f"Model call failed: {exc}"
        st.chat_message("assistant").markdown(a)
        st.session_state.chat += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]

with tabs[4]:
    approvals = json.loads(APPROVALS.read_text(encoding="utf-8")) if APPROVALS.exists() else {}
    st.write("Proposed tickets need your decision. Nothing is final until approved here.")
    for n in order:
        if n not in alloc and n not in approvals:
            continue
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        c1.write(f"**{n}**: proposed ${alloc.get(n, 0):,}")
        amt = c2.number_input("Amount", 0, rules["fund_usd"], int(approvals.get(n, {}).get("amount", alloc.get(n, 0))), 10000, key=f"amt-{n}")
        for col, label, outcome in ((c3, "Approve", "approved"), (c4, "Reject", "rejected")):
            if col.button(label, key=f"{label}-{n}"):
                approvals[n] = {"amount": amt if outcome == "approved" else 0, "outcome": outcome, "approved_by": "team",
                                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
                APPROVALS.write_text(json.dumps(approvals, indent=1), encoding="utf-8"); st.rerun()
        if n in approvals:
            st.caption(f"{approvals[n]['outcome'].upper()}: ${approvals[n]['amount']:,} at {approvals[n]['timestamp']}")
    total = sum(a["amount"] for a in approvals.values())
    st.metric("Approved total", f"${total:,}", delta=f"${rules['fund_usd'] - total:,} left")

with tabs[5]:
    st.code((DATA / "rules.yaml").read_text(encoding="utf-8"), language="yaml")
