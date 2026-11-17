"""Founder approvals for outward actions (publish_landing_page, create_order, refund_order) and the founder's
waitlist count, against a real seeded Postgres. Skipped when the DB is unreachable."""

import io
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from venture_os import approval
from venture_os.config import Settings

try:
    with psycopg.connect(Settings().database_url, connect_timeout=2) as _c:
        _c.execute("SELECT 1 FROM founder_approvals LIMIT 1")
    _ok = True
except Exception:  # noqa: BLE001
    _ok = False

pytestmark = pytest.mark.skipif(not _ok, reason="seeded Postgres with founder_approvals not available")
DRAFT = "<html><body><h1>Join the waitlist</h1></body></html>"


@pytest.fixture
def brief():
    """A confirmed brief and the onboarding session that owns it (owner connection: test setup only)."""
    bid, sid, other = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    with psycopg.connect(Settings().database_url) as c:
        c.execute("INSERT INTO briefs (id) VALUES (%s)", (bid,))
        c.execute("INSERT INTO onboarding_sessions (id, state, brief_id) VALUES (%s, '{}', %s), (%s, '{}', NULL)",
                  (sid, bid, other))
    yield {"brief_id": bid, "session": sid, "other_session": other}
    with psycopg.connect(Settings().database_url) as c:
        c.execute("DELETE FROM founder_approvals WHERE brief_id = %s", (bid,))
        c.execute("DELETE FROM onboarding_sessions WHERE id IN (%s, %s)", (sid, other))
        c.execute("DELETE FROM briefs WHERE id = %s", (bid,))


@pytest.fixture
def client():
    from venture_os.api.main import app

    return TestClient(app)


def test_content_hash_is_sha256_of_the_exact_content():
    assert approval.content_hash(DRAFT) == approval.content_hash(DRAFT.encode("utf-8"))
    assert approval.content_hash(DRAFT) != approval.content_hash(DRAFT + " ")
    assert len(approval.content_hash(b"")) == 64


def test_nothing_is_approved_until_the_founder_approves_in_the_ui(client, brief):
    h = approval.content_hash(DRAFT)
    body = {"brief_id": brief["brief_id"], "action": "publish_landing_page", "content_hash": h}
    assert not approval.has_founder_approval(brief["brief_id"], "publish_landing_page", h)
    assert client.post("/stages/approvals", json=body).status_code == 401                      # no session
    assert client.post("/stages/approvals", json=body,
                       headers={"X-Founder-Session": brief["other_session"]}).status_code == 401  # not the owner
    r = client.post("/stages/approvals", json=body, headers={"X-Founder-Session": brief["session"]})
    assert r.status_code == 201 and r.json()["channel"] == "ui"
    assert approval.has_founder_approval(brief["brief_id"], "publish_landing_page", h)
    check = client.get("/stages/approvals/check", params=body).json()
    assert check == {"approved": True}


def test_approval_covers_only_that_exact_content_action_and_brief(client, brief):
    h = approval.content_hash(DRAFT)
    approval.record_founder_approval(brief["brief_id"], "create_order", h, session_id=brief["session"], channel="ui")
    assert approval.has_founder_approval(brief["brief_id"], "create_order", h)
    assert not approval.has_founder_approval(brief["brief_id"], "create_order", approval.content_hash(DRAFT + "!"))
    assert not approval.has_founder_approval(brief["brief_id"], "refund_order", h)
    assert not approval.has_founder_approval(str(uuid.uuid4()), "create_order", h)


@pytest.mark.parametrize("brief_id, action, h", [
    ("not-a-uuid", "create_order", "a" * 64), (str(uuid.uuid4()), "send_email", "a" * 64),
    (str(uuid.uuid4()), "create_order", "A" * 64), (str(uuid.uuid4()), "create_order", "abc")])
def test_malformed_checks_are_never_approved(brief_id, action, h):
    assert approval.has_founder_approval(brief_id, action, h) is False


def test_only_the_founder_through_ui_or_cli_can_record(brief):
    h = approval.content_hash(DRAFT)
    with pytest.raises(PermissionError):
        approval.record_founder_approval(brief["brief_id"], "refund_order", h, session_id=brief["session"],
                                         channel="agent")
    with pytest.raises(PermissionError):
        approval.record_founder_approval(brief["brief_id"], "refund_order", h, session_id="", channel="ui")
    with pytest.raises(ValueError):
        approval.record_founder_approval(brief["brief_id"], "wire_money", h, session_id=brief["session"], channel="ui")
    assert not approval.has_founder_approval(brief["brief_id"], "refund_order", h)


def test_database_refuses_other_actors_channels_and_sessions(brief):
    h = approval.content_hash(DRAFT)
    sql = ("INSERT INTO founder_approvals (brief_id, action, content_hash, actor, channel, session_id) "
           "VALUES (%s,%s,%s,%s,%s,%s)")
    bad = [("agent", "ui", brief["session"]), ("founder", "api", brief["session"]),
           ("founder", "ui", brief["other_session"])]
    for actor, channel, session in bad:
        with psycopg.connect(Settings().database_url) as c, pytest.raises(psycopg.Error):
            c.execute("SET ROLE vos_app")
            c.execute(sql, (brief["brief_id"], "publish_landing_page", h, actor, channel, session))
    with psycopg.connect(Settings().database_url) as c, pytest.raises(psycopg.Error):
        c.execute("SET ROLE vos_agent")  # agents may read approvals, never write one
        c.execute(sql, (brief["brief_id"], "publish_landing_page", h, "founder", "ui", brief["session"]))


class _Tty(io.StringIO):
    def isatty(self):
        return True


def _cli(brief, tmp_path, stdin):
    draft = tmp_path / "landing.html"
    draft.write_text(DRAFT, encoding="utf-8")
    out = io.StringIO()
    code = approval.main(["--brief", brief["brief_id"], "--action", "publish_landing_page", "--file", str(draft),
                          "--session", brief["session"]], stdin=stdin, stdout=out)
    return code, out.getvalue()


def test_cli_approves_only_when_the_founder_types_approve(brief, tmp_path):
    h = approval.content_hash(DRAFT)
    code, out = _cli(brief, tmp_path, io.StringIO("approve\n"))  # piped input: refused
    assert code == 2 and "interactive" in out
    code, out = _cli(brief, tmp_path, _Tty("yes\n"))
    assert code == 1 and not approval.has_founder_approval(brief["brief_id"], "publish_landing_page", h)
    code, out = _cli(brief, tmp_path, _Tty("approve\n"))
    assert code == 0 and h in out
    assert approval.has_founder_approval(brief["brief_id"], "publish_landing_page", h)
