"""Phase 3 product spec: the MVP is about THIS brief's product, for any brief (replay mode, no live model)."""

import json
import os
from pathlib import Path

import pytest

from venture_os.agents import build_inputs, mvp_builder, mvp_tester
from venture_os.agents import product_spec as ps
from venture_os.agents.mvp_planner import MvpPlan
from venture_os.build_stage import run_build_stage
from venture_os.onboarding.briefs import ConfirmedBrief

FIX = Path(__file__).parents[1] / "fixtures"
BRIEFS = {"pharmastock_v1": "tracker_dashboard", "nadafa_v1": "booking_service", "cvpacks_v1": "digital_download",
          "darsak_v1": "content_course"}


def path(name):
    sub = "build_briefs" if (FIX / "build_briefs" / f"{name}.json").exists() else "briefs"
    return FIX / sub / f"{name}.json"


def inputs(name):
    return build_inputs.run(ConfirmedBrief.from_file(path(name)))


def page_of():
    return (Path(os.environ["OUTPUTS_DIR"]) / "phase3_step5_mvp.html").read_text(encoding="utf-8")


def checks_for(inp, page, terms=None):
    return {c.name: c for c in mvp_tester.product_checks(inp, mvp_tester._config(page), page, terms)}


REL = "about this brief (key terms in title, offers and core action)"
CORE = "core action is wired (input changes the page)"


def model_for(name, kind):
    """A stand-in model: answers the spec prompt from the brief's own fields (any brief), {} to everything else."""
    v = ps.brief_values(inputs(name))

    def chat(messages):
        if "smallest sellable version" not in messages[0]["content"]:
            return "{}"
        return json.dumps({"offer_kind": kind,
                           "offers": [{"name": {"value": v["idea"], "source": "brief:idea"},
                                       "price": {"value": v.get("business_model", ""), "source": "brief:business_model"}}],
                           "core_action": {"verb": "Try", "object": v["idea"], "source": "brief:idea",
                                           "result": "see a preview"},
                           "fields": ["A", "B"], "sample_title": {"value": v["idea"], "source": "brief:idea"},
                           "sample_lines": ["{f1}", "{f2}"], "delivery": "Download (MOCKED)",
                           "blocks": ["offers", "core"]})
    return chat


@pytest.mark.parametrize("name,kind", BRIEFS.items())
@pytest.mark.parametrize("with_model", [True, False])
def test_each_brief_gets_its_own_product(name, kind, with_model):
    inp = inputs(name)
    chat = model_for(name, kind) if with_model else None
    r = run_build_stage(ConfirmedBrief.from_file(path(name)), chat_json=chat, model="fake" if chat else None,
                        use_browser=False)
    assert r.decision.outcome == "go"
    cfg = mvp_tester._config(page_of())
    if with_model:  # the model decides the kind and the block order; code only checks them
        assert cfg["spec"]["kind"] == kind and cfg["spec"]["blocks"][:2] == ["offers", "core"]
    else:  # no model: no guess
        assert cfg["spec"]["kind"] == "other" and r.template == "directory"
    page = page_of()
    own = checks_for(inp, page)
    assert own[REL].passed and own[CORE].passed and own["every button has a handler"].passed
    assert own["buy, delivery and waitlist labelled MOCKED"].passed
    cfg = mvp_tester._config(page)
    assert next(iter(cfg["screens"])) == "product" and cfg["spec"]["offers"]
    for other in BRIEFS:  # the same page fails relevance for every other brief's terms
        if other != name:
            terms = ps.key_terms(ps.brief_values(inputs(other)))
            assert not checks_for(inp, page, terms)[REL].passed, other


def test_old_library_output_for_the_template_brief_now_fails():
    inp = inputs("cvpacks_v1")
    old = json.loads((FIX / "mvp" / "cvpacks_old_library_plan.json").read_text(encoding="utf-8"))
    plan = MvpPlan(brief_id=inp.brief_id, lang="en", template=old["template"], title=old["title"],
                   tagline=old["tagline"], item_name=old["item_name"], fields=old["fields"],
                   screens={"home": "Library", "add": "Add an item", "list": "Saved"}, flows=[["home", "list"]])
    page = mvp_builder.render(mvp_builder.config(plan, {}, inp.brief_version))
    got = checks_for(inp, page)
    assert not got[REL].passed and not got[CORE].passed


