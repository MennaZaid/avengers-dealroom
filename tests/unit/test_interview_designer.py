"""Mom Test checks: the script linter and the tagging of the founder's interview notes (EN + AR)."""

import json
from pathlib import Path

import pytest

from venture_os.agents.brief_analyzer import analyze
from venture_os.agents.interview_designer import EVIDENCE_TAGS, lint_question, plan, tag_interview, tag_note

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"


# ---------- 1. script linter ----------

@pytest.mark.parametrize("q,problem", [
    ("Would you use an app that tracks your invoices?", "hypothetical"),
    ("Will you switch to a new tool next year?", "hypothetical"),
    ("How much would you pay for this?", "hypothetical"),
    ("Do you think freelancers need this?", "hypothetical"),
    ("هل ممكن تستخدم تطبيق للفواتير؟", "hypothetical"),
    ("لو فيه تطبيق بيعمل كده، هتدفع كام؟", "hypothetical"),
    ("Our app sends reminders automatically - wouldn't it be great?", "pitch"),
    ("تطبيقنا بيبعت تذكير أوتوماتيك، مش شايف إن ده مفيد؟", "pitch"),
    ("Do you like the idea?", "compliment"),
    ("Is this a good idea?", "compliment"),
    ("الفكرة عاجباك؟", "compliment"),
    ("هل تحب الفكرة دي؟", "compliment"),
])
def test_linter_rejects_and_rewrites(q, problem):
    r = lint_question(q)
    assert not r.ok and problem in r.problems
    assert r.rewrite and lint_question(r.rewrite).ok  # the rewrite itself passes the linter


def test_linter_flags_the_idea_name_as_a_pitch():
    r = lint_question("Tell me about the last time you used InvoiceBuddy.", idea_terms=["InvoiceBuddy"])
    assert "pitch" in r.problems


@pytest.mark.parametrize("q", [
    "Tell me about the last time you sent a late invoice.",
    "What have you tried so far to get paid on time?",
    "How much did the last missed payment cost you?",
    "How do you currently keep track of who owes you money?",
    "احكِ لي عن آخر مرة اتأخر فيها عميل في الدفع.",
    "إيه اللي جربته لحد دلوقتي عشان تتابع الفواتير؟",
    "الموضوع ده كلّفك كام آخر مرة؟",
])
def test_linter_accepts_past_behaviour_questions(q):
    assert lint_question(q).ok


def test_question_must_be_about_past_behaviour():
    r = lint_question("What features matter to you?")
    assert not r.ok and r.problems == ["no_past_behaviour"]


def test_generated_plan_passes_its_own_linter():
    brief = json.loads((FIX / "pharmastock_v1.json").read_text(encoding="utf-8"))
    p = plan(analyze(brief), [], "PharmaStock stock-tracking app")
    for g in p.guides.values():
        assert g["questions"] and all(lint_question(q).ok for q in g["questions"])


# ---------- 2. notes tagging ----------

@pytest.mark.parametrize("note,tag", [
    ("Last month I lost a client because my invoice was late.", "past_behaviour"),
    ("الشهر اللي فات ضاع مني عميل عشان الفاتورة اتأخرت", "past_behaviour"),
    ("We currently track everything in an Excel sheet.", "current_workaround"),
    ("بستخدم إكسل حالياً وبتابع على واتساب", "current_workaround"),
    ("I paid 500 EGP to a designer for a template.", "money_or_time_already_spent"),
    ("دفعت 300 جنيه على قالب", "money_or_time_already_spent"),
    ("She introduced me to two other freelancers.", "commitment"),
    ("He asked to pre-order the first version.", "commitment"),
    ("هعرفك على اتنين صحابي بيشتغلوا فريلانس", "commitment"),
    ("Great idea, I love it!", "compliment"),
    ("فكرة حلوة جداً", "compliment"),
    ("I would definitely use it.", "hypothetical"),
    ("لو فيه تطبيق كده هستخدمه", "hypothetical"),
    ("Everyone needs this.", "generic_opinion"),
    ("كل الناس محتاجة ده", "generic_opinion"),
])
def test_note_tags(note, tag):
    assert tag in tag_note(note).tags


def test_only_evidence_tags_count_and_noise_is_kept_separate():
    tagged = tag_interview("Great idea, I love it! I would definitely use it. "
                           "Last week I spent two hours chasing a payment.")
    counts = [t for t in tagged if t.counts]
    noise = [t for t in tagged if not t.counts]
    assert len(counts) == 1 and set(counts[0].tags) & set(EVIDENCE_TAGS)
    assert {tg for t in noise for tg in t.tags} <= {"compliment", "hypothetical", "generic_opinion"}


def test_tagging_never_changes_the_founders_words():
    notes = "  Last month I lost a client.\nWe use WhatsApp.  "
    tagged = tag_interview(notes)
    assert [t.text.strip() for t in tagged] == ["Last month I lost a client.", "We use WhatsApp."]
    assert all(t.text in notes for t in tagged)  # verbatim pieces of what the founder wrote
    assert " ".join(t.text for t in tagged).split() == notes.split()  # no word added, removed or changed
