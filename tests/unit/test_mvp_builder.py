"""Phase 3 step 4: the MVP is one safe, self-contained HTML file for every template and both languages."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from venture_os.agents import build_inputs, mvp_builder, mvp_planner, requirements_mapper
from venture_os.agents.mvp_planner import Field
from venture_os.decision_log import read_log
from venture_os.onboarding.briefs import ConfirmedBrief

FIX = Path(__file__).parents[1] / "fixtures" / "briefs"


def setup(name="pharmastock_v1.json", template=None):
    inp = build_inputs.collect(ConfirmedBrief.from_file(FIX / name))
    reqs = requirements_mapper.Requirements(brief_id=inp.brief_id, source="rules",
                                            items=requirements_mapper._number(requirements_mapper.from_rules(inp)))
    plan = mvp_planner.from_rules(inp, reqs, template or mvp_planner.choose_template(inp, reqs))
    return inp, reqs, plan


def config_of(page):
    raw = re.search(r'<script type="application/json" id="config">(.*?)</script>', page, re.DOTALL).group(1)
    return json.loads(raw)


@pytest.mark.parametrize("template", list(mvp_planner.TEMPLATES))
@pytest.mark.parametrize("name", ["pharmastock_v1.json", "nadafa_v1.json"])
def test_every_template_renders_a_self_contained_page(template, name):
    inp, _reqs, plan = setup(name, template)
    page = mvp_builder.render(mvp_builder.config(plan, {}, inp.brief_version))
    cfg = config_of(page)
    assert cfg["template"] == template and [f["label"] for f in cfg["fields"]] == [f.label for f in plan.fields]
    assert not re.search(r'(src|href)\s*=\s*["\']?https?:', page)  # nothing loaded from outside
    assert "fetch(" not in page and "XMLHttpRequest" not in page and "innerHTML" not in page
    assert "MOCKED" in cfg["texts"]["banner"]
    if name == "nadafa_v1.json":
        assert 'dir="rtl"' in page and 'lang="ar"' in page


def test_no_sample_data_is_shipped():
    _inp, _reqs, plan = setup("nadafa_v1.json", "booking")
    cfg = config_of(mvp_builder.render(mvp_builder.config(plan, {}, 1)))
    assert set(cfg) == {"brief_id", "brief_version", "lang", "template", "title", "tagline", "screens", "fields",
                        "screen_requirements", "texts", "spec"}  # no items, providers or reviews
    assert cfg["spec"] is None  # no spec given: no product blocks


def test_hostile_text_cannot_escape_the_page():
    _inp, _reqs, plan = setup()
    evil = plan.model_copy(update={"title": '</script><script>alert(1)</script>', "tagline": "<img src=x onerror=1>"})
    page = mvp_builder.render(mvp_builder.config(evil, {}, 1))
    assert "<script>alert(1)" not in page and "<img src=x" not in page
    assert config_of(page)["title"] == '</script><script>alert(1)</script>'  # still shown, as plain text


def test_payment_fields_are_marked_mocked():
    _inp, _reqs, plan = setup()
    fields = plan.fields + [Field(id="f9", label="Price per month", type="number")]
    cfg = config_of(mvp_builder.render(mvp_builder.config(plan.model_copy(update={"fields": fields}), {}, 1)))
    assert cfg["fields"][-1]["mocked"] is True and cfg["fields"][0]["mocked"] is False


def test_model_help_lines_are_checked():
    inp, reqs, plan = setup()
    page = mvp_builder.run(inp, reqs, plan, chat_json=lambda m: json.dumps({"help": {
        "home": "See which items are running low.", "add": "You will make 10k a month with this!",
        "nope": "ignored"}}), model="qwen3:4b-instruct")
    help_ = config_of(page)["texts"]["help"]
    assert help_ == {"home": "See which items are running low."}


def test_run_writes_the_html_output_and_logs():
    inp, reqs, plan = setup()
    mvp_builder.run(inp, reqs, plan)
    out = Path(os.environ["OUTPUTS_DIR"]) / "phase3_step5_mvp.html"
    assert out.exists() and inp.brief_id in out.read_text(encoding="utf-8")
    e = read_log()[-1]
    assert e["agent"] == "mvp_builder" and e["outcome"] == "built" and e["template"] == plan.template


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_script_is_valid_javascript(tmp_path):
    _inp, _reqs, plan = setup("nadafa_v1.json", "booking")
    page = mvp_builder.render(mvp_builder.config(plan, {}, 1))
    js = re.findall(r"<script>(.*?)</script>", page, re.DOTALL)[-1]
    f = tmp_path / "app.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], check=False, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
