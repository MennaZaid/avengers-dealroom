"""Phase 3 step 5: the tester passes a good MVP and catches every kind of broken or unsafe one."""

import os
from pathlib import Path

import pytest
from test_mvp_builder import setup

from venture_os.agents import mvp_builder, mvp_tester, product_spec
from venture_os.agents.mvp_planner import Field
from venture_os.decision_log import read_log


def built(name="pharmastock_v1.json", template=None, help_lines=None, plan_update=None):
    inp, reqs, plan = setup(name, template)
    if plan_update:
        plan = plan.model_copy(update=plan_update)
    spec = product_spec.from_rules(inp)
    return inp, reqs, plan, mvp_builder.render(mvp_builder.config(plan, help_lines or {}, inp.brief_version, spec))


def failed(checks):
    return [c.name for c in checks if not c.passed]


@pytest.mark.parametrize("name", ["pharmastock_v1.json", "nadafa_v1.json"])
def test_a_built_mvp_passes_every_static_check(name):
    inp, reqs, plan, page = built(name)
    checks, _ = mvp_tester.check(inp, reqs, plan, page, use_browser=False)
    assert failed(checks) == []


def test_external_script_and_network_call_fail():
    inp, reqs, plan, page = built()
    page = page.replace("</head>", '<script src="https://cdn.example.com/x.js"></script></head>')
    page = page.replace('"use strict";', '"use strict"; fetch("https://evil.example");')
    f = failed(mvp_tester.check(inp, reqs, plan, page, use_browser=False)[0])
    assert "nothing loaded from outside" in f and "no network calls or code injection points" in f


def test_must_never_help_text_fails():
    inp, reqs, plan, page = built(help_lines={"home": "You will make 10k a month!"})
    assert "no must-never text (income promises, fake reviews, urgency)" in failed(
        mvp_tester.check(inp, reqs, plan, page, use_browser=False)[0])


def test_missing_field_and_forbidden_field_fail():
    inp, reqs, plan, page = built()
    bigger = plan.model_copy(update={"fields": plan.fields + [Field(id="f9", label="Shelf", type="text")]})
    assert "every planned field is present" in failed(mvp_tester.check(inp, reqs, bigger, page, use_browser=False)[0])
    inp, reqs, plan, page = built(plan_update={"fields": [Field(id="f1", label="Password", type="text"),
                                                           Field(id="f2", label="Item", type="text")]})
    assert "no password, card or medical fields" in failed(mvp_tester.check(inp, reqs, plan, page, use_browser=False)[0])


def test_arabic_brief_needs_rtl():
    inp, reqs, plan, page = built("nadafa_v1.json")
    assert "right-to-left for an Arabic brief" in failed(
        mvp_tester.check(inp, reqs, plan, page.replace('dir="rtl"', 'dir="ltr"'), use_browser=False)[0])


@pytest.mark.skipif(mvp_tester._browser() is None, reason="no Edge or Chrome installed")
def test_page_really_builds_its_screens_in_a_browser():
    _inp, _reqs, _plan, page = built("nadafa_v1.json", "booking")
    import json
    import re
    cfg = json.loads(re.search(r'id="config">(.*?)</script>', page, re.DOTALL).group(1))
    c = mvp_tester.browser_check(page, cfg)
    assert c.passed, c.detail


def test_run_writes_the_report_and_logs():
    inp, reqs, plan, page = built()
    rep = mvp_tester.run(inp, reqs, plan, page, attempt=2, use_browser=False)
    assert rep.passed and rep.browser is None
    text = (Path(os.environ["OUTPUTS_DIR"]) / "phase3_step6_test_report.md").read_text(encoding="utf-8")
    assert "ALL PASSED (attempt 2)" in text and "Brief id:" in text
    e = read_log()[-1]
    assert e["agent"] == "mvp_tester" and e["outcome"] == "pass" and e["failed"] == []
