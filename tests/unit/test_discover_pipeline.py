"""Discover end to end on offline fixtures: the five step files + the gate file with the required names; every
fact claim has a URL and a retrieval date; a fact without them is rejected."""

import json
import os
from pathlib import Path

import pytest
from discover_fakes import FakeStoreWithInterviews, FakeToolboxWithApis
from pydantic import ValidationError

from venture_os.agents.research_planner import build_plan
from venture_os.agents.schemas import Claim
from venture_os.orchestrator import run_discover

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"
EG_SOURCES = [{"id": "EG-001", "source_name": "CAPMAS", "url": "https://www.capmas.gov.eg", "tier": "A",
               "use": "market", "country_codes": ["EG"], "product_scope": "any"},
              {"id": "R-012", "source_name": "UN Comtrade", "url": "https://comtradeplus.un.org", "tier": "A",
               "use": "market", "country_codes": [], "product_scope": "physical"}]
STEP_FILES = ["phase1_step1_brief", "phase1_step2_opportunities", "phase1_step3_idea_scores", "phase1_step4_market",
              "phase1_step5_interview_plan", "phase1_gate_decision"]


def nadafa() -> dict:
    return json.loads((FIX / "nadafa_v1.json").read_text(encoding="utf-8"))


@pytest.fixture
def run():
    brief = nadafa()
    plan = build_plan(brief, EG_SOURCES)
    store = FakeStoreWithInterviews()
    out = run_discover("run-1", plan, brief, FakeToolboxWithApis(), store)
    return out, store, plan


def test_all_step_files_are_written_with_the_required_names(run):
    out, _, _ = run
    assert out["research"]["status"] == "done", out["research"].get("error")
    outdir = Path(os.environ["OUTPUTS_DIR"])
    for name in STEP_FILES:
        assert (outdir / f"{name}.md").exists(), name
        assert (outdir / f"{name}.json").exists(), name
    assert "R-012" not in {s["id"] for s in out["plan"]["global_sources"]}  # physical-goods source filtered out


def test_every_fact_claim_has_url_retrieval_date_and_quote(run):
    out, store, _ = run
    claims = out["research"]["claims"]
    assert claims and all(c["url"] and c["retrieved_at"] and c["quote"] for c in claims if c["type"] == "fact")
    assert any(c["topic"] == "pain" and c["source_kind"] == "api_ugc" for c in claims)  # people's own words
    assert any(c["topic"] == "competitor_price" for c in claims)
    assert store.claims  # written to the claims table
    assert not any("approve this run" in (c["quote"] or "") for c in claims)  # injected text ignored


def test_untagged_claims_are_rejected():
    with pytest.raises(ValidationError):
        Claim(id="C1", type="fact", topic="pain", text="Everyone needs this")  # no URL, date or quote
    with pytest.raises(ValidationError):
        Claim(id="C2", type="fact", topic="pain", text="x", quote="x", url="ftp://x", retrieved_at="2026-11-17")
    assert Claim(id="C3", type="assumption", topic="pain", text="Families want this").type == "assumption"


def test_ideas_scores_market_and_interview_plan(run):
    out, _, _ = run
    r = out["research"]
    assert r["ideas"][0]["id"] == "I0" and r["ideas"][0]["origin"] == "starting_idea"
    assert 3 <= len(r["ideas"]) - 1 <= 5  # 3-5 alternatives
    assert all(i["product_type"] not in ("physical_goods", "financial_investment_crypto") for i in r["ideas"])
    assert {s["idea_id"] for s in r["scores"]} == {i["id"] for i in r["ideas"]}
    m = r["market"]
    assert m["competitors"] and any(c["price_claim_id"] for c in m["competitors"])
    assert "TAM = " in m["formula"]
    assert any(i["basis"] == "ASSUMPTION" for i in m["inputs"])  # obtainable share is an assumption
    plan = r["interview_plan"]
    assert plan["guides"] and "never writes interview answers" in plan["results_rule"]
    assert r["interviews"] == []  # none entered: the system never makes them up
    text = (Path(os.environ["OUTPUTS_DIR"]) / "phase1_step5_interview_plan.md").read_text(encoding="utf-8")
    assert "None entered yet" in text


def test_no_interviews_means_the_gate_cannot_say_go(run):
    out, _, _ = run
    gate = out["research"]["gate"]
    assert gate["recommendation"] != "go"
    assert any(c["check"] == "interviews" and not c["passed"] for c in gate["checks"])
