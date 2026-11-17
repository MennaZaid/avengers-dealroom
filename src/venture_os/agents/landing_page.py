"""Phase 2 Validate: landing-page draft for the demand test. MOCKED: nothing is published or sent.

    from venture_os.agents import landing_page
    draft = landing_page.run(brief_id, canvas)     # declares the demand test FIRST, then drafts the page
    landing_page.publish(draft, approval)          # refused unless the founder approved this exact draft

Order matters: gates.plan_demand_test(100, 14) is called and written to
outputs/phase2_step2_demand_test_plan.md before any copy is generated, so the threshold is fixed before any result.
The page is one self-contained HTML file (no external URLs, fonts or scripts). The model writes copy only (JSON),
never HTML; all copy is HTML-escaped and checked by guardrails.check_output() plus the bans below. If the model is
off or its JSON is bad twice, the copy comes from the Lean Canvas.
"""

from __future__ import annotations

import hashlib
import html
import importlib
import json
import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

from venture_os import gates
from venture_os.agents.business_designer import INCOME_PATTERNS
from venture_os.decision_log import log_action
from venture_os.guardrails import check_output
from venture_os.outputs import write_output
from venture_os.prompts import load_prompt

Chat = Callable[[list[dict]], str]
TARGET, DAYS = 100, 14
PUBLISH_ACTION = "publish_landing_page"
MOCK_MESSAGE = "MOCKED: not published, nothing was sent"

# Copy that must never appear: testimonials, reviews, user counts, countdowns, scarcity, income claims.
BANNED = [re.compile(p, re.IGNORECASE) for p in (
    r"testimonial", r"\breviews?\b", r"\brated\b", r"\bstars?\b", r"★",
    r"\d[\d,.]*\+?\s*(people|users|customers|members|families|pharmacies|businesses|founders)\b",
    r"\b(join|joined|joining)\s+(over\s+|more than\s+)?\d", r"\balready\s+(joined|signed)",
    r"countdown", r"\bhurry\b", r"last chance", r"limited (time|spots|places|offer)",
    r"\bonly\s+\d+\s+(left|spots|places)", r"\b(ends|closing)\s+(today|tonight|soon)", r"don'?t miss",
    r"تقييم", r"آراء العملاء", r"عرض لفترة محدودة", r"آخر فرصة", r"\d+\s*(شخص|عميل|مستخدم|أسرة)", r"عداد",
)] + INCOME_PATTERNS

TEXT = {
    "en": {"banner": "DRAFT — not published (MOCKED)", "email": "Email", "cta": "Join the waitlist",
           "problem": "The problem", "offer": "What we are building",
           "note": "This product is in development. Joining the waitlist only means we may email you when it is "
                   "ready to try."},
    "ar": {"banner": "مسودة — غير منشورة (MOCKED)", "email": "البريد الإلكتروني", "cta": "انضم لقائمة الانتظار",
           "problem": "المشكلة", "offer": "ما الذي نبنيه",
           "note": "هذا المنتج قيد التطوير. الانضمام لقائمة الانتظار يعني فقط أننا قد نراسلك عندما يصبح جاهزاً للتجربة."},
}


class LandingDraft(BaseModel):
    brief_id: str
    brief_version: int | None = None
    language: Literal["en", "ar"]
    copy_text: dict  # headline, subheadline, problem, benefits, cta
    html: str
    sha256: str
    demand_test: dict  # the DemandTest declared before the page was drafted
    built_by: str
    model: str | None = None
    notes: list[str] = []
    dropped: list[str] = []


def banned(text: str) -> str | None:
    """Name of the first rule the text breaks, or None."""
    rules = check_output(text)
    if rules:
        return rules[0]
    return next((p.pattern for p in BANNED if p.search(text)), None)


