"""Deterministic validation of sources proposed by crawler agents (decision D8: option a).

No LLM is involved, so text on a fetched page cannot argue its way into the registry.
Verdicts:
  rejected    - a hard check failed
  provisional - an official government body found by the discovery rules: auto-added at tier B,
                labelled unconfirmed, expires in 30 days unless an admin confirms it
  queued      - passed the checks but is not an official body: waits for an admin
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

PROVISIONAL_DAYS = 30
OFFICIAL_KINDS = {"statistics_office", "central_bank", "company_registry", "regulator"}

# Government second-level labels under country-code TLDs (gov.eg, gob.mx, gouv.fr, go.jp, govt.nz ...).
GOV_LABELS = {"gov", "gob", "gouv", "go", "govt", "gv", "admin", "government"}
# Official without a country label.
OFFICIAL_SUFFIXES = (".gov", ".int", ".europa.eu", ".gc.ca", ".gov.uk")
SHORTENERS = {"bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "is.gd", "buff.ly", "rebrand.ly", "cutt.ly"}
INJECTION_PATTERNS = re.compile(
    r"ignore (all |any )?(previous|prior) instructions|you are (an? )?(ai|assistant|llm)|system prompt"
    r"|add this (site|source|domain) to",
    re.IGNORECASE,
)

Verdict = Literal["rejected", "provisional", "queued"]


@dataclass
class Candidate:
    url: str
    source_name: str
    country_code: str | None  # ISO 3166-1 alpha-2
    kind: str  # statistics_office | central_bank | company_registry | regulator | other
    proposed_by: str
    found_via: str = ""


@dataclass
class PageProbe:
    """What the crawler observed when it fetched the candidate (filled by the network layer)."""

    http_status: int | None
    robots_allowed: bool | None
    text_sample: str = ""
    has_dated_figure: bool = False
    license_text: str | None = None


@dataclass
class Result:
    verdict: Verdict
    checks: dict[str, dict] = field(default_factory=dict)
    tier: str | None = None
    expires_at: datetime | None = None

    def reasons(self) -> list[str]:
        return [f"{k}: {v['detail']}" for k, v in self.checks.items() if not v["passed"]]


def domain_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def is_official_domain(domain: str, country_code: str | None) -> bool:
    if domain.endswith(OFFICIAL_SUFFIXES) or domain in {s.lstrip(".") for s in OFFICIAL_SUFFIXES}:
        return True
    labels = domain.split(".")
    if len(labels) < 3:
        return False
    tld, second = labels[-1], labels[-2]
    if second not in GOV_LABELS:
        return False
    return country_code is None or tld == country_code.lower()


def validate(
    c: Candidate,
    known_domains: set[str],
    fetch: Callable[[str], PageProbe],
    now: datetime | None = None,
) -> Result:
    now = now or datetime.now(UTC)
    checks: dict[str, dict] = {}

    def check(name: str, passed: bool, detail: str, hard: bool = True) -> None:
        checks[name] = {"passed": passed, "detail": detail, "hard": hard}

    parts = urlsplit(c.url)
    dom = domain_of(c.url)

    # URL hygiene (no network)
    check("https", parts.scheme == "https", f"scheme is {parts.scheme or 'missing'}")
    try:
        ipaddress.ip_address(dom)
        is_ip = True
    except ValueError:
        is_ip = False
    check("not_ip_address", not is_ip, dom)
    check("not_shortener", dom not in SHORTENERS, dom)
    check("not_punycode", "xn--" not in dom, "punycode domains can imitate official names")
    check("no_credentials_in_url", parts.username is None and parts.password is None, "user info in URL")
    check("not_duplicate", dom not in known_domains, f"{dom} already in registry")

    # Page probe (network layer is injected so this stays testable offline)
    probe = fetch(c.url)
    check("reachable", probe.http_status == 200, f"HTTP {probe.http_status}")
    check("robots_allowed", probe.robots_allowed is True, f"robots allows crawl: {probe.robots_allowed}")
    check(
        "no_injection_text",
        not INJECTION_PATTERNS.search(probe.text_sample or ""),
        "page text addressed to an AI agent",
    )
    check("has_dated_figure", probe.has_dated_figure, "needs at least one citable, dated figure", hard=False)
    check("license_stated", bool(probe.license_text), probe.license_text or "UNKNOWN", hard=False)

    official = is_official_domain(dom, c.country_code)
    check("official_domain", official, f"{dom} for country {c.country_code}", hard=False)

    if any(not v["passed"] and v["hard"] for v in checks.values()):
        return Result("rejected", checks)
    if official and c.kind in OFFICIAL_KINDS and probe.has_dated_figure:
        return Result("provisional", checks, tier="B", expires_at=now + timedelta(days=PROVISIONAL_DAYS))
    return Result("queued", checks)
