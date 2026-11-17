"""Phase 5 Launch, core steps "Open the store; deliver automatically" (STUBBED).

A store page draft and 3 launch post drafts. Nothing is posted: post() refuses unless approval.py confirms the
founder approved that exact post, and even then it only logs "post (MOCKED)". No urgency, reviews or user counts.
Automatic delivery is delivery.py (MOCKED, idempotent per order).
-> outputs/phase5_step1_store_page.md, outputs/phase5_step2_launch_posts.md
"""

from __future__ import annotations

from typing import Any

from venture_os import payments
from venture_os.agents import stubbed

POST_ACTION = "publish_launch_post"


def run(brief_id: str, *, brief: Any = None):
    if brief is None:
        from venture_os.onboarding.briefs import load_brief
        brief = load_brief(brief_id)
    idea = brief.known("idea") or "unknown"
    customer = brief.known("target_customer") or "unknown"
    problem = brief.known("problem") or "unknown"
    price = brief.known("business_model") or "unknown (see phase4_step1_pricing.md)"

    store = stubbed.header(brief_id, "Phase 5, step 1: store page draft")
    store += ["Status: DRAFT, not published (MOCKED).", "",
              f"**Product:** {stubbed.cell(idea)}", f"**For:** {stubbed.cell(customer)}",
              f"**Problem it addresses:** {stubbed.cell(problem)}", (f"**Price (founder's stated model):** "
              f"{stubbed.cell(price)}"), "",
              ("**After purchase:** access is delivered automatically once, by `src/venture_os/delivery.py` "
              "(MOCKED: no real payment; a refund revokes access, see `src/venture_os/refunds.py`)."), ""]
    stubbed.write_checked(5, 1, "store_page", "\n".join(store) + "\n")
    stubbed.log_step("launch", "draft_store_page", brief_id)

    drafts = posts(idea, customer, problem)
    md = stubbed.header(brief_id, "Phase 5, step 2: launch post drafts")
    md += [("Drafts only. Nothing is posted: each post needs the founder's approval through approval.py, and "
           "posting is MOCKED."), ""]
    for i, p in enumerate(drafts, 1):
        md += [f"## Post {i}", "", p, ""]
    stubbed.write_checked(5, 2, "launch_posts", "\n".join(md) + "\n")
    stubbed.log_step("launch", "draft_launch_posts", brief_id, posts=len(drafts))
    return stubbed.record_gate(5, "launch", "go",
                               "Store page and posts are drafts; nothing goes out without the founder's approval.",
                               "drafts pass the guardrails and every external action needs approval -> go", brief_id)


def posts(idea: str, customer: str, problem: str) -> list[str]:
    return [
        (f"We are building {idea} for {customer}. The problem: {problem}. It is in development; if this sounds "
        "useful, the waitlist link is in the comments."),
        (f"Question for {customer}: how do you handle this today? \"{problem}\". We would like to hear what you "
        "already use and what is missing."),
        (f"Early version of {idea} is ready to try with a few people. Tell us honestly whether it solves "
        "your problem."),
    ]


def post(brief_id: str, text: str, approval: dict | None) -> str:
    """MOCKED posting of one launch post; refused without the founder's approval of this exact text."""
    payments.require_founder_approval(str(brief_id), POST_ACTION, {"text": text}, approval)
    stubbed.log_action("launch", "post (MOCKED)", sources=[], model=None, cost=0, approved_by="founder",
                       brief_id=str(brief_id), mocked=True)
    return "MOCKED: not posted, nothing was sent"
