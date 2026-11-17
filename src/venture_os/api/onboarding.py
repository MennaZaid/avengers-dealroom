"""Onboarding chat API. The conversation logic lives in venture_os.onboarding.chat; this file only
loads and saves state. Runs under the vos_app database role."""

import hashlib
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from venture_os.api.db import connect
from venture_os.config import Settings
from venture_os.decision_log import entries_for
from venture_os.guardrails import redact
from venture_os.llm.client import chat_json, live_enabled
from venture_os.onboarding import chat
from venture_os.onboarding.analyst import LLMAnalyst, RuleAnalyst
from venture_os.onboarding.brief import OnboardingState
from venture_os.onboarding.documents import MAX_BYTES, DocumentError, extract_text
from venture_os.onboarding.extract import LLMExtractor, NullExtractor
from venture_os.outputs import outputs_dir, write_output

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def extractor():
    return LLMExtractor(chat_json, model=Settings().llm_model_extract) if live_enabled() else NullExtractor()


def analyst():
    return LLMAnalyst(chat_json, model=Settings().llm_model_extract) if live_enabled() else RuleAnalyst()


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class NewSession(BaseModel):
    lang: Literal["en", "ar"] = "en"  # language of the greeting; the founder's first message can change it


def _out(session_id, state: OnboardingState, reply: str, brief_id=None) -> dict:
    return {
        "session_id": str(session_id),
        "reply": reply,
        "phase": state.phase,
        "lang": state.lang,
        "fields": {k: v.model_dump() for k, v in state.fields.items()},
        "tags": {k: v.model_dump() for k, v in state.tags.items()},
        "followups": [f.model_dump() for f in state.followups],
        "open_questions": state.open_questions,
        "product_check": state.product_check,
        "budget": state.budget_parsed,
        "version": state.version,
        "unsaved_changes": state.phase == "confirming" and state.version > 0,
        "documents": state.documents,
        "brief_id": str(brief_id) if brief_id else None,
        "model": "live" if live_enabled() else "none (rule-based)",
    }


def _load(conn, session_id: UUID) -> tuple[OnboardingState, UUID | None]:
    row = conn.execute("SELECT state, brief_id FROM onboarding_sessions WHERE id = %s", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "session not found")
    state = OnboardingState.model_validate(row["state"])
    state.session_id = state.session_id or str(session_id)  # sessions created before ids were stored
    if row["brief_id"] and not state.brief_id:
        state.brief_id = str(row["brief_id"])
    return state, row["brief_id"]


def _save(conn, session_id: UUID, state: OnboardingState, brief_id=None) -> None:
    conn.execute(
        "UPDATE onboarding_sessions SET state = %s, brief_id = COALESCE(%s, brief_id), updated_at = now() WHERE id = %s",
        (state.model_dump_json(), brief_id, session_id),
    )


@router.post("/sessions", status_code=201)
def new_session(body: NewSession | None = None):
    sid = uuid4()
    state = OnboardingState(session_id=str(sid), lang=(body or NewSession()).lang)
    reply = chat.start(state)
    with connect("vos_app") as conn:
        conn.execute("INSERT INTO onboarding_sessions (id, state) VALUES (%s, %s)", (sid, state.model_dump_json()))
    return _out(sid, state, reply)


@router.get("/sessions/{session_id}")
def get_session(session_id: UUID):
    with connect("vos_app") as conn:
        state, brief_id = _load(conn, session_id)
    out = _out(session_id, state, "", brief_id)
    out["messages"] = [m.model_dump() for m in state.messages]
    return out


