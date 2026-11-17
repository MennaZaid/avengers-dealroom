"""Discover Research Planner on the two fixture briefs (no database, no model)."""

import copy
import json
from pathlib import Path

import pytest

from venture_os.agents.research_planner import (
    NO_COUNTRY_SOURCE,
    ResearchPlan,
    build_plan,
    lang_of,
    split_competitors,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"

# Shaped like GET /registry/sources?country=<cc> rows (country rows + global rows).
SOURCES = [
    {"id": "EG-001", "source_name": "CAPMAS", "url": "https://www.capmas.gov.eg", "tier": "A", "use": "market",
     "country_codes": ["EG"], "verified": False},
    {"id": "EG-003", "source_name": "Egypt law portal", "url": "https://example.eg", "tier": "A", "use": "legal",
     "country_codes": ["EG"], "verified": False},
    {"id": "R-001", "source_name": "World Bank WDI", "url": "https://data.worldbank.org", "tier": "A",
     "use": "market", "country_codes": [], "verified": False},
    {"id": "R-002", "source_name": "Global law index", "url": "https://example.org", "tier": "B", "use": "legal",
     "country_codes": [], "verified": False},
    {"id": "CS-001", "source_name": "Case study", "url": "https://example.com", "tier": "B", "use": "analogy",
     "country_codes": [], "verified": False},
]


def load(name: str) -> dict:
    return json.loads((FIX / f"{name}_v1.json").read_text(encoding="utf-8"))


def sources_for(cc: str) -> list[dict]:  # what the registry returns for ?country=cc
    return [s for s in SOURCES if not s["country_codes"] or cc in s["country_codes"]]


def queries(plan: ResearchPlan):
    return [q for t in plan.topics for q in t.queries]


def test_egypt_plan_arabic_and_english_with_egypt_sources():
    plan = build_plan(load("nadafa"), sources_for("EG"))
    assert plan.country_code == "EG" and plan.languages == ["ar", "en"]
    assert [s.id for s in plan.country_sources] == ["EG-001", "EG-003"]
    assert {s.id for s in plan.global_sources} == {"R-001", "R-002"}  # analogy sources left out
    langs = {q.language for q in queries(plan)}
    assert langs == {"ar", "en"}
    for key in ("market_size", "competitors", "customer_pain", "pricing", "regulation"):
        topic = next(t for t in plan.topics if t.key == key)
        assert {q.language for q in topic.queries} == {"ar", "en"}, key
    reg = next(t for t in plan.topics if t.key == "regulation")
    assert reg.source_ids == ["EG-003", "R-002"]  # legal sources only
    assert any("none verified" in n for n in plan.notes)


def test_queries_are_single_language():
    for name, cc in (("nadafa", "EG"), ("pharmastock", "KE")):
        plan = build_plan(load(name), sources_for(cc))
        for q in queries(plan):
            if q.language == "en" and not any(b.startswith("fields.known_competitors") for b in q.built_from):
                assert lang_of(q.text) == "en", q.text
            if q.language == "ar":
                assert lang_of(q.text) == "ar", q.text


def test_kenya_plan_english_and_no_verified_source():
    plan = build_plan(load("pharmastock"), sources_for("KE"))
    assert plan.country_code == "KE" and plan.languages == ["en"]
    assert plan.country_sources == NO_COUNTRY_SOURCE
    assert {q.language for q in queries(plan)} == {"en"}
    assert any("Kenya" in q.text for q in queries(plan))
    assert any("no KE source" in n for n in plan.notes)


def test_known_competitors_become_queries():
    plan = build_plan(load("nadafa"), sources_for("EG"))
    comp = next(t for t in plan.topics if t.key == "competitors")
    texts = [q.text for q in comp.queries]
    assert any(t.startswith("Ezhalha") for t in texts) and any(t.startswith("Filkhedma") for t in texts)
    assert split_competitors("spreadsheets, paper ledgers, wholesaler ordering apps") == [
        "spreadsheets", "paper ledgers", "wholesaler ordering apps"]


def test_one_topic_per_open_question():
    brief = load("nadafa")
    plan = build_plan(brief, sources_for("EG"))
    oq = [t for t in plan.topics if t.kind == "open_question"]
    assert [t.title for t in oq] == brief["open_questions"]
    assert all(t.queries[0].language == "ar" for t in oq)


@pytest.mark.parametrize("name,cc", [("nadafa", "EG"), ("pharmastock", "KE")])
def test_no_query_uses_an_unknown_field(name, cc):
    brief = copy.deepcopy(load(name))
    # Mark fields unknown but leave a sentinel value behind: the planner must check status, not value.
    for f in ("idea", "city", "target_customer", "known_competitors"):
        brief["fields"][f] = {"value": f"ZZ{f}", "status": "unknown", "source": None, "quote": None}
    plan = build_plan(brief, sources_for(cc))
    assert {"idea", "city", "target_customer", "known_competitors"} <= set(plan.unknown_fields)
    for q in queries(plan):
        assert "ZZ" not in q.text, q.text
        assert not any(b in q.built_from for b in
                       ("fields.idea", "fields.city", "fields.target_customer", "fields.known_competitors"))


def test_unknown_country_and_tags():
    brief = copy.deepcopy(load("pharmastock"))
    brief["fields"]["country"] = {"value": None, "status": "unknown", "source": None, "quote": None}
    brief["tags"]["country_code"]["value"] = "unknown"
    brief["tags"]["revenue_model"]["value"] = "unknown"
    plan = build_plan(brief, [s for s in SOURCES if not s["country_codes"]])
    assert plan.country_code == "unknown" and plan.country_sources == NO_COUNTRY_SOURCE
    assert any("country unknown" in n for n in plan.notes)
    reg = next(t for t in plan.topics if t.key == "regulation")
    assert reg.queries == [] and reg.skipped_reason  # regulation needs a country
    assert not any("tags.revenue_model" in q.built_from for q in queries(plan))
    built = [q for t in plan.topics if t.kind == "standard" for q in t.queries]  # open questions are verbatim
    assert built and not any("Kenya" in q.text for q in built)


def test_plan_is_json_serialisable():
    plan = build_plan(load("nadafa"), sources_for("EG"))
    again = ResearchPlan.model_validate(json.loads(plan.model_dump_json()))
    assert again == plan
