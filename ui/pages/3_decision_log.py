"""Decision log (decision_log.json) and the files in outputs/, as written by the pipeline."""

import json
import os
from pathlib import Path

import streamlit as st
from common import setup

ROOT = Path(__file__).resolve().parents[2]
LOG = Path(os.environ.get("DECISION_LOG_PATH", ROOT / "decision_log.json"))
OUT = Path(os.environ.get("OUTPUTS_DIR", ROOT / "outputs"))

setup("Decision log & outputs", "Every agent action and every founder approval, as recorded by the pipeline.")

entries = []
if LOG.exists() and LOG.read_text(encoding="utf-8").strip():
    entries = json.loads(LOG.read_text(encoding="utf-8"))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Actions logged", len(entries))
m2.metric("Model calls", sum(1 for e in entries if e.get("model")))
m3.metric("Founder approvals", sum(1 for e in entries if e.get("approved_by") == "founder"))
m4.metric("Cost (USD)", f"${sum(float(e.get('cost') or 0) for e in entries):.2f}")

tab_log, tab_out = st.tabs(["Decision log", "Outputs"])
with tab_log:
    if not entries:
        st.info("No entries yet. Confirm a founder brief to create the first ones.")
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
    files = sorted(OUT.glob("*")) if OUT.exists() else []
    if not files:
        st.info("No outputs yet.")
    else:
        name = st.selectbox("File", [f.name for f in files])
        text = (OUT / name).read_text(encoding="utf-8")
        if name.endswith(".md"):
            st.markdown(text)
        elif name.endswith(".json"):
            st.json(json.loads(text))
        else:
            st.code(text)
