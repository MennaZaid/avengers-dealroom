"""Phase 2 Validate: Lean Canvas -> demand test (declared before measuring) -> landing-page draft (MOCKED) ->
the founder's sign-up count -> demand gate -> the founder's decision. Uses the stage API only.

render(brief_id, session_id) is also shown inside the pipeline page once Discover is approved."""

import streamlit as st
import streamlit.components.v1 as components
from common import api, setup

STAGE_STATUS = {"queued": "⏳ queued", "lean_canvas": "⏳ building the Lean Canvas",
                "landing_page": "⏳ declaring the demand test and drafting the landing page",
                "awaiting_signups": "🟡 waiting for your sign-up count", "gated": "🟡 waiting for your decision",
                "failed": "❌ failed"}
REC = {"go": st.success, "repeat": st.warning, "pivot": st.warning, "stop": st.error}


def _decide(run_id: str, decision: str, headers: dict, note: str) -> None:
    try:
        api("POST", f"/stages/runs/{run_id}/decision", headers=headers, json={"decision": decision, "note": note})
        st.rerun()
    except RuntimeError as e:
        st.error(str(e))


def render(brief_id: str, session_id: str) -> None:
    headers = {"X-Founder-Session": session_id} if session_id else {}
    st.subheader("Phase 2 · Validate")
    runs = api("GET", "/stages/runs", params={"brief_id": brief_id, "stage": "validate"})
    if not runs or st.button("Run Validate again", key=f"again-{brief_id}", disabled=not runs):
        if not runs:
            st.caption("Builds the Lean Canvas, fixes the demand-test target, then drafts the landing page.")
        if runs or st.button("Start Validate", key=f"start-{brief_id}", type="primary"):
            try:
                api("POST", "/stages/validate/runs", json={"brief_id": brief_id})
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))  # e.g. Discover not approved for this brief version
        if not runs:
            return
    run = runs[0]
    v = (run.get("output") or {}).get("validate") or {}
    status = "approved" if run["status"] == "approved" else v.get("status", run["status"])
    st.markdown(f"**Status:** {STAGE_STATUS.get(status, run['status'])} · brief v{run['brief_version']}"
                + (" · **Stale**: the brief changed, run Validate again" if run.get("stale") else ""))
    if status == "failed":
        st.error(v.get("error", "failed"))
        return
    if status in ("queued", "lean_canvas", "landing_page"):
        st.info("Working in the background. This page does not wait; refresh to see progress.")
        st.button("Refresh", key=f"refresh-{run['id']}")
        return

    with st.expander("Lean Canvas (entries without evidence are labelled ASSUMPTION)", expanded=False):
        st.markdown(v.get("canvas_md") or "")
    t = v.get("demand_test") or {}
    st.markdown(f"**Demand test (set before measuring):** {t.get('target')} {t.get('metric')} in {t.get('days')} "
                f"days · declared {t.get('declared_at')}")
    with st.expander("Landing-page draft · MOCKED: not published", expanded=False):
        st.warning("MOCKED: this draft is not published anywhere. Publishing needs your separate approval.")
        components.html(v.get("draft_html") or "", height=520, scrolling=True)

    if run["status"] in ("running", "awaiting_approval", "revision_requested") and not run.get("stale"):
        with st.form(f"signups-{run['id']}"):
            c1, c2 = st.columns(2)
            actual = c1.number_input("Waitlist sign-ups (entered by the founder)", min_value=0, step=1, value=None)
            days = c2.number_input("Days since the test started", min_value=0, step=1, value=None)
            if st.form_submit_button("Send to the demand gate", disabled=not session_id):
                if actual is None or days is None:
                    st.error("Enter both numbers: the count is never filled in for you.")
                else:
                    try:
                        api("POST", f"/stages/runs/{run['id']}/signups", headers=headers,
                            json={"actual": int(actual), "days_elapsed": int(days)})
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))
        if not session_id:
            st.caption("Enter your founder session to send the count and decide.")

    g = v.get("gate")
    if g:
        REC.get(g["outcome"], st.info)(f"**Demand gate: {g['outcome'].upper()}** · target {g.get('target'):g} · "
                                       f"actual {g.get('actual'):g} (founder-reported) · {g['reason']}")
        st.caption(f"Rule (fixed before the result): {g.get('rule')}")
    for d in run.get("decisions") or []:
        st.caption(f"{d['created_at'][:19]} · your decision: {d['decision']}" + (f": {d['note']}" if d["note"] else ""))
    if run["status"] in ("awaiting_approval", "revision_requested") and not run.get("stale"):
        note = st.text_input("Note", key=f"vnote-{run['id']}")
        c1, c2, c3 = st.columns(3)
        if c1.button("Go: continue to Build", key=f"vgo-{run['id']}", disabled=not session_id):
            _decide(run["id"], "approve", headers, note)
        if c2.button("Repeat: run the test again", key=f"vrep-{run['id']}", disabled=not session_id):
            _decide(run["id"], "revise", headers, note)
        if c3.button("Stop", key=f"vstop-{run['id']}", disabled=not session_id):
            _decide(run["id"], "reject", headers, note)
    if run["status"] == "approved":
        st.success("Validate approved: Phase 3 Build can start.")
        st.page_link("pages/5_build.py", label="Go to Build →")


if __name__ == "__main__":  # opened as its own page
    setup("Phase 2 · Validate", "Lean Canvas, a demand test fixed before measuring, and a MOCKED landing page.")
    briefs = api("GET", "/stages/briefs")
    if not briefs:
        st.info("Confirm a founder brief first.")
        st.stop()
    labels = {b["brief_id"]: f"{(b['idea'] or 'untitled')[:70]} · v{b['version']}" for b in briefs}
    keys = list(labels)
    confirmed = (st.session_state.get("brief") or {}).get("id")
    bid = st.selectbox("Brief", keys, format_func=labels.get, index=keys.index(confirmed) if confirmed in keys else 0)
    sid = st.text_input("Your founder session", value=st.session_state.get("sid", ""), type="password")
    render(bid, sid)
