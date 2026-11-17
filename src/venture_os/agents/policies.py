"""Phase 4 Commercial setup: draft terms, privacy policy and refund policy (STUBBED).

Headed "DRAFT, not legal advice; have it reviewed". The refund policy describes what refunds.py actually does:
a refund needs the founder's approval and revokes access to the product. -> outputs/phase4_step2_policies.md
"""

from __future__ import annotations

from typing import Any

from venture_os.agents import stubbed

DISCLAIMER = "DRAFT, not legal advice; have it reviewed by a qualified lawyer in your country before use."


def run(brief_id: str, *, brief: Any = None):
    if brief is None:
        from venture_os.onboarding.briefs import load_brief
        brief = load_brief(brief_id)
    product = brief.known("idea") or "the product"
    country = brief.known("country") or "unknown (to be confirmed)"
    values = brief.known("values")
    md = stubbed.header(brief_id, "Phase 4, step 2: draft policies")
    md += [f"> {DISCLAIMER}", "", f"Product: {stubbed.cell(product)} · Country: {stubbed.cell(country)}", "",
           "## Terms of service (draft)", "",
           ("- The service is a digital product provided as described on its page; features may change while it is "
           "in development."),
           "- No result, income or outcome is promised.",
           "- Users must not misuse the service or try to access other users' data.",
           "- The founder may suspend access that breaks these terms, after telling the user why.", "",
           "## Privacy policy (draft)", "",
           "- We collect only what the product needs: an email address for the waitlist and account access.",
           ("- We never store passwords in plain text and never store card numbers; payments would be handled "
           "by a payment provider (none is connected in this prototype: MOCKED)."),
           "- Data is not sold or shared for advertising. Users can ask for their data to be deleted.",
           *([f"- Founder's stated value: {stubbed.cell(values)}."] if values else []), "",
           "## Refund policy (draft)", "",
           "- A buyer can ask for a refund; the founder checks and approves each refund (no automatic refunds).",
           ("- When a refund is approved, the order is marked refunded and access to the product is revoked "
           "(this is what refunds.py and delivery.py do)."),
           "- In this prototype refunds are MOCKED: no money is returned or moved.", ""]
    stubbed.write_checked(4, 2, "policies", "\n".join(md) + "\n")
    stubbed.log_step("policy_writer", "draft_policies", brief_id, documents=["terms", "privacy", "refund"])
    return stubbed.record_gate(4, "policies", "go",
                               "Terms, privacy and refund drafts exist and are marked as drafts for legal review.",
                               "all three drafts present and labelled DRAFT -> go; otherwise repeat", brief_id)