def test_model_values_without_a_source_become_assumptions_and_bad_text_is_dropped():
    inp = inputs("cvpacks_v1")
    reply = {"offer_kind": "digital_download",
             "offers": [{"name": {"value": "Arabic CV template pack", "source": "brief:idea"},
                         "price": {"value": "$5", "source": "made-up"},
                         "contents": {"value": "Guaranteed income of $500 a month", "source": "brief:idea"}}],
             "core_action": {"verb": "Fill in", "object": "your Arabic CV template", "source": "brief:idea",
                             "result": "see it laid out"},
             "fields": ["Full name", "Job title"], "sample_title": {"value": "Arabic CV", "source": "brief:idea"},
             "sample_lines": ["{f1}", "{f2}"], "delivery": "Instant download (MOCKED)"}
    spec = ps.run(inp, chat_json=lambda m: json.dumps(reply), model="fake")
    assert spec.source == "model" and spec.offers[0].price.source == ps.ASSUMPTION
    assert "Guaranteed" not in spec.visible_text()  # income promise dropped, the brief's own words used instead


def test_an_off_brief_model_spec_is_replaced_by_rules():
    inp = inputs("cvpacks_v1")
    reply = {"offers": [{"name": {"value": "Book library", "source": "brief:idea"}}],
             "core_action": {"verb": "Add", "object": "a book", "result": "see your shelf"},
             "sample_title": {"value": "My books", "source": "brief:idea"}}
    spec = ps.run(inp, chat_json=lambda m: json.dumps(reply), model="fake")
    assert spec.source == "rules" and ps.relevance(spec.key_terms, spec.visible_text())[0]


def test_no_model_gives_a_minimal_spec_from_brief_fields():
    spec = ps.from_rules(inputs("darsak_v1"))
    assert spec.offer_kind == "other"
    assert spec.offers[0].name.source == "brief:idea" and spec.offers[0].price.source == "brief:business_model"
    assert all("{" not in x or x.startswith("{f") for x in spec.sample_lines)


def test_the_model_gets_the_discover_and_validate_data():
    from venture_os.build_stage import canvas_to_items
    from venture_os.evidence import Item

    canvas = {"boxes": {"problem": [{"text": "Formatting takes hours", "basis": "EVIDENCED",
                                     "url": "https://example.org/thread", "date": "2026-11-10"}],
                        "unique_value_proposition": [{"text": "Ready in minutes", "basis": "ASSUMPTION"}]},
              "riskiest_assumption": "People will pay for it"}
    validate = canvas_to_items(canvas)
    assert [i.label for i in validate] == ["evidenced", "assumption", "assumption"]
    discover = [Item(phase=1, kind="pain", label="evidenced", text="pain: a quoted customer pain",
                     sources=["https://example.org/q"])]
    seen = {}
    name = "cvpacks_v1"
    chat = model_for(name, "digital_download")

    def spy(messages):
        if "smallest sellable version" in messages[0]["content"]:
            seen["facts"] = messages[1]["content"]
        return chat(messages)

    r = run_build_stage(ConfirmedBrief.from_file(path(name)), chat_json=spy, model="fake", use_browser=False,
                        extra_items=discover + validate)
    assert "(Discover, pain, evidenced) = pain: a quoted customer pain" in seen["facts"]
    assert "(Validate, pain, evidenced) = lean canvas problem: Formatting takes hours" in seen["facts"]
    assert r.decision.outcome == "go"


def test_with_a_model_configured_a_page_from_brief_words_alone_does_not_pass():
    name = "cvpacks_v1"
    r = run_build_stage(ConfirmedBrief.from_file(path(name)), chat_json=lambda m: "{}", model="fake",
                        use_browser=False)
    assert r.decision.outcome == "repeat"  # the model gave nothing usable: reported, not hidden
    report = (Path(os.environ["OUTPUTS_DIR"]) / "phase3_step6_test_report.md").read_text(encoding="utf-8")
    assert "product written by the model" in report and "**FAIL**" in report