def run(brief_id: str, canvas: Any, *, brief: Any = None, chat: Chat | None | Literal["auto"] = "auto",
        target: int = TARGET, days: int = DAYS) -> LandingDraft:
    # 1. The threshold is fixed before anything else happens.
    test = gates.plan_demand_test(target=target, days=days)
    write_output(2, 2, "demand_test_plan", _plan_markdown(str(brief_id), test))
    write_output(2, 2, "demand_test_plan", json.dumps({"brief_id": str(brief_id), **test.model_dump()}), ext="json")
    log_action("landing_page", "plan_demand_test", sources=[], model=None, cost=0, approved_by=None,
               brief_id=str(brief_id), metric=test.metric, target=test.target, days=test.days,
               declared_at=test.declared_at)

    if brief is None:
        from venture_os.onboarding.briefs import load_brief
        brief = load_brief(brief_id)
    lang = _language(brief)
    notes: list[str] = []
    copy, dropped = _rule_copy(canvas, lang), []
    model_name, cost = None, 0.0
    if chat == "auto":
        chat, model_name = _default_chat()
    if chat is None:
        notes.append("Copy written by rules from the Lean Canvas: no model is configured.")
    else:
        from venture_os.llm.client import usage_mark, usage_summary
        mark = usage_mark()
        raw = _ask_model(chat, canvas, lang)
        cost = usage_summary(since=mark)["cost_usd"]
        if raw is None:
            notes.append("The model returned no valid JSON after one retry: copy written by rules.")
            model_name = None
        else:
            model_name = model_name or "model"
            dropped = _merge_copy(copy, raw)
            notes.append(f"Copy written by {model_name}; every line checked against the must-never rules.")
    for key in ("headline", "subheadline", "problem", "cta"):  # rule copy is checked too
        if copy.get(key) and banned(copy[key]):
            dropped.append(f"{key}: {banned(copy[key])}")
            copy[key] = TEXT[lang]["cta"] if key == "cta" else ""
    copy["benefits"] = [b for b in copy.get("benefits", []) if not banned(b)]

    page = render_html(copy, lang, test, str(brief_id))
    if check_output(page):
        raise RuntimeError(f"landing page failed the output guardrail: {check_output(page)}")
    digest = hashlib.sha256(page.encode("utf-8")).hexdigest()
    write_output(2, 2, "landing_page", page, ext="html")
    log_action("landing_page", "draft_landing_page", sources=[], model=model_name, cost=cost, approved_by=None,
               brief_id=str(brief_id), sha256=digest, mocked=True, language=lang, dropped=dropped)
    return LandingDraft(brief_id=str(brief_id), brief_version=getattr(brief, "version", None), language=lang,
                        copy_text=copy, html=page, sha256=digest, demand_test=test.model_dump(),
                        built_by=f"rules + {model_name}" if model_name else "rules", model=model_name,
                        notes=notes, dropped=dropped)


def publish(draft: LandingDraft, approval: dict | None = None) -> str:
    """MOCKED publish. Refused unless approval.py holds a founder approval for this exact draft (sha256).
    Even when approved, nothing leaves the machine: it only logs "publish (MOCKED)"."""
    digest = hashlib.sha256(draft.html.encode("utf-8")).hexdigest()
    reason = None
    if digest != draft.sha256:
        reason = "the draft changed after it was hashed"
    elif not approval or approval.get("approved_by") != "founder" or approval.get("content_hash") != digest \
            or approval.get("action") != PUBLISH_ACTION:
        reason = "no founder approval for this exact draft"
    else:
        reason = _approval_store_refuses(draft.brief_id, digest)
    if reason:
        log_action("landing_page", "publish_refused", sources=[], model=None, cost=0, approved_by=None,
                   brief_id=draft.brief_id, sha256=digest, reason=reason)
        raise PermissionError(f"publish refused: {reason}")
    log_action("landing_page", "publish (MOCKED)", sources=[], model=None, cost=0, approved_by="founder",
               brief_id=draft.brief_id, sha256=digest, mocked=True)
    return MOCK_MESSAGE


def _approval_store_refuses(brief_id: str, digest: str) -> str | None:
    """The approval dict alone is not trusted: approval.py must confirm it. Fails closed.
    TODO(approval.py): needs has_founder_approval(brief_id, action, content_hash) -> bool (not on main yet)."""
    try:
        approval = importlib.import_module("venture_os.approval")
    except ImportError:
        return "approval.py is not available, so no founder approval can be verified"
    check = getattr(approval, "has_founder_approval", None)
    if check is None:
        return "approval.py has no has_founder_approval() yet"
    ok = check(brief_id=brief_id, action=PUBLISH_ACTION, content_hash=digest)
    return None if ok is True else "approval.py has no founder approval for this exact draft"


# ---------- copy ----------

def _language(brief: Any) -> Literal["en", "ar"]:
    langs = brief.tag("languages") if hasattr(brief, "tag") else []
    first = langs[0] if isinstance(langs, list) and langs else langs
    return "ar" if first == "ar" else "en"


def _first(canvas: Any, box: str, skip_composed: bool = False) -> str:
    for e in canvas.boxes.get(box, []):
        if e.basis == "UNKNOWN" or (skip_composed and e.by == "rules" and e.basis == "ASSUMPTION"):
            continue
        return e.text
    return ""


def _rule_copy(canvas: Any, lang: str) -> dict:
    solutions = [e.text for e in canvas.boxes.get("solution", []) if e.basis != "UNKNOWN"]
    return {
        "headline": (_first(canvas, "unique_value_proposition", skip_composed=True)
                     or _first(canvas, "solution") or _first(canvas, "unique_value_proposition"))[:120],
        "subheadline": _first(canvas, "customer_segments")[:200],
        "problem": _first(canvas, "problem")[:300],
        "benefits": [s[:160] for s in solutions[1:4]],
        "cta": TEXT[lang]["cta"],
    }


def _default_chat() -> tuple[Chat | None, str | None]:
    from venture_os.llm.client import chat_json, live_enabled, model_for
    if not live_enabled():
        return None, None
    return (lambda messages: chat_json(messages, profile="validate")), model_for("validate")


