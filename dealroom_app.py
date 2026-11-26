"""DealRoom VC Copilot, by Team Avengers. Run: streamlit run dealroom_app.py"""
import json, os, sys, html, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import streamlit as st

st.set_page_config(page_title="Avengers Capital · DealRoom", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="collapsed")
# Streamlit Cloud: keys live in st.secrets; copy them into the environment before the LLM client loads.
try:
    for k, v in st.secrets.items():
        if isinstance(v, str):
            os.environ.setdefault(k, v)
except Exception:
    pass

import yaml
import dealroom  # loads a local .env when present
from dealroom import dossier, analyst, research, forecast

DATA, OUT = ROOT / "data", ROOT / "outputs" / "dealroom"
APPROVALS = OUT / "approvals.json"
esc = html.escape

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;500;600&display=swap');
:root { --navy:#14213D; --navy2:#1F3158; --gold:#B08D3C; --gold2:#D9BC72; --ivory:#F7F5F0; --card:#FFFFFF;
        --line:#E4DDCC; --muted:#5B6478; --green:#1F6F4A; --red:#8B1E2D; }
html, body, [class*="css"], .stMarkdown, p, li, label { font-family:'Inter',sans-serif; }
.block-container { padding-top:1.2rem; padding-bottom:3rem; max-width:1180px; }
h1,h2,h3,h4 { font-family:'Playfair Display',serif !important; color:var(--navy); letter-spacing:.2px; }
.hero { background:linear-gradient(135deg,var(--navy) 0%,var(--navy2) 70%,#2A3F6E 100%); color:#fff;
        border-radius:18px; padding:28px 30px 24px; border-bottom:4px solid var(--gold); margin-bottom:18px;
        box-shadow:0 10px 30px rgba(20,33,61,.18); }
.hero .kicker { color:var(--gold2); font-size:.78rem; letter-spacing:3px; text-transform:uppercase; font-weight:600; }
.hero h1 { color:#fff !important; font-size:2.1rem; margin:.25rem 0 .35rem; }
.hero p { color:#D5DAE6; margin:0; font-size:.95rem; }
.hero .team { margin-top:12px; display:inline-block; border:1px solid var(--gold); color:var(--gold2);
              border-radius:999px; padding:4px 14px; font-size:.8rem; letter-spacing:1px; }
.kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:6px 0 18px; }
.kpi { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; }
.kpi .l { color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:1.5px; }
.kpi .v { font-family:'Playfair Display',serif; color:var(--navy); font-size:1.55rem; font-weight:700; }
.deal { background:var(--card); border:1px solid var(--line); border-left:5px solid var(--gold); border-radius:14px;
        padding:14px 18px; margin-bottom:10px; display:grid; grid-template-columns:1.6fr 1fr 1fr 1fr 1fr; gap:10px; align-items:center; }
.deal.pass { border-left-color:#B9B2A3; opacity:.8; }
.deal .n { font-family:'Playfair Display',serif; font-size:1.15rem; color:var(--navy); font-weight:700; }
.deal .s { color:var(--muted); font-size:.78rem; }
.deal .l { color:var(--muted); font-size:.68rem; text-transform:uppercase; letter-spacing:1.2px; }
.deal .v { font-weight:600; color:var(--navy); }
.tag { display:inline-block; border-radius:999px; padding:2px 10px; font-size:.72rem; font-weight:600; letter-spacing:.5px; }
.tag.in { background:#E8F2EC; color:var(--green); } .tag.out { background:#F3E6E8; color:var(--red); }
.v-supported{color:var(--green);font-weight:600} .v-contradicted{color:var(--red);font-weight:600}
.v-context{color:var(--navy2);font-weight:600} .v-unverified{color:#8A7A55;font-weight:600}
.stTabs [data-baseweb="tab-list"] { gap:4px; overflow-x:auto; flex-wrap:nowrap; scrollbar-width:none; }
.stTabs [data-baseweb="tab"] { background:#ECE7DC; border-radius:10px 10px 0 0; padding:8px 16px; white-space:nowrap; }
.stTabs [aria-selected="true"] { background:var(--navy) !important; }
.stTabs [aria-selected="true"] p { color:#fff !important; }
.stButton>button, .stDownloadButton>button { background:var(--navy); color:#fff; border:1px solid var(--gold);
        border-radius:10px; font-weight:600; min-height:44px; }
.stButton>button:hover, .stDownloadButton>button:hover { background:var(--gold); color:var(--navy); border-color:var(--gold); }
.foot { text-align:center; color:var(--muted); font-size:.78rem; margin-top:30px; letter-spacing:1px; }
.foot b { color:var(--gold); }
@media (max-width: 760px) {
  .block-container { padding-left:.8rem; padding-right:.8rem; }
  .hero { padding:20px 18px; border-radius:14px; } .hero h1 { font-size:1.55rem; }
  .kpis { grid-template-columns:repeat(2,1fr); } .kpi .v { font-size:1.25rem; }
  .deal { grid-template-columns:1fr 1fr; } .deal .head { grid-column:1 / -1; }
}
</style>""", unsafe_allow_html=True)

room = dossier.build()
evidence, scores, rules, res, vals, alloc = dossier.load()
order = sorted(vals, key=lambda n: -vals[n]["weighted"])
money = lambda x: f"${x:,.0f}" if x else "—"

st.markdown(f"""<div class="hero"><div class="kicker">Avengers Capital · The DealRoom 2026</div>
<h1>Investment Committee Console</h1>
<p>A ${rules['fund_usd']:,} simulated fund. Founder claims checked word for word, markets researched with cited sources,
every ticket signed off by a human.</p>
<div class="team">TEAM AVENGERS · ASSEMBLE</div></div>""", unsafe_allow_html=True)

fc = forecast.forecast(vals, alloc, rules)
post = lambda n, a: vals[n]["blended_premoney"] + max(evidence[n].get("ask_usd") or 0, a)
tabs = st.tabs(["Portfolio", "Year 5", "Startups", "Research", "Analyst", "Approve", "Glossary", "Rules"])

with tabs[0]:
    researched = sum(1 for n in order if res.get(n))
    st.markdown(f"""<div class="kpis">
<div class="kpi"><div class="l">Deployed</div><div class="v">{money(sum(alloc.values()))}</div></div>
<div class="kpi"><div class="l">Reserve</div><div class="v">{money(rules['fund_usd'] - sum(alloc.values()))}</div></div>
<div class="kpi"><div class="l">Backed</div><div class="v">{len(alloc)} / {len(vals)}</div></div>
<div class="kpi"><div class="l">Researched</div><div class="v">{researched} / {len(vals)}</div></div></div>""", unsafe_allow_html=True)
    cards = []
    for n in order:
        v, a, e = vals[n], alloc.get(n, 0), evidence[n]
        stake = f"{a / post(n, a):.1%}" if a else "—"
        tag = '<span class="tag in">INVEST</span>' if a else '<span class="tag out">PASS</span>'
        cards.append(f"""<div class="deal {'' if a else 'pass'}">
<div class="head"><div class="n">{esc(n)} {tag}</div><div class="s">{esc(e['sector'])}</div></div>
<div><div class="l">Score</div><div class="v">{v['weighted']} / 5</div></div>
<div><div class="l">Pre-money</div><div class="v">{money(v['blended_premoney'])}</div></div>
<div><div class="l">Their ask</div><div class="v">{money(e.get('ask_usd')) if e.get('ask_usd') else 'n/a'}</div></div>
<div><div class="l">Ticket · stake</div><div class="v">{money(a) if a else 'Pass'} · {stake}</div></div></div>""")
    st.markdown("".join(cards), unsafe_allow_html=True)
    st.download_button("Download the full data room", room, "data_room.md", use_container_width=True)

with tabs[2]:
    name = st.selectbox("Startup", order)
    st.markdown(f"#### Scorecard · {name}")
    st.caption("1 = far below a typical pre-seed startup · 3 = typical · 5 = far above")
    new = {}
    for i in range(0, len(dossier.CRITERIA), 4):
        cols = st.columns(4)
        for j, c in enumerate(dossier.CRITERIA[i:i + 4]):
            new[c] = cols[j].slider(c.replace("_", " ").title(), 1, 5, int(scores[name][c]), key=f"{name}-{c}")
    why = st.text_area("Investment reasoning", scores[name]["why"], key=f"{name}-why")
    if st.button("Save scorecard", use_container_width=True):
        scores[name] = {**new, "why": why}
        (DATA / "scores.yaml").write_text(yaml.safe_dump(scores, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
        st.success("Saved. The portfolio has been recalculated."); st.rerun()
    with st.expander("Full dossier: claims and research", expanded=True):
        st.markdown((OUT / f"dossier_{name}.md").read_text(encoding="utf-8"))

with tabs[3]:
    st.markdown("#### Independent research")
    st.caption("For each startup, 6 targeted web searches (market, competitors, regulation, checkable claims). "
               "Every finding cites only links the search returned.")
    for n in order:
        fs = res.get(n, {}).get("findings", [])
        with st.expander(f"{n} · {len(fs)} findings" if fs else f"{n} · not researched"):
            for f in fs:
                vd = str(f.get("verdict", "")).lower()
                srcs = " ".join(f"[source {i + 1}]({u})" for i, u in enumerate(f.get("sources", [])))
                st.markdown(f"<span class='v-{vd}'>{vd.upper()}</span> · **{esc(str(f.get('topic', '')).title())}**: "
                            f"{esc(f.get('finding', ''))} {srcs}", unsafe_allow_html=True)
                if f.get("risk_flag"):
                    st.caption("Risk: " + f["risk_flag"])
    search_ok = bool(os.environ.get("SEARXNG_URL"))
    pick = st.multiselect("Re-run research for", order, disabled=not search_ok)
    if not search_ok:
        st.info("Re-running research needs the local search engine (SearXNG), so it only works on the team laptop.")
    if st.button("Run research", disabled=not pick or not search_ok, use_container_width=True):
        for n in pick:
            with st.spinner(f"Researching {n}..."):
                out = research.research(n, evidence[n])
                (DATA / "research").mkdir(exist_ok=True)
                (DATA / "research" / f"{n}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        st.rerun()

with tabs[4]:
    st.markdown("#### Ask the analyst")
    st.caption("Answers come only from our data room. Name a startup to load its full deck and transcript. "
               "Check facts before using them on a slide.")
    if "chat" not in st.session_state:
        st.session_state.chat = []
    starters = ["Which ticket is the weakest and why?", "What would a judge attack in our Blaze ticket?",
                "Rank the 8 startups by evidence quality."]
    picked = None
    cols = st.columns(len(starters))
    for i, s in enumerate(starters):
        if cols[i].button(s, key=f"st{i}", use_container_width=True):
            picked = s
    for m in st.session_state.chat:
        st.chat_message(m["role"], avatar="🛡️" if m["role"] == "assistant" else "💼").markdown(m["content"])
    q = st.chat_input("Ask about any startup, ticket or risk...") or picked
    if q:
        st.chat_message("user", avatar="💼").markdown(q)
        with st.spinner("The analyst is reviewing the data room..."):
            try:
                a = analyst.answer(q, st.session_state.chat)
            except Exception as exc:
                a = f"The model could not be reached ({type(exc).__name__}). Check the API keys in Secrets."
        st.chat_message("assistant", avatar="🛡️").markdown(a)
        st.session_state.chat += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]

with tabs[5]:
    approvals = json.loads(APPROVALS.read_text(encoding="utf-8")) if APPROVALS.exists() else {}
    st.markdown("#### Investment committee sign-off")
    st.caption("Nothing is final until approved here. On the hosted app, approvals can reset when it restarts, so keep a record.")
    for n in order:
        if n not in alloc and n not in approvals:
            continue
        with st.container(border=True):
            st.markdown(f"**{n}** · proposed {money(alloc.get(n, 0))}")
            amt = st.number_input("Ticket (USD)", 0, rules["fund_usd"],
                                  int(approvals.get(n, {}).get("amount", alloc.get(n, 0))), 10000, key=f"amt-{n}")
            c1, c2 = st.columns(2)
            for col, label, outcome in ((c1, "Approve", "approved"), (c2, "Reject", "rejected")):
                if col.button(label, key=f"{label}-{n}", use_container_width=True):
                    approvals[n] = {"amount": amt if outcome == "approved" else 0, "outcome": outcome, "approved_by": "team",
                                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
                    APPROVALS.parent.mkdir(parents=True, exist_ok=True)
                    APPROVALS.write_text(json.dumps(approvals, indent=1), encoding="utf-8"); st.rerun()
            if n in approvals:
                st.caption(f"{approvals[n]['outcome'].upper()} · {money(approvals[n]['amount'])} · {approvals[n]['timestamp']}")
    total = sum(a["amount"] for a in approvals.values())
    st.metric("Approved so far", money(total) if total else "$0", delta=f"{money(rules['fund_usd'] - total)} left")

with tabs[1]:
    st.markdown(f"""<div class="kpis">
<div class="kpi"><div class="l">Y5 base case</div><div class="v">${fc['base']/1e6:.1f}M</div></div>
<div class="kpi"><div class="l">Base multiple</div><div class="v">{fc['moic_base']:.1f}x</div></div>
<div class="kpi"><div class="l">Y5 downside</div><div class="v">${fc['down']/1e6:.2f}M</div></div>
<div class="kpi"><div class="l">Downside multiple</div><div class="v">{fc['moic_down']:.2f}x</div></div></div>""", unsafe_allow_html=True)
    st.markdown(forecast.markdown(fc))
    st.markdown(forecast.benchmarks_markdown())
    st.caption("Edit year-5 company values, burn rates and dilution in data/forecast.yaml. Words unclear? See the Glossary tab.")

with tabs[6]:
    st.markdown((ROOT / "for-the-team" / "GLOSSARY.md").read_text(encoding="utf-8"))

with tabs[7]:
    st.markdown("#### Fund rules")
    st.code((DATA / "rules.yaml").read_text(encoding="utf-8"), language="yaml")

st.markdown("<div class='foot'>Built by <b>Team Avengers</b> · Assemble · The DealRoom, ES × MADS, AUC</div>",
            unsafe_allow_html=True)
