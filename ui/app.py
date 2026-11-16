"""Founder onboarding chat. Run the API first, then:  streamlit run ui/app.py"""

import os
import sys

import httpx
import streamlit as st

# API address: `streamlit run ui/app.py -- --api http://localhost:8010`, or the API_URL env var.
_args = sys.argv[1:]
API = _args[_args.index("--api") + 1] if "--api" in _args else os.environ.get("API_URL", "http://localhost:8000")
STATUS_BADGE = {"answered": "✅ answered", "from_document": "📄 from document", "inferred": "⚠️ inferred - check",
                "unknown": "❔ unknown"}

st.set_page_config(page_title="Venture OS · Founder onboarding", page_icon="🧭", layout="wide")


def api(method: str, path: str, **kw) -> dict:
    r = httpx.request(method, f"{API}{path}", timeout=120, **kw)
    if r.status_code >= 400:
        detail = r.json().get("detail", r.text) if "json" in r.headers.get("content-type", "") else r.text
        raise RuntimeError(detail)
    return r.json()


def start_session() -> None:
    out = api("POST", "/onboarding/sessions")
    st.session_state.sid = out["session_id"]
    st.session_state.chat = [("assistant", out["reply"])]
    st.session_state.last = out


def send(text: str) -> None:
    try:
        out = api("POST", f"/onboarding/sessions/{st.session_state.sid}/messages", json={"text": text})
        st.session_state.chat += [("user", text), ("assistant", out["reply"])]
        st.session_state.last = out
    except RuntimeError as e:
        st.session_state.chat += [("user", text), ("system", f"Error: {e}")]
    st.rerun()


if "sid" not in st.session_state:
    try:
        start_session()
    except Exception as e:  # noqa: BLE001
        st.error(f"Cannot reach the API at {API}: {e}")
        st.stop()

last = st.session_state.last
left, right = st.columns([3, 2], gap="large")

with right:
    st.subheader("Founder brief")
    version = last.get("version", 0)
    st.caption(f"Phase: **{last['phase']}** · Saved version: **{version or '-'}** · Model: {last.get('model', '')}")
    if last.get("unsaved_changes"):
        st.warning(f"Editing: changes are not saved until you reply 'yes' ('cancel' keeps version {version}).")
    fields = last.get("fields", {})
    from venture_os.onboarding.brief import FIELDS, label  # same field list as the backend

    rows = []
    for f in FIELDS:
        v = fields.get(f.name, {})
        rows.append({
            "field": label(f.name, last.get("lang", "en")) + (" *" if f.required else ""),
            "value": v.get("value") or "",
            "status": STATUS_BADGE.get(v.get("status", "unknown"), ""),
            "source": v.get("source", ""),
        })
    st.dataframe(rows, hide_index=True, width="stretch")
    if last.get("brief_id") and last["phase"] == "confirmed":
        st.success(f"Brief confirmed · version {version} · id {last['brief_id']}")
        if st.button("Edit brief"):
            send("edit")

    tags = last.get("tags", {})
    if tags:
        st.subheader("Tags")
        st.caption("Used to choose research sources. Correct in the chat, e.g. 'industry: education'.")
        st.dataframe([{"tag": label(k, last.get("lang", "en")),
                       "value": ", ".join(v["value"]) if isinstance(v["value"], list) else v["value"],
                       "by": v["basis"]} for k, v in tags.items()], hide_index=True, width="stretch")
    fups = last.get("followups", [])
    if fups:
        st.subheader("Follow-up questions")
        for i, f in enumerate(fups, 1):
            st.markdown(f"**q{i}.** {f['question']}  \n→ {f['answer'] or '_not answered_'}")
    if last.get("open_questions"):
        st.subheader("Open questions for research")
        st.caption("The Discover stage will look for these; the founder doesn't need to answer them.")
        for q in last["open_questions"]:
            st.markdown(f"- {q}")

    st.subheader("Documents")
    up = st.file_uploader("Upload a pitch deck, notes or plan", type=["pdf", "docx", "txt", "md"])
    if up is not None and st.button("Read this document"):
        try:
            out = api("POST", f"/onboarding/sessions/{st.session_state.sid}/documents",
                      files={"file": (up.name, up.getvalue())})
            st.session_state.chat += [("system", f"📄 Uploaded {up.name}"), ("assistant", out["reply"])]
            st.session_state.last = out
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
    for d in last.get("documents", []):
        st.write(f"📄 {d}")
    if st.button("Start over"):
        start_session()
        st.rerun()

with left:
    st.title("Tell us about your idea")
    for role, text in st.session_state.chat:
        if role == "system":
            st.caption(text)
        else:
            with st.chat_message("assistant" if role == "assistant" else "user"):
                st.markdown(text)
    prompt = st.chat_input("Type your answer… (English or Arabic)")
    if prompt:
        send(prompt)
