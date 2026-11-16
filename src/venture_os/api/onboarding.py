"""Onboarding chat API. The conversation logic lives in venture_os.onboarding.chat; this file only
loads and saves state. Runs under the vos_app database role."""

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from venture_os.api.db import connect
from venture_os.llm.client import chat_json, live_enabled
from venture_os.onboarding import chat
from venture_os.onboarding.analyst import LLMAnalyst, RuleAnalyst
from venture_os.onboarding.brief import OnboardingState
from venture_os.onboarding.documents import MAX_BYTES, DocumentError, extract_text
from venture_os.onboarding.extract import LLMExtractor, NullExtractor

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def extractor():
    return LLMExtractor(chat_json) if live_enabled() else NullExtractor()


def analyst():
    return LLMAnalyst(chat_json) if live_enabled() else RuleAnalyst()


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


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
    return OnboardingState.model_validate(row["state"]), row["brief_id"]


def _save(conn, session_id: UUID, state: OnboardingState, brief_id=None) -> None:
    conn.execute(
        "UPDATE onboarding_sessions SET state = %s, brief_id = COALESCE(%s, brief_id), updated_at = now() WHERE id = %s",
        (state.model_dump_json(), brief_id, session_id),
    )


@router.post("/sessions", status_code=201)
def new_session():
    state = OnboardingState()
    reply = chat.start(state)
    with connect("vos_app") as conn:
        sid = conn.execute(
            "INSERT INTO onboarding_sessions (state) VALUES (%s) RETURNING id", (state.model_dump_json(),)
        ).fetchone()["id"]
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
            note = ("Confirmed by founder in onboarding chat" if state.version == 1
                    else "Edited by founder: " + ", ".join(state.last_changes))
            snap = state.snapshot()
            conn.execute(
                "INSERT INTO brief_versions (brief_id, version, fields, tags, followups, open_questions, "
                "change_note) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (brief_id, state.version, json.dumps(snap["fields"]), json.dumps(snap["tags"]),
                 json.dumps(snap["followups"]), json.dumps(snap["open_questions"]), note),
            )
        _save(conn, session_id, state, brief_id)
    return _out(session_id, state, reply, brief_id)


@router.post("/sessions/{session_id}/documents")
async def upload_document(session_id: UUID, file: UploadFile):
    data = await file.read(MAX_BYTES + 1)
    name = (file.filename or "upload").replace("/", "_").replace("\\", "_")[:200]
    try:
        text = extract_text(name, data)
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


@router.get("/briefs/{brief_id}")
def get_brief(brief_id: UUID):
    """Latest brief version plus the version history. Stages pin the version they ran on; a newer version
    means their output is stale."""
    with connect("vos_app") as conn:
        rows = conn.execute(
            "SELECT version, fields, tags, followups, open_questions, change_note, created_at FROM brief_versions "
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
        "history": [{"version": r["version"], "change_note": r["change_note"], "created_at": r["created_at"]}
                    for r in rows],
    }