@router.post("/sessions/{session_id}/messages")
def post_message(session_id: UUID, body: MessageIn):
    with connect("vos_app") as conn:
        state, brief_id = _load(conn, session_id)
        version_before = state.version
        reply = chat.handle_message(state, body.text, extractor(), analyst())
        if state.version > version_before:  # the founder said "yes": save the next brief version
            if brief_id is None:
                brief_id = conn.execute("INSERT INTO briefs DEFAULT VALUES RETURNING id").fetchone()["id"]
                state.brief_id = str(brief_id)
            note = ("Confirmed by founder in onboarding chat" if state.version == 1
                    else "Edited by founder: " + ", ".join(state.last_changes))
            snap = state.snapshot()
            conn.execute(
                "INSERT INTO brief_versions (brief_id, version, fields, tags, followups, open_questions, "
                "product_check, budget, change_note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (brief_id, state.version, json.dumps(snap["fields"]), json.dumps(snap["tags"]),
                 json.dumps(snap["followups"]), json.dumps(snap["open_questions"]),
                 json.dumps(snap["product_check"]), json.dumps(snap["budget"]), note),
            )
            # Phase 1 starts from this brief: written by the run, never by hand.
            write_output(1, 0, "founder_brief", chat.brief_markdown(state, str(brief_id)))
        _save(conn, session_id, state, brief_id)
    return _out(session_id, state, reply, brief_id)


@router.post("/sessions/{session_id}/documents")
async def upload_document(session_id: UUID, file: UploadFile):
    data = await file.read(MAX_BYTES + 1)
    name = (file.filename or "upload").replace("/", "_").replace("\\", "_")[:200]
    try:
        text = redact(extract_text(name, data))  # card numbers / passwords are never stored
    except DocumentError as e:
        raise HTTPException(422, str(e)) from e
    sha = hashlib.sha256(data).hexdigest()
    with connect("vos_app") as conn:
        state, brief_id = _load(conn, session_id)
        seen = conn.execute("SELECT 1 FROM founder_documents WHERE session_id = %s AND sha256 = %s",
                            (session_id, sha)).fetchone()
        if seen:  # the same file again (e.g. a double click): don't read it twice
            reply = chat.already_read(state, name, analyst())
            _save(conn, session_id, state)
            return _out(session_id, state, reply, brief_id)
        conn.execute(
            "INSERT INTO founder_documents (session_id, filename, sha256, size_bytes, text) VALUES (%s,%s,%s,%s,%s)",
            (session_id, name, sha, len(data), text),
        )
        # After confirmation a document starts an edit; it is saved only when the founder says "yes" again.
        reply = chat.handle_document(state, name, text, extractor(), analyst())
        _save(conn, session_id, state)
    return _out(session_id, state, reply, brief_id)


@router.get("/sessions/{session_id}/log")
def session_log(session_id: UUID):
    """Decision-log entries of this conversation only (its session id, or its brief id for later stages)."""
    with connect("vos_app") as conn:
        _state, brief_id = _load(conn, session_id)
    return entries_for(str(session_id), str(brief_id) if brief_id else None)


@router.get("/sessions/{session_id}/outputs")
def session_outputs(session_id: UUID):
    """Files in outputs/ that belong to this conversation's confirmed brief (they contain its brief id)."""
    with connect("vos_app") as conn:
        _, brief_id = _load(conn, session_id)
    folder = outputs_dir()
    if not brief_id or not folder.exists():
        return []
    files = []
    for f in sorted(folder.glob("*")):
        text = f.read_text(encoding="utf-8", errors="replace")
        if str(brief_id) in text:
            files.append({"name": f.name, "text": text})
    return files


@router.get("/briefs/{brief_id}")
def get_brief(brief_id: UUID):
    """Latest brief version plus the version history. Stages pin the version they ran on; a newer version
    means their output is stale."""
    with connect("vos_app") as conn:
        rows = conn.execute(
            "SELECT version, fields, tags, followups, open_questions, product_check, budget, change_note, "
            "created_at "
            "FROM brief_versions "
            "WHERE brief_id = %s ORDER BY version", (brief_id,)).fetchall()
    if not rows:
        raise HTTPException(404, "brief not found")
    latest = rows[-1]
    return {
        "brief_id": str(brief_id),
        "version": latest["version"],
        "fields": latest["fields"],
        "tags": latest["tags"],
        "followups": latest["followups"],
        "open_questions": latest["open_questions"],
        "product_check": latest["product_check"],
        "budget": latest["budget"],
        "history": [{"version": r["version"], "change_note": r["change_note"], "created_at": r["created_at"]}
                    for r in rows],
    }
