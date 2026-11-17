"""Stage API against a real, seeded Postgres (python db/seed.py). Skipped when the DB is unreachable.
The web and the free APIs are offline fakes; the evidence store is the real Postgres one."""

import json
import os
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from venture_os.config import Settings

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from discover_fakes import COMPETITOR_ITEMS, PAGES, PAIN_ITEMS, FakeApis, FakeToolbox  # offline web and APIs

try:
    with psycopg.connect(Settings().database_url, connect_timeout=2) as _c:
        _c.execute("SELECT 1 FROM discover_interviews LIMIT 1")
        _ok = _c.execute("SELECT count(*) FROM sources WHERE product_scope = 'digital'").fetchone()[0] > 0
except Exception:  # noqa: BLE001
    _ok = False

pytestmark = pytest.mark.skipif(not _ok, reason="seeded Postgres with Discover tables not available")
FAKE_URLS = list(PAGES) + [i.url for i in PAIN_ITEMS + COMPETITOR_ITEMS]


class OfflineToolbox(FakeToolbox):
    """Fake web and APIs, real Postgres evidence store: pages, chunks and claims really land in the database."""

    def __init__(self):
        super().__init__()
        from venture_os.evidence.store import EvidenceStore
        self.store = EvidenceStore()
        self.apis = FakeApis()

    def save_page(self, page):
        return self.store.save_page(page)

    def search_store(self, query):
        return []

    def registry_match(self, url):
        return self.store.registry_match(url)


@pytest.fixture(autouse=True, scope="module")
def _remove_fake_pages():
    """Canned pages are stored in the real evidence index during these tests: delete them afterwards so a live
    run can never reuse them as evidence."""
    yield
    with psycopg.connect(Settings().database_url) as c:  # owner connection: test cleanup only
        fake_wdi = "Individuals using the Internet (% of population), Egypt, 2024: 74.6"
        docs = c.execute("SELECT DISTINCT d.id FROM documents d LEFT JOIN chunks ch ON ch.document_id = d.id "
                         "WHERE d.url = ANY(%s) OR (d.title = 'Internet users' AND ch.text LIKE %s)",
                         (FAKE_URLS, fake_wdi + "%")).fetchall()
        ids = [r[0] for r in docs]
        c.execute("DELETE FROM claims WHERE document_id = ANY(%s)", (ids,))
        c.execute("DELETE FROM documents WHERE id = ANY(%s)", (ids,))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "replay")
    from venture_os.api import stages
    from venture_os.api.main import app
    from venture_os.evidence.store import EvidenceStore

    monkeypatch.setattr(stages, "toolbox_factory", lambda: (OfflineToolbox(), EvidenceStore()))
    return TestClient(app)


@pytest.fixture
def make_brief():
    """Insert a fixture brief + the founder's onboarding session (owner connection, setup only)."""
    made = []

    def _make(name: str | None, versions: int = 1, product_check: dict | None = None) -> tuple[str, str]:
        bid, sid = str(uuid.uuid4()), str(uuid.uuid4())
        with psycopg.connect(Settings().database_url) as c:
            c.execute("INSERT INTO briefs (id) VALUES (%s)", (bid,))
            for v in range(1, versions + 1):
                add_version(bid, name, v, c, product_check)
            c.execute("INSERT INTO onboarding_sessions (id, state, brief_id) VALUES (%s, '{}', %s)", (sid, bid))
        made.append(bid)
        return bid, sid

    yield _make
    with psycopg.connect(Settings().database_url) as c:
        for bid in made:
            c.execute("DELETE FROM claims WHERE stage_run_id IN (SELECT id FROM stage_runs WHERE brief_id = %s)",
                      (bid,))
            c.execute("DELETE FROM stage_decisions WHERE stage_run_id IN "
                      "(SELECT id FROM stage_runs WHERE brief_id = %s)", (bid,))
            c.execute("DELETE FROM stage_runs WHERE brief_id = %s", (bid,))
            c.execute("DELETE FROM discover_interviews WHERE brief_id = %s", (bid,))
            c.execute("DELETE FROM onboarding_sessions WHERE brief_id = %s", (bid,))
            c.execute("DELETE FROM brief_versions WHERE brief_id = %s", (bid,))
            c.execute("DELETE FROM briefs WHERE id = %s", (bid,))


def add_version(bid: str, name: str | None, version: int, conn=None, product_check: dict | None = None) -> None:
    if name is None:
        return
    b = json.loads((FIX / f"{name}_v1.json").read_text(encoding="utf-8"))
    pc = product_check if product_check is not None else b.get("product_check") or {}
    sql = ("INSERT INTO brief_versions (brief_id, version, fields, tags, followups, open_questions, product_check, "
           "change_note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)")
    args = (bid, version, json.dumps(b["fields"]), json.dumps(b["tags"]), json.dumps(b["followups"]),
            json.dumps(b["open_questions"]), json.dumps(pc), f"test v{version}")
    if conn is not None:
        conn.execute(sql, args)
    else:
        with psycopg.connect(Settings().database_url) as c:
            c.execute(sql, args)


def start(client, stage, bid):
    """POST a run; the research runs as a background task, which TestClient finishes before returning."""
    r = client.post(f"/stages/{stage}/runs", json={"brief_id": bid})
    if r.status_code != 201:
        return r, None
    return r, client.get(f"/stages/runs/{r.json()['id']}").json()


def decide(client, run_id, decision, sid, **kw):
    return client.post(f"/stages/runs/{run_id}/decision", json={"decision": decision, **kw},
                       headers={"X-Founder-Session": sid} if sid else {})


