"""Discover relevance: pain pages unrelated to customer + pain are dropped before claim extraction, and the gate
says repeat or stop when too few survive. Replay mode: a stand-in embedding, never a live model."""

from types import SimpleNamespace as NS

from venture_os import gates
from venture_os.agents.base import Evidence, Trace
from venture_os.orchestrator import relevance_filter

CFG = {"relevance": {"min_similarity": 0.5}}


def page(url, text):
    return Evidence("pain", "q", "opportunity_finder", [NS(url=url, text=text)])


def fake_embed(texts):  # 1-d "embedding": pages mentioning invoices point the same way as the pain statement
    return [[1.0, 0.0] if "invoice" in t else [0.0, 1.0] for t in texts]


def test_unrelated_pages_are_dropped_and_traced():
    trace = Trace()
    ev = [page("https://a.example/1", "freelancers chasing late invoice payments"),
          page("https://b.example/2", "best pizza in Cairo")]
    kept, info = relevance_filter(ev, "freelance designers late invoice payments", CFG, trace, embed=fake_embed)
    assert [e.chunks[0].url for e in kept] == ["https://a.example/1"]
    assert info == {"ran": True, "kept": 1, "dropped": 1}
    assert any(x["action"] == "drop_page" and x["url"] == "https://b.example/2" for x in trace.events)


def test_without_an_embedding_model_nothing_is_dropped():
    def broken(texts):
        raise ConnectionError("no ollama")
    ev = [page("https://b.example/2", "best pizza")]
    kept, info = relevance_filter(ev, "late invoices", CFG, Trace(), embed=broken)
    assert kept == ev and info["ran"] is False


def test_tests_never_embed(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "replay")
    _kept, info = relevance_filter([page("u", "x")], "late invoices", CFG, Trace())
    assert info["ran"] is False


def _gate(kept, dropped):
    return gates.evaluate_discover("digital_product", "template", [], [], [], [],
                                   relevance={"ran": True, "kept": kept, "dropped": dropped})


def test_gate_stops_when_no_page_is_about_the_pain():
    g = _gate(0, 9)
    assert g.recommendation == "stop" and "relevance filter" in g.reasons[0]


def test_gate_repeats_when_too_few_relevant_pages():
    g = _gate(1, 5)
    check = next(c for c in g.checks if c["check"] == "relevant_pages")
    assert not check["passed"] and g.recommendation in ("repeat", "stop")
    assert any(x.startswith("relevant_pages") for x in g.collect_next) or g.recommendation == "stop"


def test_pain_queries_use_customer_and_pain_not_the_category():
    from venture_os.agents.research_planner import _standard_queries

    w = NS(target=("freelance designers", ["fields.target_customer"]),
           problem=("late invoice payments", ["fields.problem"]), place=("Cairo", ["tags.city"]),
           industry=("design services", ["tags.industries"]), country=("Egypt", ["tags.country_code"]))
    qs = [q for q in _standard_queries("customer_pain", "en", w, []) if q]
    texts = [q.text for q in qs]
    assert "freelance designers late invoice payments" in texts
    assert not any("tags.industries" in q.built_from for q in qs)          # no product-category query
