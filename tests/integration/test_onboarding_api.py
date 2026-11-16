"""Onboarding API against a real Postgres. Skipped when the database is unreachable."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from venture_os.config import Settings
from venture_os.onboarding.brief import REQUIRED

try:
    with psycopg.connect(Settings().database_url, connect_timeout=2) as _c:
        _c.execute("SELECT 1 FROM onboarding_sessions LIMIT 1")
        _ok = True
except Exception:  # noqa: BLE001
    _ok = False

pytestmark = pytest.mark.skipif(not _ok, reason="Postgres with onboarding tables not available")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "replay")  # no model: rule-based, zero cost
    from venture_os.api.main import app

    return TestClient(app)


def test_chat_with_document_to_confirmed_brief(client):
    s = client.post("/onboarding/sessions").json()
    sid = s["session_id"]
    assert s["phase"] == "collecting" and s["model"].startswith("none")

    doc = client.post(f"/onboarding/sessions/{sid}/documents",
                      files={"file": ("notes.txt", b"Some notes about the idea")}).json()
    assert doc["documents"] == ["notes.txt"]

    for _ in REQUIRED:
        out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "an answer"}).json()
    while out["phase"] == "collecting":  # optional fields, then follow-up questions
        out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "skip"}).json()
    assert out["phase"] == "confirming" and out["tags"]["languages"]["value"] == ["en"]
    assert len(out["followups"]) == 3
    out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "yes"}).json()
    assert out["phase"] == "confirmed" and out["brief_id"]

    with psycopg.connect(Settings().database_url) as c:
        v = c.execute("SELECT version, fields, tags FROM brief_versions WHERE brief_id = %s",
                      (out["brief_id"],)).fetchone()
        assert v[0] == 1 and v[1]["idea"]["value"] == "an answer" and "industries" in v[2]
        assert c.execute("SELECT count(*) FROM founder_documents WHERE session_id = %s", (sid,)).fetchone()[0] == 1

    # Edit after confirmation: a correction, then "yes", saves version 2 of the same brief.
    out2 = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "budget: 75,000 EGP"}).json()
    assert out2["phase"] == "confirming" and out2["unsaved_changes"]
    out2 = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "yes"}).json()
    assert out2["version"] == 2 and out2["brief_id"] == out["brief_id"]
    brief = client.get(f"/onboarding/briefs/{out['brief_id']}").json()
    assert brief["version"] == 2 and brief["fields"]["budget"]["value"] == "75,000 EGP"
    assert [h["version"] for h in brief["history"]] == [1, 2]
    assert "budget" in brief["history"][1]["change_note"]

    late = client.post(f"/onboarding/sessions/{sid}/documents", files={"file": ("x.txt", b"City: Giza")})
    assert late.status_code == 200 and late.json()["phase"] == "confirming"


def test_rejects_unsupported_upload(client):
    sid = client.post("/onboarding/sessions").json()["session_id"]
    r = client.post(f"/onboarding/sessions/{sid}/documents", files={"file": ("virus.exe", b"MZ")})
    assert r.status_code == 422


def test_same_document_twice_is_read_once(client):
    sid = client.post("/onboarding/sessions").json()["session_id"]
    first = client.post(f"/onboarding/sessions/{sid}/documents", files={"file": ("a.txt", b"Country: Kenya")}).json()
    again = client.post(f"/onboarding/sessions/{sid}/documents", files={"file": ("a.txt", b"Country: Kenya")}).json()
    assert first["documents"] == ["a.txt"] and again["documents"] == ["a.txt"]
    assert "already read" in again["reply"]
