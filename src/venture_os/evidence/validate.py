"""Research Critic, rules part (the Evidence Validator). Plain code: the same answer every time.

Per claim it adds flags; per run it reports topics with no evidence. Flags:
- quote_not_found : the quote is not in the stored chunk (the claim must not be shown as a fact)
- undated         : the page has no publication date; only the retrieval date is known
- stale           : published longer ago than the source's max age (registry) or the default for the topic
- web_source      : the page is not from a registry source (lower trust; check before relying on it)
- other_country   : the quote names another country and not the brief's (may be a proxy market)
"""

from __future__ import annotations

from datetime import date

from venture_os.evidence.extract import quote_in
from venture_os.evidence.store import StoredChunk
from venture_os.onboarding.tags import COUNTRIES, mentions_country

DEFAULT_MAX_AGE_MONTHS = {"market_size": 36, "pricing": 18, "competitors": 24, "customer_pain": 36,
                          "regulation": 60}


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def claim_flags(claim: dict, chunk: StoredChunk, topic: str, country_code: str | None,
                today: date | None = None) -> list[str]:
    today = today or date.today()
    flags = []
    if not quote_in(claim.get("quote") or "", chunk.text):
        flags.append("quote_not_found")
    if chunk.published_at is None:
        flags.append("undated")
    else:
        limit = chunk.max_age_months or DEFAULT_MAX_AGE_MONTHS.get(topic.split("_question")[0], 36)
        if _months_between(chunk.published_at, today) > limit:
            flags.append("stale")
    if not chunk.source_id:
        flags.append("web_source")
    if country_code and country_code in COUNTRIES:
        text = claim.get("quote") or ""
        others = [c for c in COUNTRIES if c != country_code and mentions_country(text, c)]
        if others and not mentions_country(text, country_code):
            flags.append("other_country")
    return flags


def run_report(claims: list[dict], topic_keys: list[str]) -> dict:
    by_topic = {k: [c for c in claims if c["topic"] == k] for k in topic_keys}
    gaps = [k for k, cs in by_topic.items() if not any("quote_not_found" not in c["flags"] for c in cs)]
    counts: dict[str, int] = {}
    for c in claims:
        for f in c["flags"]:
            counts[f] = counts.get(f, 0) + 1
    usable = [c for c in claims if not ({"quote_not_found", "stale"} & set(c["flags"]))]
    return {
        "planned_topics": topic_keys,
        "claims": len(claims),
        "usable_claims": len(usable),
        "from_registry_sources": sum(1 for c in claims if "web_source" not in c["flags"]),
        "flag_counts": counts,
        "topics_without_evidence": gaps,
    }