def test_discover_run_lands_in_postgres_and_the_founder_decides(client, make_brief):
    bid, sid = make_brief("nadafa")
    assert client.post("/stages/validate/runs", json={"brief_id": bid}).status_code == 403

    r, run = start(client, "discover", bid)
    assert r.status_code == 201 and r.json()["status"] == "running"
    assert run["status"] == "awaiting_approval", run["output"]["research"].get("error")
    plan, research = run["output"]["plan"], run["output"]["research"]
    assert {"EG-004", "EG-005", "EG-006"} <= {s["id"] for s in plan["country_sources"]}
    assert not {"R-012", "R-019", "R-020", "R-021"} & {s["id"] for s in plan["global_sources"]}  # physical scope
    assert research["gate"]["recommendation"] != "go"  # no interviews yet
    stored = client.get(f"/stages/runs/{run['id']}/claims").json()
    assert stored and all(c["url"] and c["quote"] and c["retrieved_at"] for c in stored)

    # only the founder (the onboarding session that confirmed this brief) can decide
    assert decide(client, run["id"], "approve", None).status_code == 401
    assert decide(client, run["id"], "approve", str(uuid.uuid4())).status_code == 401
    assert decide(client, run["id"], "pivot", sid).status_code == 409  # pivot needs an idea
    assert decide(client, run["id"], "revise", sid, note="find more pain quotes").json()["status"] == \
        "revision_requested"
    approved = decide(client, run["id"], "approve", sid).json()
    assert approved["status"] == "approved"
    assert [d["decision"] for d in approved["decisions"]] == ["revise", "approve"]
    assert all(d["actor"] == "founder" for d in approved["decisions"])
    log = json.loads(Path(os.environ["DECISION_LOG_PATH"]).read_text(encoding="utf-8"))
    gate_entries = [e for e in log if e["action"] == "discover_gate_decision" and e["run_id"] == run["id"]]
    assert [e["outcome"] for e in gate_entries] == ["repeat", "go"]
    assert all(e["approved_by"] == "founder" for e in gate_entries)
    gate_md = (Path(os.environ["OUTPUTS_DIR"]) / "phase1_gate_decision.md").read_text(encoding="utf-8")
    assert "outcome: **go**" in gate_md
    assert client.post("/stages/validate/runs", json={"brief_id": bid}).status_code == 501  # gate passed

    add_version(bid, "nadafa", 2)  # the founder edits the brief: the run is stale, Phase 2 is refused again
    runs = client.get("/stages/runs", params={"brief_id": bid}).json()
    assert runs[0]["stale"] and runs[0]["latest_brief_version"] == 2
    assert client.post("/stages/validate/runs", json={"brief_id": bid}).status_code == 403


def test_interviews_are_founder_only_tagged_and_regate(client, make_brief):
    bid, sid = make_brief("nadafa")
    start(client, "discover", bid)
    body = {"brief_id": bid, "person": "Working mother, New Cairo",
            "notes": "Last month the cleaner never came and I lost a whole Saturday. Great idea, I love it!"}
    assert client.post("/stages/discover/interviews", json=body).status_code == 401
    out = client.post("/stages/discover/interviews", json=body, headers={"X-Founder-Session": sid}).json()
    tags = [t["tags"] for t in out["interview"]["tagged"]]
    assert ["past_behaviour"] in tags and any("compliment" in t for t in tags)
    assert [n["text"] for n in out["noise"]] == ["Great idea, I love it!"]
    assert next(c for c in out["gate"]["checks"] if c["check"] == "interviews")["actual"] == 1
    assert client.get("/stages/discover/interviews", params={"brief_id": bid}).json()[0]["notes"] == body["notes"]


def test_pivot_needs_a_real_idea_and_waiver_needs_a_reason(client, make_brief):
    bid, sid = make_brief("nadafa")
    _, run = start(client, "discover", bid)
    assert decide(client, run["id"], "pivot", sid, pivot_to="I99").status_code == 409
    assert decide(client, run["id"], "waive", sid).status_code == 409  # no reason
    out = decide(client, run["id"], "pivot", sid, pivot_to="I1", note="the template pack looks stronger").json()
    assert out["status"] == "pivoted" and out["decisions"][0]["pivot_to"] == "I1"
    assert client.post("/stages/validate/runs", json={"brief_id": bid}).status_code == 403


def test_excluded_product_cannot_enter_discover(client, make_brief):
    bid, _ = make_brief("nadafa", product_check={"status": "excluded", "categories": ["physical_goods"],
                                                  "matched": ["rug"]})
    r = client.post("/stages/discover/runs", json={"brief_id": bid})
    assert r.status_code == 403 and "excluded" in r.json()["detail"]


def test_registry_filters_on_product_scope(client):
    digital = client.get("/registry/sources", params={"product_scope": "digital,any", "country": "EG"}).json()
    ids = {s["id"] for s in digital}
    assert {"D-001", "D-020", "EG-004"} <= ids and not {"R-012", "R-019"} & ids
    assert all(s["verified"] is False for s in digital if s["id"].startswith(("D-", "KE-")))


def test_decisions_are_append_only_and_founder_only(client, make_brief):
    bid, sid = make_brief("nadafa")
    _, run = start(client, "discover", bid)
    decide(client, run["id"], "revise", sid)
    with psycopg.connect(Settings().database_url) as c:
        c.execute("SET ROLE vos_app")
        for sql in ("UPDATE stage_decisions SET note = 'x' WHERE stage_run_id = %s",
                    "DELETE FROM stage_decisions WHERE stage_run_id = %s",
                    "DELETE FROM stage_runs WHERE id = %s"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                c.execute(sql, (run["id"],))
        with pytest.raises(psycopg.errors.CheckViolation), c.transaction():  # a model can never be the actor
            c.execute("INSERT INTO stage_decisions (stage_run_id, decision, actor) VALUES (%s, 'approve', 'model')",
                      (run["id"],))
