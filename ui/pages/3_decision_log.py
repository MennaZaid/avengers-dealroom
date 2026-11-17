"""Decision log and outputs for THIS conversation only, as recorded by the pipeline.

Entries come from the API (GET /onboarding/sessions/{id}/log), filtered by this session's id and, once the
brief is confirmed, its brief id (later stages log under it). Other sessions and test runs are never shown.
"""

import json

import streamlit as st
from common import api, setup

setup("Decision log & outputs", "Every agent action and founder approval in this session, as recorded by the pipeline.")

sid = st.session_state.get("sid")
if not sid:
    st.info("No session yet. Start a founder brief on the onboarding page; this page then shows only that "
            "session's actions.")
    st.stop()

try:
    entries = api("GET", f"/onboarding/sessions/{sid}/log")
    outputs = api("GET", f"/onboarding/sessions/{sid}/outputs")
except RuntimeError as e:
    st.error(f"Decision log unavailable: {e}")
    st.stop()

st.caption(f"Session `{sid}`" + (f" · brief `{st.session_state.last['brief_id']}`"
                                 if st.session_state.get("last", {}).get("brief_id") else ""))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Actions logged", len(entries))
m2.metric("Model calls", sum(1 for e in entries if e.get("model")))
m3.metric("Founder approvals", sum(1 for e in entries if e.get("approved_by") == "founder"))
m4.metric("Cost (USD)", f"${sum(float(e.get('cost') or 0) for e in entries):.2f}")

tab_log, tab_out = st.tabs(["Decision log", "Outputs"])
with tab_log:
    if not entries:
        st.info("No actions logged in this session yet.")
    else:
        agents = sorted({e["agent"] for e in entries})
        pick = st.multiselect("Agent", agents, default=agents)
        rows = [{"time": e["timestamp"], "agent": e["agent"], "action": e["action"], "model": e.get("model") or "—",
                 "approved by": e.get("approved_by") or "—", "outcome": e.get("outcome") or "",
                 "sources": len(e.get("sources") or [])} for e in reversed(entries) if e["agent"] in pick]
        st.dataframe(rows, hide_index=True, width="stretch")
        with st.expander("Raw JSON"):
            st.json(entries[-20:])

with tab_out:
    if not outputs:
        st.info("No outputs for this session yet. Confirming the brief writes the first one.")
    else:
        names = [o["name"] for o in outputs]
        name = st.selectbox("File", names)
        text = outputs[names.index(name)]["text"]
        if name.endswith(".md"):
            st.markdown(text)
        elif name.endswith(".json"):
            st.json(json.loads(text))
        else:
            st.code(text)
