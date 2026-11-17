"""Interview designer (Discover step 5): a Mom Test interview plan, a script linter, and tagging of the
founder's interview notes. Plain code; the rules are written out in prompts/interview_designer.md.

- plan(): who to talk to, where to find them (from where the pain quotes were found), the questions (EN/AR),
  questions to avoid, and a notes form. Interview results come ONLY from the founder (typed
  primary_founder_reported); the system never writes interview answers.
- lint_question(): rejects hypothetical/future questions, pitches and leading questions, and compliment fishing;
  every question must ask about past behaviour, the last time, what they tried, or what it cost. A rejected
  question gets a past-behaviour rewrite.
- tag_note(): tags each line the founder wrote as past_behaviour | current_workaround |
  money_or_time_already_spent | commitment | compliment | hypothetical | generic_opinion. Only the first four
  count toward the Discover gate; the rest is shown as noise. Tags come only from the founder's own words.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import BaseModel

from venture_os.agents.brief_analyzer import DiscoverBrief
from venture_os.agents.research_planner import lang_of
from venture_os.agents.schemas import Claim

# ---------- script linter ----------

HYPOTHETICAL = [r"\bwould you\b", r"\bwill you\b", r"\bhow much would you\b", r"\bwould it\b", r"\bdo you think\b",
                r"\bif (?:there|you) (?:was|were|had)\b", r"\bcould you see yourself\b", r"\bare you going to\b",
                r"هل ممكن", r"(?:^|\s)لو(?:\s|$)", r"هتدفع", r"هتستخدم", r"هتشتري", r"هل ستدفع", r"هل ستستخدم",
                r"هل ستشتري", r"تفتكر", r"هل تعتقد", r"كم ستدفع"]
PITCH = [r"\b(?:our|my|this) (?:app|product|tool|platform|service|course|template|solution|idea|extension|software)\b",
         r"\bwouldn'?t it be (?:great|nice)\b", r"\bdon'?t you (?:agree|think)\b", r"\bisn'?t it\b",
         r"تطبيقنا", r"منتجنا", r"أداتنا", r"منصتنا", r"فكرتي", r"فكرتنا", r"مش شايف إن", r"أليس كذلك"]
COMPLIMENT = [r"\bdo you like\b", r"\bis (?:this|it) a good idea\b", r"\bwhat do you think (?:of|about)\b",
              r"\bwould you recommend\b", r"\bdo you love\b", r"هل تحب", r"عجبتك", r"تعجبك", r"عاجب", r"الفكرة (?:حلوة|كويسة|جيدة)",
              r"رأيك في"]
PAST = [r"\blast time\b", r"\btell me about\b", r"\bwhat did you\b", r"\bhave you (?:ever )?(?:tried|used|paid|had)\b",
        r"\bhow do you (?:currently|handle|deal)\b", r"\bwhat have you (?:already )?tried\b", r"\bhow much did\b",
        r"\bcost you\b", r"\bwhen did\b", r"\bhow often\b", r"\bwho else\b", r"\bwhat happened\b", r"\bwalk me through\b",
        r"آخر مرة", r"احك", r"ماذا فعلت", r"عملت (?:ايه|إيه)", r"جربت", r"جرّبت", r"كلف", r"كلّف", r"دفعت",
        r"كيف تتعامل", r"(?:ازاي|إزاي) بتتعامل", r"متى", r"امتى", r"من غيرك", r"ماذا حدث", r"حصل (?:ايه|إيه)"]
REWRITE = {
    "en": {"hypothetical": "When did this last happen, and what did you do about it?",
           "pitch": "Tell me about the last time this problem came up for you.",
           "compliment": "What have you already tried for this, and why didn't it work?",
           "no_past_behaviour": "Walk me through the last time this happened. What did you do?"},
    "ar": {"hypothetical": "امتى آخر مرة حصل ده، وعملت إيه وقتها؟",
           "pitch": "احكِ لي عن آخر مرة واجهتك فيها المشكلة دي.",
           "compliment": "إيه اللي جربته قبل كده عشان تحل المشكلة دي، وليه منفعش؟",
           "no_past_behaviour": "احكِ لي عن آخر مرة حصل فيها ده. عملت إيه؟"},
}


class LintResult(BaseModel):
    question: str
    ok: bool
    problems: list[str]              # hypothetical | pitch | compliment | no_past_behaviour
    rewrite: str | None = None


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def lint_question(q: str, problem: str | None = None, idea_terms: list[str] | None = None) -> LintResult:
    t = " ".join(q.split())
    lang = lang_of(t)
    problems = []
    if _any(HYPOTHETICAL, t):
        problems.append("hypothetical")
    if _any(PITCH, t) or any(w and re.search(rf"\b{re.escape(w)}\b", t, re.IGNORECASE)
                             for w in (idea_terms or [])):
        problems.append("pitch")
    if _any(COMPLIMENT, t):
        problems.append("compliment")
    if not _any(PAST, t):
        problems.append("no_past_behaviour")
    if not problems:
        return LintResult(question=t, ok=True, problems=[])
    first = next(p for p in ("hypothetical", "pitch", "compliment", "no_past_behaviour") if p in problems)
    return LintResult(question=t, ok=False, problems=problems, rewrite=REWRITE[lang][first])


def lint_script(questions: list[str], problem: str | None, idea_terms: list[str]) -> tuple[list[str], list[LintResult]]:
    """Keep good questions; replace rejected ones by their rewrite (once, de-duplicated)."""
    final, results = [], []
    for q in questions:
        r = lint_question(q, problem, idea_terms)
        results.append(r)
        out = q if r.ok else r.rewrite
        if out and out not in final:
            final.append(out)
    return final, results


# ---------- note tagging ----------

EVIDENCE_TAGS = ("past_behaviour", "current_workaround", "money_or_time_already_spent", "commitment")
NOISE_TAGS = ("compliment", "hypothetical", "generic_opinion")
TAG_RULES: dict[str, list[str]] = {
    "past_behaviour": [r"\blast (?:time|week|month|year)\b", r"\byesterday\b", r"\bago\b", r"\bonce\b",
                       r"\b(?:i|we) (?:had|tried|used|lost|missed|called|asked|went|switched|stopped|spent|paid)\b",
                       r"آخر مرة", r"امبارح", r"أمس", r"الأسبوع اللي فات", r"الشهر اللي فات", r"من (?:شهر|أسبوع|سنة)",
                       r"جربت", r"جرّبت", r"استخدمت", r"اضطريت", r"ضاع", r"فاتني", r"حصل"],
    "current_workaround": [r"\bcurrently\b", r"\bright now\b", r"\b(?:i|we) (?:use|keep|track|do it)\b",
                           r"\bspreadsheet\b", r"\bexcel\b", r"\bwhatsapp\b", r"\bmanually\b", r"\bby hand\b",
                           r"\bnotebook\b", r"\bpaper\b", r"حالياً", r"حاليا", r"دلوقتي", r"بنستخدم", r"بستخدم",
                           r"إكسل", r"اكسل", r"واتساب", r"يدوي", r"بإيدي", r"ورق", r"كشكول"],
    "money_or_time_already_spent": [r"\b(?:paid|spent|spend|cost(?:s)? (?:me|us))\b",
                                    r"\d[\d,.]*\s*(?:egp|usd|kes|\$|pounds?|dollars?|hours?|hrs|days?)\b",
                                    r"\$\s?\d", r"دفعت", r"صرفت", r"كلفني", r"كلّفني", r"\d+\s*(?:جنيه|دولار|ساعة|ساعات|يوم)"],
    "commitment": [r"\bintro\b", r"\bintroduc\w*", r"\breferr?al\b", r"\brefer(?:red)?\b", r"\bpre-?order\b",
                   r"\bdeposit\b", r"\bfollow-?up (?:call|meeting)\b", r"\bmeet again\b", r"\bsigned up\b",
                   r"\bpilot\b", r"هعرفك", r"عرّفني", r"عرفني على", r"حجز", r"عربون", r"دفعة مقدمة", r"ميعاد تاني",
                   r"هيجرب النسخة", r"سجل"],
    "compliment": [r"\bgreat idea\b", r"\blove (?:it|this)\b", r"\bsounds (?:great|good|cool)\b", r"\bawesome\b",
                   r"\bi like (?:it|this|the idea)\b", r"\bcool idea\b", r"فكرة (?:حلوة|جميلة|هايلة|تحفة)", r"عجبتني",
                   r"تحفة", r"ممتاز"],
    "hypothetical": [r"\bwould\b", r"\bi'?d\b", r"\bmight\b", r"\bprobably\b", r"\bmaybe\b", r"\bif there (?:was|were)\b",
                     r"\bwill (?:use|buy|pay|try)\b", r"(?:^|\s)لو(?:\s|$)", r"ممكن", r"هشتري", r"هستخدم", r"هدفع",
                     r"أكيد هجرب"],
    "generic_opinion": [r"\beveryone\b", r"\bpeople (?:always|usually|generally)\b", r"\bnobody\b", r"\bi think\b",
                        r"\bin general\b", r"كل الناس", r"الناس (?:عموماً|عموما|دايماً)", r"أعتقد", r"في رأيي", r"عادةً"],
}


class TaggedNote(BaseModel):
    text: str                        # exactly what the founder wrote
    tags: list[str]
    counts: bool                     # carries an evidence tag (past behaviour, workaround, spend, commitment)


def tag_note(text: str) -> TaggedNote:
    t = text.strip()
    tags = [tag for tag, pats in TAG_RULES.items() if _any(pats, t)]
    # A sentence that is only a future/conditional statement is not past behaviour even with a past verb nearby.
    if "hypothetical" in tags and "past_behaviour" in tags and not re.search(
            r"\blast (?:time|week|month)|yesterday|ago|آخر مرة|امبارح|أمس", t, re.IGNORECASE):
        tags.remove("past_behaviour")
    if not tags:
        tags = ["generic_opinion"]
    return TaggedNote(text=text, tags=tags, counts=any(x in EVIDENCE_TAGS for x in tags))


def tag_interview(notes: str) -> list[TaggedNote]:
    return [tag_note(line) for line in re.split(r"\n+|(?<=[.!?؟])\s+", notes) if line.strip()]


# ---------- the plan ----------

QUESTIONS = {
    "en": ["Tell me about the last time you ran into this: \"{problem}\". What happened?",
           "What did you do about it? What have you tried so far?",
           "What did that cost you, in money or hours?",
           "How do you handle it today? Which tools, apps or people do you use?",
           "Why haven't the things you tried solved it?",
           "When did you last pay for something to deal with this? What was it?",
           "Who else is involved when you deal with this?",
           "Who else should I talk to about this?"],
    "ar": ["احكِ لي عن آخر مرة واجهت فيها ده: \"{problem}\". إيه اللي حصل؟",
           "عملت إيه وقتها؟ إيه اللي جربته لحد دلوقتي؟",
           "ده كلّفك كام، فلوس أو ساعات؟",
           "إزاي بتتعامل مع الموضوع ده دلوقتي؟ بتستخدم أنهي أدوات أو تطبيقات أو ناس؟",
           "ليه الحاجات اللي جربتها محلّتش المشكلة؟",
           "امتى آخر مرة دفعت في حاجة عشان تتعامل مع ده؟ كانت إيه؟",
           "مين كمان بيشارك لما بتتعامل مع ده؟",
           "مين كمان المفروض أتكلم معاه عن الموضوع ده؟"],
}
AVOID = {"en": ["Would you use an app that ...?", "How much would you pay for ...?", "Do you like this idea?",
                "Pitching your product before they describe the problem"],
         "ar": ["هل ممكن تستخدم تطبيق ...؟", "هتدفع كام في ...؟", "الفكرة عاجباك؟", "تعرض المنتج قبل ما يحكي المشكلة"]}
NOTES_FORM = ["Person (anonymous label, role, where you found them)", "Date",
              "What happened the last time (their words)", "What they tried / use today", "What it cost them",
              "Commitment given (intro, follow-up, pre-order) or none", "Your own notes (kept separate)"]
METHOD_SOURCES = [{"corpus_id": "M-010", "title": "The Mom Test (team summary)", "url": "https://www.momtestbook.com"},
                  {"corpus_id": "M-049", "title": "GOV.UK Service Manual: user research",
                   "url": "https://www.gov.uk/service-manual/user-research"}]


class InterviewPlan(BaseModel):
    who: str
    where_to_find: list[str]
    how_many: str
    guides: dict[str, dict]           # lang -> {questions, avoid}
    lint: list[LintResult]
    notes_form: list[str]
    assumptions: list[str]
    method_sources: list[dict]
    results_rule: str = ("Interview results come only from the founder (typed primary_founder_reported). "
                         "The system never writes interview answers.")


def plan(db: DiscoverBrief, pain: list[Claim], idea_title: str | None = None,
         extra_questions: list[str] | None = None) -> InterviewPlan:
    problem = db.optional.get("problem")
    target = db.optional.get("target_customer") or db.required.get("target_market")
    langs = [x for x in ((db.tags.get("languages") or {}).get("value") or []) if x in QUESTIONS] or ["en"]
    idea_terms = [w for w in re.findall(r"[\w؀-ۿ]{5,}", idea_title or "") if
                  w.lower() not in (problem or "").lower()][:4]
    guides, lint = {}, []
    for lang in langs:
        fill = (problem if problem and lang_of(problem) == lang else
                ("the problem we're asking about" if lang == "en" else "المشكلة اللي بنسأل عنها")).rstrip(". ")
        qs = [q.format(problem=fill) for q in QUESTIONS[lang]] + [q for q in extra_questions or []
                                                                  if lang_of(q) == lang]
        final, results = lint_script(qs, fill, idea_terms)
        guides[lang] = {"questions": final, "avoid": AVOID[lang]}
        lint += results
    domains = sorted({(urlsplit(c.url).hostname or "").removeprefix("www.") for c in pain if c.url})[:6]
    where = [f"People posting about this problem on {d} (where the pain quotes came from)" for d in domains]
    where += ["Groups and communities where the target customers already meet (online and local)",
              "Introductions from each person you interview (ask at the end)"]
    assumptions = []
    if not problem:
        assumptions.append("ASSUMPTION: the problem is unknown in the brief; the questions use a generic wording")
    if not target:
        assumptions.append("ASSUMPTION: the target customer is unknown; decide who to interview first")
    return InterviewPlan(who=target or "unknown - see assumptions", where_to_find=where,
                         how_many="5-10 people from the target group, one at a time, 15-30 minutes each",
                         guides=guides, lint=lint, notes_form=NOTES_FORM, assumptions=assumptions,
                         method_sources=METHOD_SOURCES)
