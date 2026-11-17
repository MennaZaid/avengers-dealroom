"""Research critic (Discover step 6). Findings are appended to outputs/phase1_gate_decision.md.

Rules (always): stale, undated, off-country and non-registry sources (flags from evidence/validate.py);
contradicting numbers for the same thing; ideas resting on no quote; overclaiming words in generated text.
Model review (when on): the `judge` profile, which must be a DIFFERENT model family from the generator
(`reasoning`); if the families match, the model review is skipped and says why.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date

from pydantic import BaseModel

from venture_os.agents.schemas import Claim, Idea
from venture_os.decision_log import log_action
from venture_os.guardrails import check_output
from venture_os.prompts import load_prompt

OVERCLAIM = re.compile(r"\b(everyone|all (?:people|users|businesses)|guarantee\w*|definitely|huge demand|no "
                       r"competition|always)\b|الكل|مضمون|أكيد|بدون منافسة", re.IGNORECASE)


class Finding(BaseModel):
    kind: str            # stale | undated | off_geo | web_only | contradiction | unsourced_idea | overclaim | broad_target | model
    detail: str
    claim_ids: list[str] = []


class CriticReport(BaseModel):
    findings: list[Finding]
    model_review: str     # what the judge model said, or why it did not run (STUBBED)
    judge_model: str | None = None
    dropped: list[str] = []   # model findings dropped as factually wrong (e.g. a past date called "future")


FUTURE = re.compile(r"\b(in the future|future[- ]dated|has not happened yet|not yet happened|upcoming)\b|"
                    r"في المستقبل|لم يحدث بعد", re.IGNORECASE)
DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(19|20)\d{2}\b")


def calls_past_date_future(detail: str, today: date) -> bool:
    """True when a model finding calls a date that is not after `today` "in the future" (a judge error)."""
    if not FUTURE.search(detail):
        return False
    for m in DATE.finditer(detail):
        if m.group(1):
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
        else:
            d = date(int(m.group(0)), 1, 1)
        if d <= today:
            return True
    return False


def _numbers(text: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"\d{1,3}(?:,\d{3})+|\d{3,}", text)]


def rule_findings(claims: list[Claim], ideas: list[Idea], brief_text: str = "") -> list[Finding]:
    out: list[Finding] = []
    for kind in ("stale", "undated", "other_country"):
        ids = [c.id for c in claims if kind in c.flags]
        if ids:
            out.append(Finding(kind="off_geo" if kind == "other_country" else kind, claim_ids=ids[:12],
                               detail=f"{len(ids)} claims are {kind.replace('_', ' ')}"))
    web = [c.id for c in claims if c.type == "fact" and "web_source" in c.flags and c.source_kind == "web"]
    if claims and len(web) == len([c for c in claims if c.type == "fact"]):
        out.append(Finding(kind="web_only", claim_ids=web[:12],
                           detail="every fact comes from the open web, none from a registry source"))
    sized = [(c, n) for c in claims if c.topic == "market_size" and c.quote for n in _numbers(c.quote)]
    for i, (a, x) in enumerate(sized):
        for b, y in sized[i + 1:]:
            if a.url != b.url and min(x, y) > 0 and max(x, y) / min(x, y) > 2 and \
                    set(re.findall(r"[a-z]{5,}", (a.quote or "").lower())) & set(re.findall(r"[a-z]{5,}", (b.quote or "").lower())):
                out.append(Finding(kind="contradiction", claim_ids=[a.id, b.id],
                                   detail=f"{x:,.0f} vs {y:,.0f} for what looks like the same thing"))
                break
    broad: set[str] = set()
    for idea in ideas:
        if not idea.pain_claim_ids:
            out.append(Finding(kind="unsourced_idea", detail=f"{idea.id} '{idea.title[:60]}' cites no pain quote"))
        text = f"{idea.title} {idea.description} {idea.why_founder}"
        words = {m.group(0).lower() for m in OVERCLAIM.finditer(text)}
        from_brief = {w for w in words if w in brief_text.lower()}  # the founder's own words, e.g. "Everyone"
        if check_output(text) or words - from_brief:
            out.append(Finding(kind="overclaim", detail=f"{idea.id}: overclaiming wording in the idea text "
                                                        f"({', '.join(sorted(words - from_brief)) or 'must-never rule'})"))
        elif from_brief:
            broad.update(from_brief)
    if broad:
        out.append(Finding(kind="broad_target", detail=(f"the brief's target is '{', '.join(sorted(broad))}': name one "
                                                        "specific group of people to interview and sell to first")))
    return out[:30]


def review(claims: list[Claim], ideas: list[Idea], judge: Callable | None, judge_id: str | None,
           judge_family: str | None, generator_family: str | None, brief_text: str = "",
           today: date | None = None) -> CriticReport:
    findings = rule_findings(claims, ideas, brief_text)
    if judge is None:
        return CriticReport(findings=findings, model_review="STUBBED: no judge model configured (LLM_MODE is "
                                                            "not live); rule checks only")
    if generator_family and judge_family == generator_family:
        return CriticReport(findings=findings, judge_model=judge_id,
                            model_review=f"skipped: judge family '{judge_family}' is the same as the generator's")
    today = today or date.today()
    payload = {"today": today.isoformat(), "claims": {c.id: f"{c.quote or c.text} ({c.url}, {c.published_at or 'undated'})" for c in claims[:40]},
               "ideas": [i.model_dump(include={"id", "title", "pain", "pain_claim_ids"}) for i in ideas]}
    try:
        data = json.loads(judge([{"role": "system", "content": load_prompt("research_critic")},
                                 {"role": "user", "content": f"<untrusted>{json.dumps(payload, ensure_ascii=False)}"
                                                             "</untrusted>"}]))
        known, dropped = {c.id for c in claims}, []
        for f in (data.get("findings") or [])[:10]:
            if isinstance(f, dict) and f.get("detail"):
                detail = str(f["detail"])[:300]
                if calls_past_date_future(detail, today):   # factually wrong: dropped, and logged, never hidden
                    dropped.append(detail)
                    log_action("research_critic", "drop_model_finding", sources=[], model=judge_id, cost=0,
                               approved_by=None, reason=f"calls a date on or before {today.isoformat()} 'in the "
                                                        "future'", finding=detail)
                    continue
                findings.append(Finding(kind="model", detail=detail,
                                        claim_ids=[i for i in f.get("claim_ids") or [] if i in known]))
        summary = str(data.get("summary") or "")[:600]
    except Exception as e:  # noqa: BLE001
        summary, dropped = f"judge model call failed: {type(e).__name__}", []
    return CriticReport(findings=findings, model_review=summary or "no issues raised", judge_model=judge_id,
                        dropped=dropped)
