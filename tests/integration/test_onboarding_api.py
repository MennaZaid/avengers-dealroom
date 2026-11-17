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


def test_confirmed_brief_writes_output_and_founder_approval(client):
    import os
    from pathlib import Path

    from venture_os.decision_log import read_log

    sid = client.post("/onboarding/sessions").json()["session_id"]
    out = client.post(f"/onboarding/sessions/{sid}/messages",
                      json={"text": "idea: an app to book home cleaners"}).json()
    while out["phase"] == "collecting":
        out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "an answer"}).json()
        if out["phase"] == "collecting" and ("Optional" in out["reply"] or "(" in out["reply"]):
            out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "skip"}).json()
    assert out["product_check"]["status"] == "allowed"
    out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "yes"}).json()
    assert out["phase"] == "confirmed"

    brief_file = Path(os.environ["OUTPUTS_DIR"]) / "phase1_step0_founder_brief.md"
    assert brief_file.exists() and out["brief_id"] in brief_file.read_text(encoding="utf-8")
    assert client.get(f"/onboarding/briefs/{out['brief_id']}").json()["product_check"]["status"] == "allowed"
    assert any(e["action"] == "confirm_brief" and e["approved_by"] == "founder" for e in read_log())


def test_excluded_product_is_not_saved(client):
    sid = client.post("/onboarding/sessions").json()["session_id"]
    out = client.post(f"/onboarding/sessions/{sid}/messages",
                      json={"text": "idea: an online shop selling handmade rugs"}).json()
    for _ in range(20):
        if out["phase"] != "collecting":
            break
        out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "skip"}).json()
    out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "yes"}).json()
    assert out["phase"] == "confirming" and out["brief_id"] is None and out["product_check"]["status"] == "excluded"


def test_pipeline_can_load_the_confirmed_brief_and_see_staleness(client):
    from venture_os.onboarding.briefs import is_stale, load_brief

    sid = client.post("/onboarding/sessions").json()["session_id"]
    out = client.post(f"/onboarding/sessions/{sid}/messages",
                      json={"text": "idea: an online course for Instagram marketing\nbudget: 20 ألف جنيه\n"
                                    "country: Egypt"}).json()
    for _ in range(30):
        if out["phase"] != "collecting":
            break
        out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "skip"}).json()
    out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "yes"}).json()
    bid = out["brief_id"]
    brief = load_brief(bid)
    assert brief.version == 1 and brief.allowed and brief.tag("country_code") == "EG"
    assert brief.budget["min"] == 20000 and brief.budget["currency"] == "EGP"
    assert brief.known("time_available") is None and "time_available" in brief.unknown_fields
    assert not is_stale(bid, 1)
    client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "budget: 30 ألف جنيه"})
    client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "yes"})
    assert is_stale(bid, 1) and load_brief(bid).budget["min"] == 30000 and load_brief(bid, 1).version == 1


def test_each_session_sees_only_its_own_log_and_outputs(client):
    def run(idea):
        sid = client.post("/onboarding/sessions").json()["session_id"]
        out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": f"idea: {idea}"}).json()
        for _ in range(30):
            if out["phase"] != "collecting":
                break
            out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "skip"}).json()
        out = client.post(f"/onboarding/sessions/{sid}/messages", json={"text": "yes"}).json()
        return sid, out["brief_id"]

    sid_a, brief_a = run("an online course for Instagram marketing")
    sid_b, brief_b = run("a booking app for private tutors")
    log_a = client.get(f"/onboarding/sessions/{sid_a}/log").json()
    log_b = client.get(f"/onboarding/sessions/{sid_b}/log").json()
    assert log_a and all(e.get("session_id") == sid_a or e.get("brief_id") == brief_a for e in log_a)
    assert log_b and all(e.get("session_id") == sid_b or e.get("brief_id") == brief_b for e in log_b)
    assert any(e["action"] == "confirm_brief" and e["approved_by"] == "founder" for e in log_a)

    # outputs/phase1_step0_founder_brief.md now holds brief B: session A must not see it
    assert client.get(f"/onboarding/sessions/{sid_a}/outputs").json() == []
    assert [o["name"] for o in client.get(f"/onboarding/sessions/{sid_b}/outputs").json()] == [
        "phase1_step0_founder_brief.md"]


def test_new_session_has_no_log_entries_from_others(client):
    client.post("/onboarding/sessions")
    sid = client.post("/onboarding/sessions").json()["session_id"]
    assert client.get(f"/onboarding/sessions/{sid}/log").json() == []
