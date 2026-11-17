"""Registry API against a real, seeded Postgres (python db/seed.py). Skipped when the DB is unreachable."""

from pathlib import Path

import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient

from venture_os.config import Settings

CONFIG = Path(__file__).resolve().parents[2] / "config" / "sources"

try:
    with psycopg.connect(Settings().database_url, connect_timeout=2) as _c:
        _seeded = _c.execute("SELECT count(*) FROM sources").fetchone()[0] > 0
except Exception:  # noqa: BLE001
    _seeded = False

pytestmark = pytest.mark.skipif(not _seeded, reason="seeded Postgres not available")

TOKEN = "test-admin-token-0123456789"
HDR = {"X-Admin-Token": TOKEN, "X-Admin-Id": "tester"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    from venture_os.api.main import app

    return TestClient(app)


@pytest.fixture
def cleanup():
    ids = []
    yield ids
    with psycopg.connect(Settings().database_url) as c:  # owner connection: test cleanup only
        for table, col, i in ids:
            c.execute(f"DELETE FROM {table} WHERE {col} = %s", (i,))


def test_read_routes(client):
    assert client.get("/health").json()["status"] == "ok"
    eg = client.get("/registry/sources", params={"country": "EG"}).json()
    ids = {s["id"] for s in eg}
    assert {"EG-001", "R-001"} <= ids  # Egypt pack plus global sources
    assert "R-047" not in ids  # US Census is not returned for Egypt
    assert all(s["tier"] == "A" for s in client.get("/registry/sources", params={"tier": "A"}).json())
    corpus_files = ("corpus_seed.yaml", "corpus_digital.yaml")
    expected = sum(len(yaml.safe_load((CONFIG / f).read_text(encoding="utf-8"))) for f in corpus_files)
    assert len(client.get("/registry/corpus").json()) == expected
    models = client.get("/registry/components", params={"kind": "model"}).json()
    assert models and all(m["open_weight"] for m in models)


def test_endpoints_expose_env_names_never_secrets(client):
    eps = client.get("/registry/endpoints", params={"profile": "reasoning"}).json()
    assert [e["provider"] for e in eps] == ["hosted", "colab"]  # fallback order
    for e in eps:
        assert e["api_key_env"].isupper()
        assert not any(k in e for k in ("api_key", "key_value", "secret"))


def test_admin_requires_token(client):
    body = {"reason": "testing auth"}
    assert client.post("/admin/sources/R-001/deactivate", json=body).status_code == 401
    bad = {"X-Admin-Token": "wrong", "X-Admin-Id": "x"}
    assert client.post("/admin/sources/R-001/deactivate", json=body, headers=bad).status_code == 401


def test_admin_disabled_without_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "")
    from venture_os.api.main import app

    r = TestClient(app).post("/admin/sources/R-001/deactivate", json={"reason": "x" * 6}, headers=HDR)
    assert r.status_code == 503


def test_admin_add_and_deactivate_source_is_logged(client, cleanup):
    cleanup += [("source_changes", "source_id", "ZZ-901"), ("sources", "id", "ZZ-901")]
    new = {
        "id": "ZZ-901", "scope": "country", "source_name": "Test statistics office",
        "url": "https://stats.gov.zz", "tier": "A", "country_codes": ["ZZ"], "reason": "integration test",
    }
    r = client.post("/admin/sources", json=new, headers=HDR)
    assert r.status_code == 201 and r.json()["domain"] == "stats.gov.zz"
    assert client.post("/admin/sources", json=new, headers=HDR).status_code == 409

    r = client.post("/admin/sources/ZZ-901/deactivate", json={"reason": "integration test"}, headers=HDR)
    assert r.json()["active"] is False
    assert "ZZ-901" not in {s["id"] for s in client.get("/registry/sources").json()}

    log = client.get("/admin/changes", headers=HDR).json()["sources"]
    actions = [(c["source_id"], c["action"], c["admin_id"]) for c in log]
    assert ("ZZ-901", "add", "tester") in actions and ("ZZ-901", "deactivate", "tester") in actions


def test_admin_rejects_non_https_source(client):
    bad = {"id": "ZZ-902", "scope": "global", "source_name": "x", "url": "http://x.org", "tier": "A",
           "reason": "integration test"}
    assert client.post("/admin/sources", json=bad, headers=HDR).status_code == 422


def test_admin_add_component_is_logged(client, cleanup):
    cleanup += [("catalog_changes", "row_id", "T-901"), ("components", "id", "T-901")]
    comp = {"id": "T-901", "kind": "model", "name": "Test model", "license": "Apache 2.0",
            "open_weight": True, "osi_open": True, "reason": "integration test"}
    assert client.post("/admin/components", json=comp, headers=HDR).status_code == 201
    r = client.post("/admin/components/T-901/deactivate", json={"reason": "integration test"}, headers=HDR)
    assert r.json()["active"] is False
