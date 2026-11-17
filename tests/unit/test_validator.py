from datetime import UTC, datetime

from venture_os.registry.validator import Candidate, PageProbe, is_official_domain, validate

NOW = datetime(2026, 11, 16, tzinfo=UTC)
GOOD = PageProbe(http_status=200, robots_allowed=True, text_sample="Population 2025: 107m", has_dated_figure=True)


def cand(url, kind="statistics_office", cc="EG"):
    return Candidate(url=url, source_name="x", country_code=cc, kind=kind, proposed_by="run-1")


def test_official_domain_patterns():
    assert is_official_domain("www.capmas.gov.eg", "EG")
    assert is_official_domain("www.inegi.gob.mx", "MX")
    assert is_official_domain("data.census.gov", "US")
    assert is_official_domain("ec.europa.eu", None)
    assert not is_official_domain("capmas-gov-eg.com", "EG")
    assert not is_official_domain("stats.gov.eg.evil.com", "EG")
    assert not is_official_domain("www.capmas.gov.eg", "MX")  # wrong country


def test_official_body_becomes_provisional_tier_b():
    r = validate(cand("https://www.capmas.gov.eg/stats"), set(), lambda u: GOOD, now=NOW)
    assert r.verdict == "provisional" and r.tier == "B"
    assert (r.expires_at - NOW).days == 30


def test_non_official_is_queued_for_admin():
    r = validate(cand("https://egypt-market-blog.com/a", kind="other"), set(), lambda u: GOOD, now=NOW)
    assert r.verdict == "queued"


def test_official_domain_without_figure_is_queued():
    probe = PageProbe(200, True, "Welcome", has_dated_figure=False)
    assert validate(cand("https://www.capmas.gov.eg"), set(), lambda u: probe).verdict == "queued"


def test_hard_failures_reject():
    cases = [
        "http://www.capmas.gov.eg",  # not https
        "https://bit.ly/abc",  # shortener
        "https://192.168.1.1/x",  # IP address
        "https://xn--cpmas-1ta.gov.eg",  # punycode lookalike
        "https://user:pw@www.capmas.gov.eg",  # credentials in URL
    ]
    for url in cases:
        assert validate(cand(url), set(), lambda u: GOOD).verdict == "rejected", url


def test_duplicate_robots_and_unreachable_reject():
    assert validate(cand("https://www.capmas.gov.eg"), {"www.capmas.gov.eg"}, lambda u: GOOD).verdict == "rejected"
    blocked = PageProbe(200, False, "", True)
    assert validate(cand("https://www.capmas.gov.eg"), set(), lambda u: blocked).verdict == "rejected"
    down = PageProbe(404, True, "", True)
    assert validate(cand("https://www.capmas.gov.eg"), set(), lambda u: down).verdict == "rejected"


def test_page_mentioning_a_system_prompt_is_rejected_even_on_official_site():
    evil = PageProbe(200, True, "This page describes a system prompt for chat assistants.", True)
    r = validate(cand("https://www.capmas.gov.eg"), set(), lambda u: evil)
    assert r.verdict == "rejected"
    assert any("no_injection_text" in x for x in r.reasons())