def _ask_model(chat: Chat, canvas: Any, lang: str) -> dict | None:
    boxes = {k: [e.text for e in v if e.basis != "UNKNOWN"] for k, v in canvas.boxes.items()}
    messages = [
        {"role": "system", "content": load_prompt("landing_page", language="Arabic" if lang == "ar" else "English")},
        {"role": "user", "content": "<untrusted>\n" + json.dumps(boxes, ensure_ascii=False)[:15000] + "\n</untrusted>"},
    ]
    for _ in range(2):
        try:
            data = json.loads(chat(messages))
        except Exception:  # noqa: BLE001 - bad JSON, timeout: retry once, then rules
            data = None
        if isinstance(data, dict) and isinstance(data.get("headline"), str):
            return data
    return None


def _merge_copy(copy: dict, raw: dict) -> list[str]:
    dropped = []
    for key, limit in (("headline", 120), ("subheadline", 200), ("cta", 40)):
        text = str(raw.get(key) or "").strip()[:limit]
        if not text:
            continue
        if why := banned(text):
            dropped.append(f"{key}: {why}")
        else:
            copy[key] = text
    benefits = [str(b).strip()[:160] for b in (raw.get("benefits") or []) if str(b).strip()][:3]
    kept = []
    for b in benefits:
        if why := banned(b):
            dropped.append(f"benefit: {why}")
        else:
            kept.append(b)
    if kept:
        copy["benefits"] = kept
    return dropped


# ---------- output ----------

def _plan_markdown(brief_id: str, test: Any) -> str:
    return (f"Brief id: {brief_id}\n\n# Phase 2, step 2: demand test plan\n\n"
            f"Declared at {test.declared_at}, before the landing page was drafted and before any result.\n\n"
            "| Metric | Target | Window |\n|---|---|---|\n"
            f"| {test.metric} | {test.target} | {test.days} days |\n\n"
            f"**Rule (fixed now):** {gates.DEMAND_RULE_TEXT}.\n\n"
            "The sign-up count will be entered by the founder after the window ends (founder-reported, not "
            "verified). The system never generates or estimates it. The landing page is MOCKED: it is not "
            "published until the founder approves it, and even then publishing is simulated.\n")


CSS = ("body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Tahoma,sans-serif;background:#f7f8f6;"
       "color:#1c2321;line-height:1.5}.banner{background:#b45309;color:#fff;text-align:center;padding:10px;"
       "font-weight:700}main{max-width:720px;margin:0 auto;padding:32px 16px}h1{font-size:2rem;margin:0 0 8px}"
       ".sub{font-size:1.1rem;color:#44514c}section{margin:28px 0}ul{padding-inline-start:20px}"
       "form{display:flex;gap:8px;flex-wrap:wrap}input{flex:1;min-width:200px;padding:10px;font-size:1rem;"
       "border:1px solid #9aa5a0;border-radius:6px}button{padding:10px 18px;font-size:1rem;background:#0f766e;"
       "color:#fff;border:0;border-radius:6px}.mock{background:#fef3c7;padding:10px;border-radius:6px;margin-top:12px}"
       ".note{font-size:.9rem;color:#5b6762}")


def render_html(copy: dict, lang: str, test: Any, brief_id: str) -> str:
    t, e = TEXT[lang], html.escape
    benefits = "".join(f"<li>{e(b)}</li>" for b in copy.get("benefits", []))
    problem = (f"<section><h2>{e(t['problem'])}</h2><p>{e(copy['problem'])}</p></section>"
               if copy.get("problem") else "")
    offer = f"<section><h2>{e(t['offer'])}</h2><ul>{benefits}</ul></section>" if benefits else ""
    return f"""<!doctype html>
<html lang="{lang}" dir="{'rtl' if lang == 'ar' else 'ltr'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(copy.get('headline') or 'Waitlist')}</title>
<!-- Brief id: {e(brief_id)}. Demand test declared {e(test.declared_at)}: target {test.target} {e(test.metric)}
     in {test.days} days (fixed before any result). MOCKED draft: not published. -->
<style>{CSS}</style>
</head>
<body data-demand-target="{test.target}" data-demand-days="{test.days}">
<div class="banner" role="status">{e(t['banner'])}</div>
<main>
<h1>{e(copy.get('headline') or '')}</h1>
<p class="sub">{e(copy.get('subheadline') or '')}</p>
{problem}
{offer}
<section>
<form id="waitlist" onsubmit="event.preventDefault();document.getElementById('mock').hidden=false;">
<label for="email" hidden>{e(t['email'])}</label>
<input id="email" type="email" required placeholder="{e(t['email'])}" autocomplete="email">
<button type="submit">{e(copy.get('cta') or t['cta'])}</button>
</form>
<p id="mock" class="mock" hidden>{MOCK_MESSAGE}</p>
<p class="note">{e(t['note'])}</p>
</section>
</main>
</body>
</html>
"""
