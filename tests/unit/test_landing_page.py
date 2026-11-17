"""Landing page draft (Phase 2): target fixed first, self-contained MOCKED page, banned copy blocked, publish gated."""

import json
import os
import re
import sys
import types
from pathlib import Path

import pytest

from venture_os.agents import business_designer as bd
from venture_os.agents import landing_page as lp
from venture_os.decision_log import read_log
from venture_os.onboarding.briefs import ConfirmedBrief

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"


def _setup(name="pharmastock_v1.json"):
    brief = ConfirmedBrief.from_file(FIXTURES / name)
    canvas = bd.run(brief.brief_id, brief=brief, evidence_items=[], chat=None)
    return brief, canvas


def _out(name):
    return (Path(os.environ["OUTPUTS_DIR"]) / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("fixture,direction", [("pharmastock_v1.json", "ltr"), ("nadafa_v1.json", "rtl")])
def test_rule_draft_has_banner_target_and_email_only_form(fixture, direction):
    brief, canvas = _setup(fixture)
    draft = lp.run(brief.brief_id, canvas, brief=brief, chat=None)
    page = _out("phase2_step2_landing_page.html")
    assert page == draft.html and f'dir="{direction}"' in page
    assert "(MOCKED)" in page and 'class="banner"' in page and lp.MOCK_MESSAGE in page
    assert re.findall(r"<input[^>]*>", page) == [m for m in re.findall(r"<input[^>]*>", page) if 'type="email"' in m]
    assert "password" not in page.lower() and "card" not in page.lower()
    assert 'data-demand-target="100"' in page

    plan = _out("phase2_step2_demand_test_plan.md")
    assert plan.startswith(f"Brief id: {brief.brief_id}") and "| waitlist sign-ups | 100 | 14 days |" in plan
    actions = [e["action"] for e in read_log() if e["agent"] == "landing_page"]
    assert actions == ["plan_demand_test", "draft_landing_page"]  # the target is fixed before the page exists


def test_page_is_self_contained():
    brief, canvas = _setup()
    page = lp.run(brief.brief_id, canvas, brief=brief, chat=None).html
    for bad in ("http://", "https://", "//cdn", "<link", "src=", "@import", "url(", "<script", "action="):
        assert bad not in page, bad


@pytest.mark.parametrize("bad", [
    "Join 500 pharmacies already on board", "★★★★★ loved by owners", "Read our customer testimonials",
    "Offer ends today, hurry", "Only 3 spots left", "Earn up to $2000 more each month",
    "Guaranteed income for your pharmacy", "Countdown: 2 days to go",
])
def test_banned_copy_from_model_is_blocked(bad):
    brief, canvas = _setup()
    reply = {"headline": bad, "subheadline": bad, "benefits": [bad, "Works offline"], "cta": "Join"}
    draft = lp.run(brief.brief_id, canvas, brief=brief, chat=lambda m: json.dumps(reply))
    assert bad not in draft.html
    assert "Works offline" in draft.html and draft.dropped


def test_copy_is_escaped_not_html():
    brief, canvas = _setup()
    reply = {"headline": "<script>alert(1)</script> Stock app", "subheadline": "ok", "benefits": [], "cta": "Go"}
    page = lp.run(brief.brief_id, canvas, brief=brief, chat=lambda m: json.dumps(reply)).html
    assert "<script>" not in page and "&lt;script&gt;" in page


def _approval(draft):
    return {"approved_by": "founder", "action": lp.PUBLISH_ACTION, "content_hash": draft.sha256}


def test_publish_without_approval_is_refused():
    brief, canvas = _setup()
    draft = lp.run(brief.brief_id, canvas, brief=brief, chat=None)
    with pytest.raises(PermissionError):
        lp.publish(draft)
    with pytest.raises(PermissionError):  # a dict alone is not enough: approval.py must confirm it
        lp.publish(draft, _approval(draft))
    assert [e["action"] for e in read_log()][-1] == "publish_refused"


def test_publish_with_founder_approval_is_only_mocked(monkeypatch):
    brief, canvas = _setup()
    draft = lp.run(brief.brief_id, canvas, brief=brief, chat=None)
    fake = types.ModuleType("venture_os.approval")
    fake.has_founder_approval = lambda brief_id, action, content_hash: content_hash == draft.sha256
    monkeypatch.setitem(sys.modules, "venture_os.approval", fake)

    assert lp.publish(draft, _approval(draft)) == lp.MOCK_MESSAGE
    entry = read_log()[-1]
    assert entry["action"] == "publish (MOCKED)" and entry["approved_by"] == "founder" and entry["mocked"]

    tampered = draft.model_copy(update={"html": draft.html + "<p>changed</p>"})
    with pytest.raises(PermissionError):
        lp.publish(tampered, _approval(draft))
