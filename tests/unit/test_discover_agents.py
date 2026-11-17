"""Discover agents, tools and evidence rules, fully offline (fake web, fake store, scripted model)."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from discover_fakes import (
    PAGES,
    FakeStoreWithInterviews,
    FakeToolbox,
    FakeToolboxWithApis,
    ScriptedModel,
    stored_chunk,
)

from venture_os.agents.base import Budget, Trace
from venture_os.agents.brief_analyzer import analyze
from venture_os.agents.competitor_intelligence import CompetitorIntelligenceAgent
from venture_os.agents.market_research import MarketResearchAgent
from venture_os.agents.opportunity_finder import propose_ideas
from venture_os.agents.research_planner import Topic, build_plan
from venture_os.agents.schemas import Claim
from venture_os.evidence.extract import model_claims, quote_in, rule_claims
from venture_os.evidence.store import StoredChunk, chunk_text
from venture_os.evidence.validate import claim_flags, run_report
from venture_os.orchestrator import run_discover
from venture_os.tools.fetch import FetchError, check_public_url, html_to_text, page_from_bytes
from venture_os.tools.search import SearchHit

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"
NADAFA = json.loads((FIX / "nadafa_v1.json").read_text(encoding="utf-8"))
EG_SOURCES = [{"id": "EG-001", "source_name": "CAPMAS", "url": "https://www.capmas.gov.eg", "tier": "A",
               "use": "market", "country_codes": ["EG"]}]


def topic(key="market_size", queries=(("home services market size Egypt", "en"),)) -> Topic:
    from venture_os.agents.research_planner import PlannedQuery
    return Topic(key=key, title=key, kind="standard", source_ids=[],
                 queries=[PlannedQuery(language=lang, text=t, built_from=[]) for t, lang in queries])


# ---------- tools ----------

def test_html_to_text_keeps_arabic_drops_scripts_reads_date():
    title, text, published = html_to_text(PAGES["https://www.capmas.gov.eg/households"])
    assert title == "CAPMAS households" and published == date(2024, 5, 1)
    assert "ignore()" not in text and "menu" not in text
    assert "القاهرة الجديدة" in text and "1.9 billion" in text


@pytest.mark.parametrize("url", ["http://localhost:8010/health", "http://127.0.0.1/", "http://10.0.0.5/x",
                                 "file:///etc/passwd", "ftp://example.com/x", "http://192.168.1.1/"])
def test_private_and_non_http_urls_refused(url):
    with pytest.raises(FetchError):
        check_public_url(url)


def test_short_pages_and_unknown_types_rejected():
    with pytest.raises(FetchError):
        page_from_bytes("https://x.org", "https://x.org", b"<p>too short</p>", "text/html")
    with pytest.raises(FetchError):
        page_from_bytes("https://x.org", "https://x.org", b"\x00" * 500, "application/zip")


def test_chunks_are_bounded_and_keep_all_text():
    text = "\n".join(f"Paragraph {i}. " + "word " * 80 for i in range(30))
    chunks = chunk_text(text, size=1200)
    assert all(len(c) <= 1200 for c in chunks)
    assert "".join(chunks).replace("\n", "").replace(" ", "") == text.replace("\n", "").replace(" ", "")


# ---------- evidence ----------

def chunk(text, **kw) -> StoredChunk:
    c = stored_chunk(text)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_rule_claims_are_verbatim_and_numeric_for_market_size():
    c = chunk("Egypt home services market size reached 1.9 billion USD in 2025 according to the survey. "
              "Home services in Egypt are popular with many families across the country today.")
    claims = rule_claims(c, "market_size", "home services market size Egypt")
    assert len(claims) == 1 and "1.9 billion" in claims[0]["text"]
    assert claims[0]["quote"] == claims[0]["text"] and quote_in(claims[0]["quote"], c.text)


def test_model_claims_keep_only_exact_quotes():
    c = chunk("Prices start at 300 EGP per visit for a standard apartment cleaning in Cairo.")
    model = ScriptedModel([{"claims": [
        {"claim": "A visit costs 300 EGP", "quote": "Prices start at 300 EGP per visit"},
        {"claim": "Market is 5bn", "quote": "the market is worth 5 billion"},  # not in the text: dropped
    ]}])
    out = model_claims(c, "pricing", "cleaning prices Cairo", model)
    assert [o["text"] for o in out] == ["A visit costs 300 EGP"] and out[0]["extracted_by"] == "model"
    assert "<document>" in model.prompts[0][1]["content"] and "untrusted" in model.prompts[0][0]["content"]


def test_critic_flags():
    old = chunk("Kenya home services market size was 10 million USD in 2014.", published_at=date(2015, 1, 1))
    flags = claim_flags({"quote": old.text}, old, "market_size", "EG", today=date(2026, 11, 17))
    assert {"stale", "web_source", "other_country"} <= set(flags)
    reg = chunk("Egypt market grew 10% in 2025 as reported.", published_at=None, source_id="EG-001",
                max_age_months=24)
    assert claim_flags({"quote": reg.text}, reg, "market_size", "EG") == ["undated"]
    assert "quote_not_found" in claim_flags({"quote": "invented"}, reg, "market_size", "EG")
    report = run_report([{"topic": "market_size", "flags": ["stale"]}], ["market_size", "pricing"])
    assert report["topics_without_evidence"] == ["pricing"] and report["usable_claims"] == 0


# ---------- agents ----------

def test_rules_agent_fetches_registry_source_first_and_stores_pages():
    tb = FakeToolbox()
    agent = MarketResearchAgent([topic()], tb, Budget(), Trace())
    agent.fetch_per_query = 1
    result = agent.run()
    assert tb.fetched == ["https://www.capmas.gov.eg/households"]  # tier A ranked above web results
    assert result.mode == "rules" and result.evidence[0].chunks[0].source_id == "EG-001"
    assert tb.searches == [("home services market size Egypt", "en")]


def test_stored_evidence_is_added_but_the_web_is_still_searched():
    tb = FakeToolbox(store_hits=[stored_chunk("a"), stored_chunk("b")])
    trace = Trace()
    res = MarketResearchAgent([topic()], tb, Budget(), trace).run()
    assert tb.searches  # stored pages never replace a fresh search
    assert any(e["action"] == "store_search" and e["found"] == 2 for e in trace.events)
    assert any(c.from_db for ev in res.evidence for c in ev.chunks)


def test_agents_in_one_run_share_fetched_pages():
    tb, budget = FakeToolbox(), Budget()
    MarketResearchAgent([topic()], tb, budget, Trace()).run()
    n = len(tb.fetched)
    MarketResearchAgent([topic()], tb, budget, Trace()).run()
    assert len(tb.fetched) == n


def test_budget_bounds_the_run():
    tb = FakeToolbox()
    budget = Budget(fetches=1, searches=1)
    two = topic(queries=(("q one market", "en"), ("q two market", "en")))
    MarketResearchAgent([two], tb, budget, Trace()).run()
    assert len(tb.searches) == 1 and len(tb.fetched) == 1


def test_competitor_agent_matches_brief_competitors():
    tb = FakeToolbox()
    t = topic("competitors", (("Ezhalha Egypt", "en"), ("Filkhedma Egypt", "en"),
                              ("home services companies in Egypt", "en")))
    res = CompetitorIntelligenceAgent([t], tb, Budget(), Trace(), known=["Ezhalha", "Filkhedma"]).run()
    by_name = {c["name"]: c for c in res.competitors}
    assert by_name["Ezhalha"]["url"] == "https://ezhalha.example.com/" and by_name["Ezhalha"]["from_brief"]
    assert by_name["Filkhedma"]["url"] is None and by_name["Filkhedma"]["status"].startswith("not found")
    assert any(not c["from_brief"] and c["status"].startswith("candidate") for c in res.competitors)


def test_model_agent_only_fetches_urls_from_search_results():
    tb = FakeToolbox()
    model = ScriptedModel([
        {"action": "web_search", "query": "egypt cleaning prices", "language": "en"},
        {"action": "fetch", "url": "https://evil.example.com/not-from-search"},
        {"action": "fetch", "url": "https://blog.example.com/cleaning-prices"},
        {"action": "finish"},
    ])
    trace = Trace()
    res = MarketResearchAgent([topic("pricing")], tb, Budget(), trace, model=model).run()
    assert tb.fetched == ["https://blog.example.com/cleaning-prices"]
    assert res.mode == "model" and any(e["action"] == "model_invalid_action" for e in trace.events)
    assert "tier A" in model.prompts[2][1]["content"]  # registry sources are marked for the model


def test_model_agent_falls_back_to_rules_on_nonsense():
    tb = FakeToolbox()
    trace = Trace()
    MarketResearchAgent([topic()], tb, Budget(), trace, model=lambda m: "not json").run()
    assert any(e["action"] == "fallback_to_rules" for e in trace.events) and tb.searches


# ---------- the whole Discover run ----------

def test_failed_run_is_recorded():
    class Broken(FakeStoreWithInterviews):
        def save_claims(self, run_id, claims):
            raise RuntimeError("db down")

    store = Broken()
    out = run_discover("run-2", build_plan(NADAFA, EG_SOURCES), NADAFA, FakeToolboxWithApis(), store)
    assert out["research"]["status"] == "failed" and "db down" in out["research"]["error"]
    assert store.updates[-1][1] == "failed"


def test_model_ideas_cite_only_real_quotes_and_pass_guardrails():
    db = analyze(NADAFA)
    pain = [Claim(id="C7", type="fact", topic="pain", text="q", quote="cleaners never came",
                  url="https://news.ycombinator.com/item?id=1", retrieved_at="2026-11-17T00:00:00")]
    model = ScriptedModel([{"starting_idea": {"title": "Booking app for working families", "product_type": "mobile_app",
                                              "pain": "unreliable cleaners", "pain_claim_ids": ["P1", "P9"]},
                            "alternatives": [
                                {"title": "Cleaner vetting checklist template", "product_type": "template_or_asset",
                                 "pain_claim_ids": ["P1"]},
                                {"title": "Guaranteed income of 50,000 EGP a month course",
                                 "product_type": "online_course"},
                                {"title": "Sell cleaning products", "product_type": "physical_goods"}]}])
    ideas = propose_ideas(db, pain, model, "qwen2.5:3b")
    assert ideas[0].pain_claim_ids == ["C7"]  # P9 does not exist: dropped
    assert not any("Guaranteed income" in i.title for i in ideas)  # check_output blocks income promises
    assert all(i.product_type != "physical_goods" for i in ideas)
    assert ideas[0].built_by == "qwen2.5:3b" and "<untrusted>" in model.prompts[0][1]["content"]


def test_pages_from_this_run_are_not_counted_as_stored_evidence():
    fresh = stored_chunk("x")
    fresh.retrieved_at = datetime.now(UTC) + timedelta(seconds=1)  # stored during this run
    tb = FakeToolbox(store_hits=[fresh, fresh])
    MarketResearchAgent([topic()], tb, Budget(), Trace()).run()
    assert tb.searches  # still searches the web


def test_registry_sources_are_read_first():
    tb = FakeToolbox()
    hit = SearchHit(url="https://www.capmas.gov.eg/households", title="EG-001 CAPMAS", snippet="", rank=0)
    trace = Trace()
    agent = MarketResearchAgent([topic()], tb, Budget(), trace, registry_pages={"market_size": [hit]})
    agent.run()
    assert tb.fetched[0] == "https://www.capmas.gov.eg/households"
    assert trace.events[1]["action"] == "registry_source"


def test_publication_date_from_the_address_when_the_page_has_none():
    from venture_os.tools.fetch import url_date
    assert url_date("https://www.the-star.co.ke/counties/eastern/2024-03-07-state-closes") == date(2024, 3, 7)
    assert url_date("https://news.example.com/2023/11/02/story") == date(2023, 11, 2)
    assert url_date("https://example.com/products/2024-99-99") is None
    assert url_date("https://example.com/page?id=2024-03-07") is None  # only the path counts


def test_model_idea_timeout_falls_back_to_templates_and_says_why():
    db = analyze(NADAFA)
    pain = [Claim(id="C7", type="fact", topic="pain", text="q", quote="cleaners never came",
                  url="https://news.ycombinator.com/item?id=1", retrieved_at="2026-11-17T00:00:00")]

    def slow_model(messages):
        raise TimeoutError("read timed out")

    ideas = propose_ideas(db, pain, slow_model, "qwen3:4b-instruct")
    assert all(i.built_by == "rules" for i in ideas)
    assert any("Model ideas not used (model call failed (TimeoutError))" in a for a in ideas[0].assumptions)


def test_model_gets_a_bounded_prompt():
    from venture_os.agents.opportunity_finder import MODEL_QUOTES, QUOTE_CHARS

    db = analyze(NADAFA)
    pain = [Claim(id=f"C{i}", type="fact", topic="pain", text="q", quote="cleaners never came " * 40,
                  url=f"https://news.ycombinator.com/item?id={i}", retrieved_at="2026-11-17T00:00:00")
            for i in range(40)]
    model = ScriptedModel([{"starting_idea": {"title": "x"}}])
    propose_ideas(db, pain, model, "m")
    sent = json.loads(model.prompts[0][1]["content"].removeprefix("<untrusted>").removesuffix("</untrusted>"))
    assert len(sent["pain_quotes"]) == MODEL_QUOTES
    assert all(len(q) <= QUOTE_CHARS for q in sent["pain_quotes"].values())


def test_critic_separates_founder_words_from_overclaims():
    from venture_os.agents.research_critic import rule_findings
    from venture_os.agents.schemas import Idea

    def idea(i, title):
        return Idea(id=i, title=title, description="", product_type="mobile_app", origin="alternative",
                    built_by="m", pain="p", pain_claim_ids=["C1"], why_founder="")

    found = rule_findings([], [idea("I0", "A chatbot for everyone"), idea("I1", "Guaranteed huge demand app")],
                          brief_text="Target market: Everyone")
    kinds = {f.kind: f.detail for f in found}
    assert "broad_target" in kinds and "everyone" in kinds["broad_target"]
    assert [f.detail for f in found if f.kind == "overclaim"] == [
        "I1: overclaiming wording in the idea text (guaranteed, huge demand)"]
