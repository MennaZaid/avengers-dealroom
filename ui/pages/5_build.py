"""Phase 3 Build: starts after the founder approved Discover; runs all agents with no approval inside the stage;
ends at the build gate, where the founder decides once (Go / Repeat / Stop)."""

import time

import streamlit as st
import streamlit.components.v1 as components
from common import API, api, phase_bar, setup

STATUS = {"running": "⏳ building", "awaiting_approval": "🟡 waiting for your decision", "approved": "✅ go",
          "revision_requested": "🔁 repeat", "rejected": "⛔ stop", "failed": "❌ failed"}
REC = {"go": "success", "repeat": "warning", "stop": "error"}
STEPS = ["Build inputs", "Requirements", "MVP plan", "Validation", "MVP", "Tests", "User guide", "Evidence summary"]

setup("Pipeline · Phase 3 Build", "From validated evidence to a tested MVP. One founder decision at the end.")
phase_bar(3, status={0: " · Working", 1: " · Working", 2: " · STUBBED", 3: " · Working", 4: " · STUBBED",
                     5: " · MOCKED", 6: " · STUBBED"})
st.caption("Agents: build inputs → requirements → MVP plan → validation → MVP → tests → docs. Nobody approves "
           "inside the stage; the founder decides once at the build gate. Nothing is published, sent or spent.")
try:
    briefs = api("GET", "/stages/briefs")
except RuntimeError as e:
    st.error(f"Cannot reach the API at {API}: {e}")
    st.stop()
if not briefs:
    st.info("No confirmed brief yet. Confirm one on the onboarding page first.")
    st.stop()

labels = {b["brief_id"]: f"{(b['idea'] or 'untitled')[:70]} · {b['country_code'] or '?'} · v{b['version']}"
          for b in briefs}
keys = list(labels)
confirmed = (st.session_state.get("brief") or {}).get("id")
brief_id = st.selectbox("Brief", keys, format_func=labels.get, index=keys.index(confirmed) if confirmed in keys else 0)
latest = next(b["version"] for b in briefs if b["brief_id"] == brief_id)
sid = st.text_input("Your founder session (from the onboarding page; needed to decide)",
                    value=st.session_state.get("sid", ""), type="password")
headers = {"X-Founder-Session": sid} if sid else {}

discover = [r for r in api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "discover"})
            if r["brief_version"] == latest]
runs = api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "build"})
current = [r for r in runs if r["brief_version"] == latest]

if not current:
    if not any(r["status"] == "approved" for r in discover):
        st.info(f"Build starts after you approve Phase 1 (Discover) for brief v{latest}. "
                "Phase 2 (Validate) is not built yet, so Build follows Discover.")
        st.page_link("pages/2_pipeline.py", label="Go to Phase 1 Discover →")
        st.stop()
    st.success("Discover is approved. Build uses its sourced claims as evidence.")
    if st.button("▶ Start Phase 3 Build", type="primary"):
        try:
            api("POST", "/stages/build/runs", json={"brief_id": brief_id})
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
    st.caption("About 6 minutes with the local model on a CPU.")
    st.stop()

run = current[0]
build = (run["output"] or {}).get("build") or {}
st.markdown(f"**Status:** {STATUS.get(run['status'], run['status'])} · **Brief version:** v{run['brief_version']}")
if run["stale"]:
    st.warning(f"Stale: the brief is now v{run['latest_brief_version']}. Approve Discover again, then rebuild.")
if run["status"] == "running":
    started = run["created_at"][:19].replace("T", " ")
    st.info(f"Building since {started}: the agents run one after another, about 6 minutes on CPU.")
    time.sleep(5)
    st.rerun()
if run["status"] == "failed":
    st.error(build.get("error") or "the build run failed")
    st.stop()

gate = build.get("gate") or {}
if gate:
    getattr(st, REC.get(gate["outcome"], "info"))(f"**Recommendation: {gate['outcome'].upper()}** — {gate['reason']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Template", build.get("template") or "-")
    c2.metric("MVP tests passed", f"{int(gate.get('actual') or 0)} / {int(gate.get('target') or 0)}")
    c3.metric("Plan rounds", build.get("plan_rounds", 0))
    c4.metric("Time", f"{build.get('seconds', 0):.0f} s")

files = build.get("files") or {}
mvp = files.get("phase3_step5_mvp.html")
tabs = st.tabs(["MVP", *[s for s in STEPS if s != "MVP"], "Gate"])
with tabs[0]:
    if mvp:
        st.caption("The MVP as built: one HTML file, data stays on the device, payments MOCKED.")
        st.download_button("⬇ Download the MVP (one HTML file)", mvp, file_name="mvp.html", mime="text/html")
        components.html(mvp, height=640, scrolling=True)
    else:
        st.info("No MVP was built in this run.")
names = ["phase3_step1_build_inputs.md", "phase3_step2_requirements.md", "phase3_step3_mvp_plan.md",
         "phase3_step4_validation.md", "phase3_step6_test_report.md", "phase3_step7_user_guide.md",
         "phase3_step8_evidence_summary.md", "phase3_gate_build.md"]
for tab, name in zip(tabs[1:], names, strict=True):
    with tab:
        st.markdown(files.get(name) or "_not written in this run_")

st.divider()
st.subheader("Your decision")
for d in run["decisions"]:
    st.caption(f"{d['created_at'][:19]} · {d['decision']}" + (f": {d['note']}" if d["note"] else ""))
if run["status"] == "revision_requested" and st.button("▶ Build again", type="primary"):
    try:
        api("POST", "/stages/build/runs", json={"brief_id": brief_id})
        st.rerun()
    except RuntimeError as e:
        st.error(str(e))
if run["status"] in ("awaiting_approval", "revision_requested"):
    note = st.text_area("Note", key=f"note-{run['id']}")
    cols = st.columns(3)

    def send(decision):
        try:
            api("POST", f"/stages/runs/{run['id']}/decision", headers=headers, json={"decision": decision, "note": note})
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
    if cols[0].button("Go", width="stretch"):
        send("approve")
    if cols[1].button("Repeat", width="stretch"):
        send("revise")
    if cols[2].button("Stop", width="stretch"):
        send("reject")
else:
    st.caption("This run is closed.")
