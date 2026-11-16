from pathlib import Path

import yaml

SOURCES = Path(__file__).resolve().parents[2] / "config" / "sources"
SOURCE_FILES = ["registry_seed.yaml", "case_studies.yaml", "egypt.yaml"]
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
