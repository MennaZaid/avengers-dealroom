"""Opportunity finder (Discover step 2, the core step "Find opportunities"). Agent with a tool loop.

1. Pain evidence in people's own words: the web research loop (agents/base.py: registry sources, SearXNG,
   fetch) on the pain topics, plus free APIs: Hacker News, Stack Exchange, GitHub issues, and App Store reviews
   of the most-rated competing apps. Everything is stored in Postgres (documents + chunks) and becomes a claim
   with a verbatim quote, URL and retrieval date.
2. Ideas: the founder's starting idea, sharpened, plus 3-5 alternative digital products built from the
   founder's skills, budget, time and values. With a model (prompts/opportunity_finder.md) ideas cite pain
   claim ids; without one, labelled rule templates are used. Generated text passes guardrails.check_output.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime

from venture_os.agents.base import Budget, Evidence, ResearchAgent, Toolbox, Trace
from venture_os.agents.brief_analyzer import DIGITAL_TYPES, DiscoverBrief
from venture_os.agents.research_planner import INDUSTRY_LABELS, ResearchPlan, lang_of
from venture_os.agents.schemas import Claim, Idea
from venture_os.guardrails import check_output
from venture_os.prompts import load_prompt
from venture_os.tools.fetch import Page, text_language
from venture_os.tools.search import SearchError

PAIN_TOPICS = ("customer_pain",)
DEV_TYPES = {"saas", "web_app", "api_or_dev_tool", "browser_extension"}
SE_SITE = {"api_or_dev_tool": "stackoverflow", "browser_extension": "superuser"}


class PainResearchAgent(ResearchAgent):
    name = "opportunity_finder"


def item_page(item) -> Page:
    text = item.text if len(item.text) >= 200 else f"{item.title}\n{item.text}"
    return Page(url=item.url, final_url=item.url, title=item.title[:300] or item.url, text=text,
                language=text_language(text), published_at=item.published, retrieved_at=datetime.now(UTC),
                content_hash=hashlib.sha256((item.url + "\n" + text).encode("utf-8")).hexdigest())


def api_queries(plan: ResearchPlan, db: DiscoverBrief) -> list[str]:
    """Short English queries for the APIs (their content is mostly English)."""
    qs = []
    for t in plan.topics:
        if t.key in ("customer_pain", "competitors"):
            qs += [q.text for q in t.queries if q.language == "en" and "reddit" not in q.text][:2]
    inds = (db.tags.get("industries") or {}).get("value") or []
    label = next((INDUSTRY_LABELS[i][0] for i in inds if i in INDUSTRY_LABELS), None)
    idea = db.required.get("idea")
    if idea and lang_of(idea) == "en":
        qs.insert(0, " ".join(idea.split()[:8]))
    if label:
        qs.append(f"{label} {db.product_type.label.replace('_', ' ')}")
    out, seen = [], set()
    for q in qs:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out[:3]


def gather_pain(plan: ResearchPlan, db: DiscoverBrief, toolbox: Toolbox, budget: Budget, trace: Trace,
                model: Callable | None, registry_pages: dict) -> list[Evidence]:
    topics = [t for t in plan.topics if t.key in PAIN_TOPICS or t.kind == "open_question"]
    agent = PainResearchAgent(topics, toolbox, budget, trace, model, registry_pages=registry_pages)
    agent.run()
    evidence = list(agent.result.evidence)
    apis = getattr(toolbox, "apis", None)
    if apis is None:
        return evidence
    country = plan.country_code.lower() if plan.country_code != "unknown" else "us"
    for q in api_queries(plan, db):
        calls = [("hn_search", lambda q=q: apis.hn_search(q)),
                 ("stackexchange_search",
                  lambda q=q: apis.stackexchange_search(q, SE_SITE.get(db.product_type.label, "webapps")))]
        if db.product_type.label in DEV_TYPES:
            calls.append(("github_issues", lambda q=q: apis.github_issues(q)))
        for name, call in calls:
            if not budget.take("searches"):
                trace.add("opportunity_finder", "budget_exhausted", kind="searches")
                return evidence
            try:
                items = call()
            except SearchError as e:
                trace.add("opportunity_finder", "api_failed", api=name, query=q, error=str(e)[:150])
                continue
            trace.add("opportunity_finder", "api_call", api=name, query=q, results=len(items),
                      sources=[i.url for i in items])
            for it in items:
                evidence.append(Evidence("pain", q, "opportunity_finder", toolbox.save_page(item_page(it))))
    # reviews of the most-rated competing apps in the target country's store (verbatim complaints)
    try:
        apps = apis.itunes_search(api_queries(plan, db)[0] if api_queries(plan, db) else plan.topics[0].title,
                                  country)
        trace.add("opportunity_finder", "api_call", api="itunes_search", results=len(apps),
                  sources=[a.url for a in apps])
        for app in sorted(apps, key=lambda a: -(a.extra.get("rating_count") or 0))[:2]:
            reviews = apis.appstore_reviews(app.extra["app_id"], country)
            trace.add("opportunity_finder", "api_call", api="appstore_reviews", app=app.title,
                      results=len(reviews), sources=[app.url])
            for rv in reviews:
                evidence.append(Evidence("pain", f"{app.title} reviews", "opportunity_finder",
                                         toolbox.save_page(item_page(rv))))
    except SearchError as e:
        trace.add("opportunity_finder", "api_failed", api="app_store", error=str(e)[:150])
    return evidence


# ---------- ideas ----------

TEMPLATES = {  # (product type, skills that fit it, English template, Arabic template)
    "template_or_asset": (("design", "excel", "notion", "writing", "تصميم", "كتابة"),
                          "Ready-made {topic} template pack for {who}", "حزمة قوالب جاهزة لـ{who} في {topic}"),
    "online_course": (("teach", "train", "expert", "pharmac", "marketing", "تدريس", "تعليم", "تسويق"),
                      "Short online course teaching {who} how to handle {topic}",
                      "كورس أونلاين قصير يعلّم {who} التعامل مع {topic}"),
    "ebook_or_guide": (("writing", "write", "research", "كتابة"),
                       "Practical guide for {who} on {topic}", "دليل عملي لـ{who} عن {topic}"),
    "browser_extension": (("python", "javascript", "coding", "programm", "developer", "برمجة", "مبرمج"),
                          "Browser extension that helps {who} with {topic}", "إضافة للمتصفح تساعد {who} في {topic}"),
    "community_or_membership": (("social media", "community", "marketing", "سوشيال", "تسويق"),
                                "Paid online community for {who} around {topic}", "مجتمع أونلاين مدفوع لـ{who} حول {topic}"),
    "saas": (("python", "coding", "programm", "developer", "software", "برمجة", "مبرمج"),
             "Simple web tool that lets {who} handle {topic}", "أداة ويب بسيطة تساعد {who} في {topic}"),
}


def _short(text: str | None, words: int = 10) -> str:
    return " ".join((text or "").rstrip(".").split()[:words])


TEMPLATE_NOTE = ("ASSUMPTION: format chosen by a rule template (no model); the pain evidence is about the problem, "
                 "not this format")


def rule_ideas(db: DiscoverBrief, pain_ids: list[str]) -> list[Idea]:
    lang = lang_of(db.required.get("idea") or db.required.get("target_market") or "")
    who = _short(db.optional.get("target_customer") or db.required.get("target_market"), 8) or \
        ("your customers" if lang == "en" else "عملائك")
    topic = _short(db.optional.get("problem") or db.required.get("idea"), 10) or "the problem"
    skills = (db.required.get("skills") or "").lower()
    start = Idea(id="I0", title=_short(db.required.get("idea"), 14) or "Starting idea",
                 description=f"{db.required.get('idea') or 'unknown'} - for {db.required.get('target_market') or 'unknown'}",
                 product_type=db.product_type.label if db.product_type.group == "digital_product" else "other_digital",
                 origin="starting_idea", built_by="rules", pain=topic, pain_claim_ids=pain_ids,
                 why_founder="the founder's own starting idea",
                 assumptions=["Sharpened by rules (no model): the starting idea restated with its target market"])
    ranked = sorted(TEMPLATES.items(), key=lambda kv: -sum(1 for s in kv[1][0] if s in skills))
    alts = []
    for ptype, (fit, en, ar) in ranked:
        if ptype == start.product_type or len(alts) >= 4:
            continue
        fits = [s for s in fit if s in skills]
        alts.append(Idea(
            id=f"I{len(alts) + 1}", title=(en if lang == "en" else ar).format(who=who, topic=topic),
            description=f"A {ptype.replace('_', ' ')} version of the same opportunity.", product_type=ptype,
            origin="alternative", built_by="rules", pain=topic, pain_claim_ids=pain_ids,
            why_founder=(f"matches the founder's skills: {', '.join(fits)}" if fits else
                         "low build cost; no direct skill match found"),
            assumptions=[TEMPLATE_NOTE]))
    return [start, *alts]


MODEL_QUOTES = 12  # quotes sent to the model; small local models on a CPU slow down sharply with long prompts
QUOTE_CHARS = 240


def model_ideas(db: DiscoverBrief, pain: list[Claim], chat: Callable, model_id: str,
                why: list[str] | None = None) -> list[Idea] | None:
    """Ideas from the model, or None (the reason is appended to `why`)."""
    why = why if why is not None else []
    ids = {f"P{i}": c for i, c in enumerate(pain[:MODEL_QUOTES], 1)}
    payload = {"brief": db.required | {"problem": db.optional.get("problem")},
               "pain_quotes": {k: c.quote[:QUOTE_CHARS] for k, c in ids.items()},
               "allowed_product_types": [*DIGITAL_TYPES, "other_digital"]}
    try:
        user = f"<untrusted>{json.dumps(payload, ensure_ascii=False)}</untrusted>"
        data = json.loads(chat([{"role": "system", "content": load_prompt("opportunity_finder")},
                                {"role": "user", "content": user}]))
    except Exception as e:  # noqa: BLE001 - fall back to rules, saying why
        why.append(f"model call failed ({type(e).__name__})")
        return None
    if not isinstance(data, dict):
        why.append("model returned no JSON object")
        return None
    raw = [data.get("starting_idea"), *(data.get("alternatives") or [])[:5]]
    ideas = []
    for i, it in enumerate(raw):
        if not isinstance(it, dict) or not it.get("title"):
            continue
        ptype = it.get("product_type") if it.get("product_type") in [*DIGITAL_TYPES, "other_digital"] else "other_digital"
        cited = [ids[k].id for k in it.get("pain_claim_ids") or [] if k in ids]
        idea = Idea(id=f"I{len(ideas)}", title=str(it["title"])[:200], description=str(it.get("description", ""))[:800],
                    product_type=ptype, origin="starting_idea" if i == 0 else "alternative", built_by=model_id,
                    pain=str(it.get("pain", ""))[:300], pain_claim_ids=cited,
                    why_founder=str(it.get("why_founder", ""))[:300],
                    assumptions=[*(str(a)[:200] for a in it.get("assumptions") or []),
                                 *([] if cited else ["ASSUMPTION: no pain quote cited for this idea"])])
        if check_output(f"{idea.title} {idea.description} {idea.pain} {idea.why_founder}"):
            why.append(f"idea '{idea.title[:40]}' broke a must-never rule and was dropped")
            continue  # must-never rules (income promises, fake urgency ...): not shown
        ideas.append(idea)
    if not ideas or ideas[0].origin != "starting_idea":
        why.append("model did not return a usable sharpened starting idea")
        return None
    if len(ideas) < 2:
        why.append("model returned no usable alternative")
        return None
    return ideas


def propose_ideas(db: DiscoverBrief, pain: list[Claim], chat: Callable | None, model_id: str | None) -> list[Idea]:
    why: list[str] = []
    if chat is not None:
        got = model_ideas(db, pain, chat, model_id or "model", why)
        if got:
            return got
    ideas = rule_ideas(db, [c.id for c in pain if c.type == "fact"][:12])
    if why:  # the model was on but its ideas could not be used: say so in the output
        ideas[0].assumptions.append(f"Model ideas not used ({'; '.join(why)}): all ideas below come from templates")
    return ideas
