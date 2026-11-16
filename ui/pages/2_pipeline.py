"""Pipeline: the six phases and their gates.

Placeholder until the orchestrator and gates land (owner: Roufayda). Replace the body below; keep `setup()` and
`phase_bar()` from common.py. Every phase that is not built is shown as STUBBED, never as working.
"""

import streamlit as st
from common import card, chip, phase_bar, setup

brief = st.session_state.get("brief") or {}
setup("Pipeline", "Six phases, each ending at a gate the founder approves.", active_phase=None)

STATUS = {0: "Working", 1: "STUBBED", 2: "STUBBED", 3: "STUBBED", 4: "STUBBED", 5: "MOCKED", 6: "STUBBED"}
phase_bar(1 if brief.get("phase") == "confirmed" else 0, status={k: f" · {v}" for k, v in STATUS.items()})

if brief.get("phase") == "confirmed":
    st.success(f"Founder brief confirmed (version {brief.get('version')}). It is the input to phase 1.")
else:
    st.info("Confirm the founder brief first: no phase can start without it.")
    st.page_link("pages/1_onboarding.py", label="Go to the founder brief →")

st.warning("STUBBED: the orchestrator, gates and phase agents are being built. This page shows the layout only; "
           "nothing below is a real result.")

PHASES = [
    (1, "Discover", "Find opportunities with sourced claims; Mom-Test interview script.",
     "phase1_step1_opportunities.md · phase1_gate_decision.md"),
    (2, "Validate", "Lean Canvas from evidenced pains; landing page with a pre-set waitlist target.",
     "phase2_step1_lean_canvas.md · phase2_gate_decision.md"),
    (3, "Build", "PRD and an MVP from a fixed template.", "phase3_step1_prd.md"),
    (4, "Commercial setup", "Price hypotheses; draft terms, privacy and refund policies.", "phase4_step1_pricing.md"),
    (5, "Sell, deliver, get paid", "Store page draft; test-mode checkout, idempotent delivery, refunds.",
     "payment_test_log.md"),
    (6, "Operate and learn", "Persevere-or-pivot memo from real metrics.", "phase6_step1_persevere_or_pivot.md"),
]
cols = st.columns(3)
for i, (n, name, what, out) in enumerate(PHASES):
    kind = "stub"
    with cols[i % 3]:
        st.markdown(card(f"Phase {n} · {name}", what, chip(STATUS[n], kind)), unsafe_allow_html=True)
        st.caption(f"Outputs: {out}")
        st.button("Run phase", key=f"run{n}", disabled=True, help="Not built yet (STUBBED)")
