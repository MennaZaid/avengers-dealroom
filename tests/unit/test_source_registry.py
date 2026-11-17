from pathlib import Path

import yaml

SOURCES = Path(__file__).resolve().parents[2] / "config" / "sources"
SOURCE_FILES = ["registry_seed.yaml", "case_studies.yaml", "egypt.yaml", "digital.yaml"]
SCOPES = {"global", "region", "country", "industry"}


def _load(name):
    return yaml.safe_load((SOURCES / name).read_text(encoding="utf-8")) or []


def _sources():
    for f in SOURCE_FILES:
        for e in _load(f):
            yield f, e


def test_source_ids_unique_across_files():
    ids = [e["id"] for _, e in _sources()]
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})


def test_sources_have_required_fields():
    for f, e in _sources():
        assert e.get("source_name"), (f, e["id"])
        assert e.get("tier") in {"A", "B", "C"}, (f, e["id"], e.get("tier"))
        assert e.get("scope") in SCOPES, (f, e["id"])
        assert e.get("crawl", "full") in {"full", "metadata", "none"}, (f, e["id"])


def test_no_tracking_params():
    for f, e in _sources():
        assert "utm_" not in str(e.get("url") or ""), (f, e["id"])


def test_corpus_and_rules_load():
    corpus = _load("corpus_seed.yaml")
    assert corpus and all(c["status"] in {"candidate", "keep", "maybe", "cut"} for c in corpus)
    rules = _load("discovery_rules.yaml")
    assert [int(r["step"]) for r in rules] == list(range(1, len(rules) + 1))


def test_digital_pack_and_registry_updates():
    ids = {e["id"] for _, e in _sources()}
    updates = _load("registry_updates.yaml")
    assert set(updates) <= ids  # only real sources are changed
    assert all(len(u.get("reason", "")) >= 5 for u in updates.values())  # every change has a reason
    assert all(u.get("product_scope", "any") in {"digital", "physical", "any"} for u in updates.values())
    digital = _load("digital.yaml")
    assert all(e["url"].startswith("https://") and e["verified"] is False for e in digital)
    assert all(e["product_scope"] in {"digital", "any"} and e.get("limitations") for e in digital)
    assert all(e["access_type"] in {"api", "search_only", "polite_fetch", "manual_upload", "manual"} for e in digital)
    corpus = _load("corpus_seed.yaml") + _load("corpus_digital.yaml")
    cids = [c["id"] for c in corpus]
    assert len(cids) == len(set(cids))
    summaries = (SOURCES.parent / "corpus" / "summaries")
    assert {p.stem for p in summaries.glob("M-*.md")} <= set(cids)  # every summary belongs to a corpus item
    rules = _load("discovery_rules.yaml") + _load("discovery_rules_digital.yaml")
    assert [int(r["step"]) for r in rules] == list(range(1, len(rules) + 1))
