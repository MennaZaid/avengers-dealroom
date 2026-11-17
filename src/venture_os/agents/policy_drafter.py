"""Phase 4 Commercial, steps 3-5: draft terms, privacy policy and refund policy (plain code, no model).

Every draft starts with "DRAFT — not legal advice". Country law is cited only from official sources in the
source registry (use = 'legal', matching the brief's country); otherwise the draft says
"No verified official source found for <country>". The refund policy describes what refunds.py does: the founder
approves each refund, and an approved refund revokes access to the product.
"""

from __future__ import annotations

from typing import Any

DRAFT_LABEL = "DRAFT — not legal advice. Have it reviewed by a qualified lawyer before use."


def legal_sources(country_code: str | None) -> list[dict]:
    """Official legal sources for the country from the registry (read-only role). [] when none or unreachable."""
    if not country_code or country_code == "unknown":
        return []
    try:
        from venture_os.api.db import connect
        with connect("vos_app") as conn:
            rows = conn.execute(
                "SELECT id, source_name, url FROM sources WHERE active AND use = 'legal' AND url IS NOT NULL "
                "AND %s = ANY(country_codes) ORDER BY tier, id LIMIT 5", (country_code,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001 - no database: the drafts say no verified source, never invent one
        return []


def _law_section(country: str, sources: list[dict]) -> list[str]:
    if not sources:
        return ["## Country law", "", (f"No verified official source found for {country}. Check the local "
                "consumer-protection and data-protection rules with a lawyer."), ""]
    return ["## Country law (official sources to check)", ""] + [
        f"- {s['source_name']}: {s['url']} (registry `{s['id']}`)" for s in sources] + [""]


def drafts(brief: Any, sources: list[dict]) -> dict[str, list[str]]:
    """name -> markdown lines (without the Brief id header)."""
    product = brief.known("idea") or "the product"
    country = brief.known("country") or str(brief.tag("country_code") or "the founder's country")
    values = brief.known("values")
    law = _law_section(country, sources)
    head = [f"**{DRAFT_LABEL}**", ""]
    return {
        "terms": head + [f"# Terms of service (draft): {product}", "",
                         ("- The service is a digital product, provided as described on its page; features may "
                         "change while it is in development."),
                         "- No result, income or outcome is promised.",
                         "- Users must not misuse the service or try to access other users' data.",
                         "- The founder may suspend access that breaks these terms, after telling the user why.",
                         ""] + law,
        "privacy": head + [f"# Privacy policy (draft): {product}", "",
                           ("- Only what the product needs is collected: an email address for the waitlist and "
                           "account access."),
                           ("- Passwords are never stored in plain text and card numbers are never stored; no "
                           "payment provider is connected in this prototype (payments are MOCKED)."),
                           ("- Data is not sold or shared for advertising. Users can ask for their data to be "
                           "deleted."),
                           *([f"- The founder's stated value: {values}."] if values else []), ""] + law,
        "refund": head + [f"# Refund policy (draft): {product}", "",
                          ("- A buyer can ask for a refund; the founder checks and approves each refund. Refunds "
                          "are never automatic."),
                          ("- An approved refund revokes access to the product (this is what refunds.py and "
                          "delivery.py do)."),
                          "- In this prototype refunds are MOCKED: no money is returned or moved.", ""] + law,
    }
