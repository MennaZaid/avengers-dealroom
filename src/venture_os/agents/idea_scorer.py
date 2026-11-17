"""Idea scorer (Discover step 3): the starting idea vs the alternatives, on a weighted 1-5 matrix.

The model (prompts/idea_scorer.md) may PROPOSE each criterion score with the evidence ids behind it; plain code
checks the ids exist, caps any score without evidence at `unevidenced_cap` and marks it ASSUMPTION, and computes
every total from the weights in config/gates/discover.yaml. Without a model, plain rules propose the scores from
the evidence counts, the founder's stated budget/time/skills, and a fixed effort table per product type.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import yaml

from venture_os.agents.brief_analyzer import DiscoverBrief
from venture_os.agents.schemas import Claim, Competitor, CriterionScore, Idea, IdeaScore
from venture_os.prompts import load_prompt

CONFIG = Path(__file__).resolve().parents[3] / "config" / "gates" / "discover.yaml"
# Hours to a first sellable version, and cash needed (USD) - a planning ASSUMPTION, shown as such.
EFFORT = {"template_or_asset": (30, 50), "ebook_or_guide": (40, 30), "online_course": (60, 50),
          "community_or_membership": (30, 30), "browser_extension": (80, 50), "web_app": (150, 150),
          "saas": (200, 200), "api_or_dev_tool": (150, 150), "mobile_app": (300, 300), "other_digital": (100, 100)}
SKILL_WORDS = {"template_or_asset": ("design", "excel", "notion", "writing", "تصميم"),
               "ebook_or_guide": ("writing", "write", "research", "كتابة"),
               "online_course": ("teach", "train", "expert", "تدريس", "تعليم"),
               "community_or_membership": ("community", "social media", "marketing", "سوشيال", "تسويق"),
               "browser_extension": ("javascript", "coding", "programm", "developer", "python", "برمجة", "مبرمج"),
               "web_app": ("coding", "programm", "developer", "python", "javascript", "برمجة", "مبرمج"),
               "saas": ("coding", "programm", "developer", "python", "javascript", "برمجة", "مبرمج"),
               "api_or_dev_tool": ("coding", "programm", "developer", "python", "برمجة"),
               "mobile_app": ("mobile", "android", "ios", "flutter", "kotlin", "swift", "برمجة")}
_EG_RATE_NOTE = "budget compared in the founder's own currency only when it is USD; otherwise ASSUMPTION"


def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def hours_available(time_text: str | None) -> float | None:
    """'10 hours a week for 6 months' -> 260. None if the founder's words don't give both numbers."""
    if not time_text:
        return None
    t = time_text.lower()
    t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    words = {"اربع": 4, "أربع": 4, "ثلاث": 3, "تلات": 3, "ست": 6, "خمس": 5, "شهرين": 2, "two": 2, "three": 3,
             "four": 4, "six": 6}
    for w, n in words.items():
        t = t.replace(w, str(n))
    h = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h\b|ساع)", t)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:months?|شهر|شهور)", t)
    w = re.search(r"(\d+(?:\.\d+)?)\s*(?:weeks?|أسابيع|اسابيع)", t)
    if not h:
        return None
    weeks = float(m.group(1)) * 4.33 if m else (float(w.group(1)) if w else None)
    return round(float(h.group(1)) * weeks) if weeks else None


def _clip(x: float) -> float:
    return max(1.0, min(5.0, x))


def rule_scores(idea: Idea, db: DiscoverBrief, claims: list[Claim], competitors: list[Competitor],
                reach: Claim | None) -> list[CriterionScore]:
    pain = [c for c in claims if c.id in idea.pain_claim_ids and c.type == "fact" and "stale" not in c.flags]
    domains = {re.sub(r"^https?://(www\.)?([^/]+).*", r"\2", c.url or "") for c in pain}
    priced = [c for c in competitors if c.price_claim_id]
    free_strong = [c for c in competitors if (c.pricing_model == "free")]
    hours, cash = EFFORT.get(idea.product_type, EFFORT["other_digital"])
    avail = hours_available(db.required.get("time_available"))
    budget = db.budget_parsed or {}
    skills = (db.required.get("skills") or "").lower()
    skill_hits = [w for w in SKILL_WORDS.get(idea.product_type, ()) if w in skills]
    values = (db.required.get("values") or "")
    out = [
        CriterionScore(criterion="pain_evidence", score=_clip(1 + len(pain) * 0.5 + len(domains) * 0.5),
                       evidence_ids=[c.id for c in pain][:8], note=f"{len(pain)} quotes from {len(domains)} sites"),
        CriterionScore(criterion="people_pay", score=_clip(1 + 1.5 * len(priced)),
                       evidence_ids=[c.price_claim_id for c in priced if c.price_claim_id][:6],
                       note=f"{len(priced)} competitors with a sourced price"),
        CriterionScore(criterion="competition",
                       score=_clip(5 - 0.5 * len(free_strong) - 0.25 * max(0, len(competitors) - len(free_strong))),
                       evidence_ids=[c.price_claim_id for c in competitors if c.price_claim_id][:6],
                       note=f"{len(competitors)} competitors found, {len(free_strong)} free"),
        CriterionScore(criterion="skill_fit", score=4.0 if skill_hits else 2.0,
                       evidence_ids=["brief:skills"] if db.required.get("skills") else [],
                       note=("skills match: " + ", ".join(skill_hits)) if skill_hits else "no matching skill stated"),
    ]
    if avail is None:
        out.append(CriterionScore(criterion="time_fit", score=3.0, evidence_ids=[], basis="ASSUMPTION",
                                  note="time available not given as hours and months"))
    else:
        out.append(CriterionScore(criterion="time_fit", score=_clip(5 * avail / (hours * 1.5)),
                                  evidence_ids=["brief:time_available"],
                                  note=f"~{hours} h needed (ASSUMPTION) vs ~{avail:.0f} h available"))
    if budget.get("currency") == "USD" and budget.get("max") is not None:
        out.append(CriterionScore(criterion="budget_fit", score=_clip(5 * float(budget["max"]) / (cash * 2)),
                                  evidence_ids=["brief:budget"], note=f"~${cash} cash needed (ASSUMPTION) vs ${budget['max']}"))
    else:
        out.append(CriterionScore(criterion="budget_fit", score=4.0 if cash <= 100 else 3.0, evidence_ids=[],
                                  basis="ASSUMPTION", note=f"~${cash} cash needed; {_EG_RATE_NOTE}"))
    out.append(CriterionScore(criterion="values_fit", score=3.0, evidence_ids=[], basis="ASSUMPTION",
                              note=("values stated: " + values[:80]) if values else "values unknown"))
    out.append(CriterionScore(criterion="digital_deliverability", score=5.0 if idea.product_type != "other_digital"
                              else 3.0, evidence_ids=["brief:product_type"], note=f"product type {idea.product_type}"))
    out.append(CriterionScore(criterion="reachable_market", score=4.0 if reach else 3.0,
                              evidence_ids=[reach.id] if reach else [],
                              basis="evidenced" if reach else "ASSUMPTION",
                              note=reach.quote if reach else "no internet-use figure for the country"))
    return out


def model_scores(idea: Idea, db: DiscoverBrief, claims: list[Claim], chat: Callable) -> list[CriterionScore] | None:
    cfg = load_config()
    payload = {"idea": idea.model_dump(), "brief": db.required,
               "criteria": list(cfg["scoring"]["weights"]),
               "evidence": {c.id: (c.quote or c.text)[:300] for c in claims[:40]}}
    try:
        data = json.loads(chat([{"role": "system", "content": load_prompt("idea_scorer")},
                                {"role": "user", "content": "<untrusted>" + json.dumps(payload, ensure_ascii=False)
                                 + "</untrusted>"}]))
        rows = data.get("scores") or []
        return [CriterionScore(criterion=str(r["criterion"]), score=float(r["score"]),
                               evidence_ids=[str(i) for i in r.get("evidence_ids") or []], note=str(r.get("note", ""))[:200])
                for r in rows if r.get("criterion") in cfg["scoring"]["weights"]]
    except Exception:  # noqa: BLE001 - fall back to rules
        return None


def finalize(idea_id: str, proposed: list[CriterionScore], claim_ids: set[str], cfg: dict,
             proposed_by: str) -> IdeaScore:
    """Plain code: drop unknown evidence ids, cap unevidenced scores, compute the weighted total."""
    lo, hi = cfg["scoring"]["scale"]
    cap = cfg["scoring"]["unevidenced_cap"]
    weights = cfg["scoring"]["weights"]
    by_name = {c.criterion: c for c in proposed}
    final = []
    for name in weights:
        c = by_name.get(name) or CriterionScore(criterion=name, score=cap, basis="ASSUMPTION", note="not scored")
        ids = [i for i in c.evidence_ids if i in claim_ids or i.startswith("brief:")]  # brief = founder's facts
        score = max(lo, min(hi, c.score))
        basis = c.basis
        if not ids:
            basis = "ASSUMPTION"
        if not ids and name in ("pain_evidence", "people_pay", "competition", "reachable_market"):
            basis = "ASSUMPTION"  # market criteria need market evidence
        if basis == "ASSUMPTION":
            score = min(score, cap)
        final.append(CriterionScore(criterion=name, score=round(score, 2), evidence_ids=ids, basis=basis, note=c.note))
    total = round(sum(weights[c.criterion] * c.score for c in final) / sum(weights.values()), 2)
    return IdeaScore(idea_id=idea_id, criteria=final, total=total, proposed_by=proposed_by)


def score_ideas(ideas: list[Idea], db: DiscoverBrief, claims: list[Claim], competitors: list[Competitor],
                reach: Claim | None, chat: Callable | None, model_id: str | None) -> list[IdeaScore]:
    cfg = load_config()
    ids = {c.id for c in claims}
    out = []
    for idea in ideas:
        rules = rule_scores(idea, db, claims, competitors, reach)
        proposed, by = rules, "rules"
        if chat is not None:
            got = model_scores(idea, db, claims, chat)
            if got:  # the model may only change market-evidence criteria; fit criteria stay rule-based
                merged = {c.criterion: c for c in rules}
                for c in got:
                    if c.criterion in ("pain_evidence", "people_pay", "competition", "values_fit"):
                        merged[c.criterion] = c
                proposed, by = list(merged.values()), f"{model_id} (proposed) + rules"
        out.append(finalize(idea.id, proposed, ids, cfg, by))
    return sorted(out, key=lambda s: -s.total)
