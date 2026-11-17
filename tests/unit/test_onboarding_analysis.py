"""Onboarding: tags, follow-up questions, unlabelled corrections, inferred values, editing after confirmation."""

import json

import pytest

from venture_os.onboarding import chat
from venture_os.onboarding.analyst import LLMAnalyst
from venture_os.onboarding.brief import REQUIRED, OnboardingState
from venture_os.onboarding.extract import LLMExtractor, NullExtractor
from venture_os.onboarding.tags import _has, rule_tags

NULL = NullExtractor()


class FakeExtractor:
    def __init__(self, table):
        self.table = table

    def extract(self, text, kind):
        return {k: v for trig, found in self.table.items() if trig in text for k, v in found.items()}


def answer_required(s):
    while s.asking in REQUIRED:
        chat.handle_message(s, f"answer for {s.asking}", NULL)


def to_summary(s, extractor=NULL):
    reply = ""
    while s.phase == "collecting":
        reply = chat.handle_message(s, "skip", extractor)
    return reply


def confirmed_state():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: an app to book trusted home cleaners for office workers", NULL)
    chat.handle_message(s, "problem: no time to cook\ntarget customer: employees in Cairo\ncountry: Egypt\n"
                           "budget: 50,000 EGP\ntime available: 20 h/week\nfounder skills: sales", NULL)
    to_summary(s)
    chat.handle_message(s, "yes", NULL)
    assert s.phase == "confirmed" and s.version == 1
    return s


# ---------- tags ----------

def test_rule_tags_from_an_arabic_brief():
    t = rule_tags({"idea": "تطبيق لتوصيل الأكل البيتي", "target_customer": "موظفين في القاهرة", "country": "مصر",
                   "business_model": "عمولة على كل طلب"}, "ar")
    assert t["industries"][:2] == ["food_beverage", "delivery_logistics"]
    assert t["customer_type"] == "b2c" and t["revenue_model"] == "commission"
    assert t["country_code"] == "EG" and t["languages"] == ["ar", "en"]


def test_keywords_match_whole_words_only():
    assert _has("العيادات الطبية", "طبي") and not _has("تطبيق", "طبي")
    assert _has("i cook meals", "cook") and not _has("i care", "car")


def test_summary_shows_tags_and_founder_can_correct_them():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: online tutoring for high-school students\ncountry: Egypt", NULL)
    answer_required(s)
    reply = to_summary(s)
    assert "education" in reply and s.tags["country_code"].value == "EG"
    bad = chat.handle_message(s, "industry: spaceships", NULL)
    assert "not a valid" in bad and s.tags["industries"].value != ["spaceships"]
    chat.handle_message(s, "industry: education, software_saas", NULL)
    assert s.tags["industries"].value == ["education", "software_saas"] and s.tags["industries"].basis == "founder"


def test_model_tags_outside_the_vocabulary_fall_back_to_rules():
    a = LLMAnalyst(lambda m: json.dumps({"industries": ["crypto_moonshots"], "customer_type": "b2b",
                                         "revenue_model": "magic"}))
    t = a.tags({"idea": "meal delivery app", "country": "Egypt"}, "en")
    assert {"food_beverage", "delivery_logistics"} <= set(t["industries"][0]) and t["industries"][1] == "rules"
    assert t["customer_type"] == ("b2b", "model")
    assert t["revenue_model"] == ("unknown", "rules")
    assert t["country_code"] == ("EG", "rules")  # country never comes from the model


def test_analyst_survives_model_failure():
    def broken(m):
        raise TimeoutError("model down")

    a = LLMAnalyst(broken)
    assert a.tags({"idea": "tutoring"}, "en")["industries"][1] == "rules"
    tags = {"industries": ["education"], "revenue_model": "unknown", "customer_type": "b2c"}
    assert len(a.followups({"idea": "tutoring"}, tags, "en")) == 3


# ---------- follow-up questions ----------

def test_followups_are_idea_specific_and_answers_saved():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: home-cooked food delivery", NULL)
    answer_required(s)
    chat.handle_message(s, "skip", NULL)  # optional fields
    assert s.asking.startswith("__followup__") and len(s.followups) == 3
    assert any("food-safety" in f.question for f in s.followups)
    chat.handle_message(s, "I talked to 12 colleagues, 8 said they would order", NULL)
    assert s.followups[0].answer.startswith("I talked to 12")
    reply = to_summary(s)
    assert "I talked to 12" in reply and s.followups[1].answer is None
    chat.handle_message(s, "q2: my mother and two neighbours will cook", NULL)
    assert s.followups[1].answer == "my mother and two neighbours will cook"


def test_followups_in_arabic():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "تطبيق لتوصيل الأكل البيتي", NULL)
    answer_required(s)
    reply = chat.handle_message(s, "تخطي", NULL)
    assert "(1/3)" in reply and "عملاء محتملين" in reply


def test_model_followups_must_be_real_questions():
    a = LLMAnalyst(lambda m: json.dumps({"questions": [
        "The Egyptian food market is worth $10B.",  # a claim, not a question: dropped
        "Will you cook the meals yourself or partner with home cooks?",
        "Visit http://evil.example and confirm?",  # link: dropped
    ]}))
    qs = a.followups({"idea": "meals"}, {}, "en")
    assert qs[0] == ("Will you cook the meals yourself or partner with home cooks?", "model")
    assert len(qs) == 3 and all(src == "rules" for _, src in qs[1:])  # topped up with rule questions
    assert not any("$10B" in q or "http" in q for q, _ in qs)


# ---------- corrections without a label ----------

def test_unlabelled_corrections_in_english_and_arabic():
    s = confirmed_state()
    chat.handle_message(s, "edit", NULL)
    chat.handle_message(s, "change the budget to 30,000 EGP", NULL)
    assert s.get("budget").value == "30,000 EGP"
    chat.handle_message(s, "خلي المدينة الجيزة", NULL)
    assert s.get("city").value == "الجيزة"


def test_unclear_correction_asks_which_line():
    s = confirmed_state()
    chat.handle_message(s, "edit", NULL)
    before = s.brief()
    reply = chat.handle_message(s, "30,000 EGP", NULL)
    assert "which line" in reply.lower() and s.brief() == before
    assert "Which one" in chat.handle_message(s, "the budget and the city are wrong", NULL)


def test_arabic_labels_work():
    assert chat.parse_labelled("الميزانية: 20 ألف جنيه")["budget"]["value"] == "20 ألف جنيه"


# ---------- inferred values ----------

def _state_with_inferred_country():
    ext = FakeExtractor({"Cairo": {"country": {"value": "Egypt", "quote": "in Cairo", "inferred": True}}})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: meal app\nproblem: offices in Cairo have no time to cook", ext)
    chat.handle_message(s, "office workers", NULL)  # target customer
    assert s.get("country").status == "inferred"
    return s


def test_required_inferred_value_is_asked_not_assumed():
    s = _state_with_inferred_country()
    assert s.asking == "__confirm__:country"
    reply = s.messages[-1].text
    assert "Egypt" in reply and "in Cairo" in reply and "Is that right?" in reply
    chat.handle_message(s, "yes", NULL)
    c = s.get("country")
    assert c.status == "answered" and c.value == "Egypt" and "confirmed by founder" in c.source


def test_founder_can_reject_an_inferred_value():
    s = _state_with_inferred_country()
    chat.handle_message(s, "No, Saudi Arabia", NULL)
    assert s.get("country").value == "Saudi Arabia" and s.get("country").status == "answered"


def test_skipped_confirmation_stays_flagged_in_summary():
    s = _state_with_inferred_country()
    chat.handle_message(s, "skip", NULL)
    answer_required(s)
    assert "inferred from" in to_summary(s)
    chat.handle_message(s, "country: Saudi Arabia", NULL)
    assert s.get("country").status == "answered"


def test_extractor_flags_country_deduced_from_city_even_if_model_does_not():
    out = LLMExtractor(lambda m: json.dumps({"country": {"value": "Egypt", "quote": "in Cairo"}})).extract(
        "We start in Cairo.", "doc")
    assert out["country"]["inferred"] is True


def test_inferred_value_never_overrides_the_founder():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "country: Jordan", NULL)
    ext = FakeExtractor({"Cairo": {"country": {"value": "Egypt", "quote": "Cairo", "inferred": True}}})
    chat.handle_message(s, "Our pilot kitchen is in Cairo", ext)
    assert s.get("country").value == "Jordan"


# ---------- editing after confirmation ----------

def test_edit_after_confirmation_saves_next_version():
    s = confirmed_state()
    reply = chat.handle_message(s, "budget: 80,000 EGP", NULL)  # a correction alone starts an edit
    assert s.phase == "confirming" and "version 1" in reply
    reply = chat.handle_message(s, "yes", NULL)
    assert s.version == 2 and s.phase == "confirmed" and "budget" in reply and "stale" in reply
    assert s.saved["fields"]["budget"]["value"] == "80,000 EGP" and s.last_changes == ["budget"]


def test_cancel_edit_restores_saved_version():
    s = confirmed_state()
    chat.handle_message(s, "edit", NULL)
    chat.handle_message(s, "budget: 1 EGP", NULL)
    chat.handle_message(s, "cancel", NULL)
    assert s.phase == "confirmed" and s.version == 1 and s.get("budget").value == "50,000 EGP"


def test_yes_without_changes_keeps_the_version():
    s = confirmed_state()
    chat.handle_message(s, "edit", NULL)
    assert "version 1" in chat.handle_message(s, "yes", NULL) and s.version == 1


def test_document_after_confirmation_starts_an_edit():
    s = confirmed_state()
    chat.handle_document(s, "plan.txt", "City: Alexandria", NULL)
    assert s.phase == "confirming" and s.get("city").value == "Alexandria"
    chat.handle_message(s, "yes", NULL)
    assert s.version == 2


def test_model_cannot_guess_revenue_model_the_founder_never_gave():
    a = LLMAnalyst(lambda m: json.dumps({"industries": ["food_beverage"], "revenue_model": "commission"}))
    assert a.tags({"idea": "meal app"}, "en")["revenue_model"] == ("unknown", "rules")
    assert a.tags({"idea": "meal app", "business_model": "we take a cut"}, "en")["revenue_model"] == (
        "commission", "model")


def test_yes_confirms_inferred_values_and_keeps_their_origin():
    ext = FakeExtractor({"Cairo": {"country": {"value": "Egypt", "quote": "in Cairo", "inferred": True}}})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "A meal app for offices in Cairo", ext)
    answer_required(s)
    to_summary(s)
    chat.handle_message(s, "yes", NULL)
    c = s.get("country")
    assert c.status == "answered" and "inferred, confirmed by founder" in c.source and c.quote == "in Cairo"
    assert s.saved["fields"]["country"]["status"] == "answered"


# ---------- review of the "Nadafa" live run ----------

def test_focused_answer_keeps_the_founders_words():
    """The model shortened skills and dropped 'a part-time programmer friend'. The asked field keeps the text."""
    answer = "أنا شاطرة في التصميم والتسويق، ومعايا صاحبتي مبرمجة بدوام جزئي"
    ext = FakeExtractor({"شاطرة": {
        "founder_skills": {"value": "تصميم وتسويق", "quote": "شاطرة في التصميم والتسويق"},
        "technical_preferences": {"value": "no coding", "quote": "مبرمجة بدوام جزئي"},
    }})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "تطبيق لحجز عمال النضافة", NULL)
    while s.asking != "founder_skills":
        chat.handle_message(s, f"إجابة {s.asking}", NULL)
    chat.handle_message(s, answer, ext)
    assert s.get("founder_skills").value == answer
    # "nobody codes" is not a technical preference: optional fields are not filled from a focused answer;
    # the optional question that follows offers technical preferences instead.
    assert s.get("technical_preferences").status == "unknown"
    assert s.asking == "supply_side"  # a cleaner-booking app is two-sided: who are the cleaners?
    chat.handle_message(s, "عمال نظافة فريلانسرز", NULL)
    assert s.get("supply_side").value == "عمال نظافة فريلانسرز"
    assert "التفضيلات التقنية" in s.messages[-1].text  # then the optional question offers technical preferences


def test_paragraph_answer_still_uses_the_model_per_field():
    text = "عايزة أعمل أبلكيشن لحجز عمال النضافة. المشكلة إن الأسر الشغالة مش لاقية حد موثوق."
    ext = FakeExtractor({"أبلكيشن": {
        "idea": {"value": "تطبيق لحجز عمال النظافة", "quote": "أعمل أبلكيشن لحجز عمال النضافة"},
        "problem": {"value": "صعوبة إيجاد عمال موثوقين", "quote": "مش لاقية حد موثوق"},
    }})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, text, ext)
    assert s.get("idea").value == "تطبيق لحجز عمال النظافة" and s.get("problem").status == "answered"


def test_answer_about_another_field_does_not_fill_the_asked_one():
    ext = FakeExtractor({"Giza": {"city": {"value": "Giza", "quote": "Giza"}}})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: cleaning app", NULL)
    chat.handle_message(s, "actually the city is Giza", ext)  # asked: problem
    assert s.get("problem").value is None and s.get("city").value == "Giza"


def test_research_questions_go_to_discover_not_the_founder():
    a = LLMAnalyst(lambda m: json.dumps({
        "questions": ["ما هو متوسط تكلفة خدمة التنظيف في المناطق المستهدفة؟",
                      "هل العمال هيكونوا موظفين ولا فريلانسرز؟",
                      "هل هناك لوائح حكومية لتشغيل هذا النوع من الأعمال؟"],
        "research_questions": ["What is the market size for home cleaning in Cairo?"]}))
    founder, research = a.questions({"idea": "cleaning"}, {}, "ar")
    assert founder[0] == ("هل العمال هيكونوا موظفين ولا فريلانسرز؟", "model")
    assert not any("متوسط" in q or "لوائح" in q for q, _ in founder)
    assert "What is the market size for home cleaning in Cairo?" in research
    assert any("متوسط" in q for q in research) and any("لوائح" in q for q in research)


def test_open_questions_shown_in_summary_and_saved():
    class Fake:
        def tags(self, fields, lang):
            return {"industries": (["home_services"], "rules")}

        def questions(self, fields, tags, lang):
            return [("Will cleaners be freelancers?", "model")], ["What do cleaners charge per visit in Cairo?"]

    s = OnboardingState()
    chat.start(s, Fake())
    chat.handle_message(s, "idea: cleaning app", NULL, Fake())
    while s.phase == "collecting":
        chat.handle_message(s, "skip" if not s.asking or s.asking.startswith("__") else "x", NULL, Fake())
    reply = chat.summary(s, Fake())
    assert "research stage" in reply and "per visit" in reply
    chat.handle_message(s, "yes", NULL, Fake())
    assert s.saved["open_questions"] == ["What do cleaners charge per visit in Cairo?"]


def test_arabic_summary_uses_arabic_labels():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "تطبيق لحجز عمال النضافة", NULL)
    answer_required(s)
    reply = to_summary(s)
    assert "- الميزانية*:" in reply and "- budget" not in reply and "القطاعات" in reply
    chat.handle_message(s, "المدينة: الجيزة", NULL)  # Arabic label works as a correction
    assert s.get("city").value == "الجيزة"


def test_extractor_is_told_the_founders_language():
    seen = []

    class Spy:
        def extract(self, text, kind):
            seen.append(kind)
            return {}

    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "تطبيق لحجز عمال النضافة", Spy())
    assert "Arabic" in seen[0]


# ---------- review of the "PharmaStock" live run ----------

class Boom:
    """An extractor that must not be called (it would misread '200' as a budget)."""

    def extract(self, text, kind):
        return {"budget": {"value": "$200", "quote": "200"}}


def _pharma_summary():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: pharmacy stock tracker\ncountry: Kenya", NULL)
    answer_required(s)
    to_summary(s)
    return s


def test_two_labels_typed_on_one_line_set_both_fields():
    s = _pharma_summary()
    reply = chat.handle_message(s, "business model: monthly subscription, 15 USD per pharmacy budget: 3,000 USD", NULL)
    assert s.get("business_model").value == "monthly subscription, 15 USD per pharmacy"
    assert s.get("budget").value == "3,000 USD"
    assert "business model" in reply and "budget" in reply.split("\n")[0]


def test_followup_answers_with_dots_and_commas_on_one_line():
    s = _pharma_summary()
    before = s.get("budget").value
    chat.handle_message(s, "q1. nothing right now , q2. 200 , q3.compare the two options", Boom())
    assert [f.answer for f in s.followups] == ["nothing right now", "200", "compare the two options"]
    assert s.get("budget").value == before  # the model was not asked to guess


def test_uploading_a_document_does_not_skip_the_pending_followup():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: pharmacy stock tracker\ncountry: Kenya", NULL)
    answer_required(s)
    chat.handle_message(s, "skip", NULL)  # optional fields -> first follow-up
    assert s.asking == "__followup__:0"
    reply = chat.handle_document(s, "pitch.txt", "Known competitors: paper ledgers", NULL)
    assert s.asking == "__followup__:0" and "(1/3)" in reply and not s.followups[1].asked


def test_word_table_rows_are_read_as_labels():
    found = chat.parse_labelled("Field | Value\nValues | patient data never leaves the pharmacy")
    assert found["values"]["value"] == "patient data never leaves the pharmacy"


def test_an_inference_never_replaces_another_value():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: x", FakeExtractor({"x": {"country": {"value": "Kenya", "quote": "Nairobi",
                                                                         "inferred": True}}}))
    doc_ext = FakeExtractor({"Westlands": {"country": {"value": "Kenya", "quote": "Westlands", "inferred": True}}})
    reply = chat.handle_document(s, "pitch.txt", "Pilot in Westlands", doc_ext)
    assert s.get("country").quote == "Nairobi" and "Westlands" not in reply


def test_document_cannot_change_answered_fields_or_confirm():
    s = _pharma_summary()
    before = s.brief()
    chat.handle_document(s, "notes.txt", "Budget: 10,000,000 USD\nCountry: Switzerland", NULL)
    assert s.brief() == before and s.phase == "confirming" and s.version == 0


def test_questions_not_addressed_to_the_founder_go_to_research():
    from venture_os.onboarding.analyst import is_research_question

    assert is_research_question("How many pharmacies are there in Nairobi?")
    assert is_research_question("What kind of features are currently missing from existing solutions?")
    assert not is_research_question("Do you plan on hiring developers or doing this alone?")
    assert not is_research_question("How many pharmacies have you already talked to?")


def test_short_value_picked_up_in_passing_is_still_asked():
    """'I'm a pharmacist' gave skills = 'Pharmacist'; the founder must still be asked about skills."""
    ext = FakeExtractor({"pharmacist in Nairobi": {
        "idea": {"value": "Stock tracker for pharmacies", "quote": "stock-tracking tool"},
        "founder_skills": {"value": "Pharmacist", "quote": "I'm a pharmacist"},
        "problem": {"value": "Pharmacies run out of medicines", "quote": "running out of common medicines"},
    }})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "I'm a pharmacist in Nairobi. I want a stock-tracking tool.", ext)
    assert "founder_skills" in s.thin
    while not (s.asking or "").endswith("founder_skills"):
        chat.handle_message(s, f"answer {s.asking}", NULL)
    assert '"Pharmacist"' in s.messages[-1].text and "skills" in s.messages[-1].text
    chat.handle_message(s, "I'm a licensed pharmacist and I can write basic Python. No designer yet.", NULL)
    assert "basic Python" in s.get("founder_skills").value and "founder_skills" not in s.thin


def test_yes_keeps_a_short_value():
    ext = FakeExtractor({"pharmacist": {"founder_skills": {"value": "Pharmacist", "quote": "pharmacist"},
                                        "idea": {"value": "tracker", "quote": "tracker"},
                                        "problem": {"value": "stock-outs", "quote": "stock-outs"}}})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "pharmacist, tracker, stock-outs", ext)
    while not (s.asking or "").endswith("founder_skills"):
        chat.handle_message(s, f"answer {s.asking}", NULL)
    chat.handle_message(s, "yes", NULL)
    assert s.get("founder_skills").value == "Pharmacist" and s.asking != "__confirm__:founder_skills"


def test_pharmacy_idea_is_tagged_health_and_software():
    t = rule_tags({"idea": "A stock tracking tool for small independent pharmacies"}, "en")
    assert {"health", "software_saas"} <= set(t["industries"])


def test_followup_answer_does_not_overwrite_an_answered_field():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: pharmacy stock tracker\ncountry: Kenya\n"
                           "target customer: small independent pharmacies in Nairobi", NULL)
    answer_required(s)
    chat.handle_message(s, "skip", NULL)  # optional -> first follow-up
    ext = FakeExtractor({"Pharmacists": {"target_customer": {"value": "pharmacists", "quote": "Pharmacists"}}})
    chat.handle_message(s, "Pharmacists themselves, usually the owner.", ext)
    assert s.get("target_customer").value == "small independent pharmacies in Nairobi"
    assert s.followups[0].answer == "Pharmacists themselves, usually the owner."


# ---------- persona 3 (Sanaa) ----------

def test_egyptian_yes_confirms_the_summary():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "فكرة: تطبيق لحجز دروس خصوصية", NULL)
    answer_required(s)
    to_summary(s)
    chat.handle_message(s, "ايوه", NULL)
    assert s.phase == "confirmed" and s.version == 1


def test_demo_pdf_is_readable_and_labelled():
    from pathlib import Path

    from venture_os.onboarding.documents import extract_text

    pdf = Path(__file__).parents[1] / "fixtures" / "personas" / "sanaa-plan.pdf"
    found = chat.parse_labelled(extract_text(pdf.name, pdf.read_bytes()))
    assert set(found) == {"business_model", "known_competitors", "technical_preferences", "values"}
    assert found["business_model"]["value"].startswith("12% commission")


def test_quote_with_copied_wrapper_tag_is_still_grounded():
    """Fanar copied '<untrusted>' into every quote, so the grounding check dropped all fields."""
    out = LLMExtractor(lambda m: json.dumps({
        "idea": {"value": "سوق للمنتجات اليدوية", "quote": "<untrusted>marketplace أونلاين"},
        "budget": {"value": "1M", "quote": "<untrusted>مليون دولار"},  # still not in the text: dropped
    })).extract("عايزة أعمل marketplace أونلاين للمنتجات", "msg")
    assert out["idea"]["quote"] == "marketplace أونلاين" and "budget" not in out


def test_arabic_to_is_stripped_from_unlabelled_correction():
    s = confirmed_state()
    chat.handle_message(s, "غير الميزانية لـ 25 ألف جنيه", NULL)
    assert s.get("budget").value == "25 ألف جنيه"


def test_short_answer_keeps_founders_words_even_if_it_mentions_another_field():
    ext = FakeExtractor({"القاهرة": {
        "target_customer": {"value": "أشخاص يحبون المنتجات اليدوية", "quote": "بيحبوا المنتجات اليدوية"},
        "country": {"value": "مصر", "quote": "برة مصر"},
    }})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: سوق للمنتجات اليدوية\nproblem: الوسطاء", NULL)
    answer = "ناس في القاهرة وبرة مصر بيحبوا المنتجات اليدوية الأصلية"
    chat.handle_message(s, answer, ext)
    assert s.get("target_customer").value == answer
    assert s.get("country").status == "inferred" and s.asking == "__confirm__:country"


def test_country_is_never_reasked_as_too_short():
    ext = FakeExtractor({"Cairo": {"idea": {"value": "x app", "quote": "x app"},
                                   "problem": {"value": "slow service in Cairo", "quote": "slow service"},
                                   "country": {"value": "Egypt", "quote": "Egypt"}}})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "An x app for Egypt because of slow service in Cairo, which is a big problem for many.",
                        ext)
    assert "country" not in s.thin


# ---------- persona 4 (Darsak) ----------

def test_skip_word_typos_count_as_skip():
    assert all(chat.is_skip(w) for w in ("تخطس", "تخطي", "skp", "Skip.", "pass"))
    assert not chat.is_skip("ship products from Aswan") and not chat.is_skip("تخطيط شهري")


def test_typo_skip_leaves_followup_unanswered():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: tutoring", NULL)
    answer_required(s)
    chat.handle_message(s, "skip", NULL)  # optional -> first follow-up
    chat.handle_message(s, "تخطس", NULL)
    assert s.followups[0].answer is None and s.asking == "__followup__:1"


def test_copied_quote_marker_is_removed():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "> A tutoring platform for high-school maths", NULL)
    assert s.get("idea").value == "A tutoring platform for high-school maths"


# ---------- budget as numbers, two-sided ideas ----------

@pytest.mark.parametrize("text,country,expected", [
    ("حوالي خمسين الف جنيه", "EG", (50000, 50000, "EGP", "stated")),
    ("معايا حوالي ٥٠ ألف جنيه", "EG", (50000, 50000, "EGP", "stated")),
    ("20-30k USD", None, (20000, 30000, "USD", "stated")),
    ("between 20 and 30 thousand dollars", None, (20000, 30000, "USD", "stated")),
    ("40 ألف درهم", "AE", (40000, 40000, "AED", "stated")),
    ("about 1.5 million KES", "KE", (1500000, 1500000, "KES", "stated")),
    ("50000", "EG", (50000, 50000, "EGP", "country_default")),
    ("$5k", None, (5000, 5000, "USD", "stated")),
])
def test_budget_is_parsed_to_numbers(text, country, expected):
    from venture_os.onboarding.money import parse_budget

    b = parse_budget(text, country)
    assert (b["min"], b["max"], b["currency"], b["currency_source"]) == expected


def test_budget_without_an_amount_stays_unparsed():
    from venture_os.onboarding.money import parse_budget

    assert parse_budget("not sure yet", "EG") is None and parse_budget(None) is None


def test_summary_and_saved_brief_carry_the_parsed_budget():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: an online tutoring platform\ncountry: Egypt\nbudget: حوالي خمسين الف جنيه", NULL)
    answer_required(s)
    reply = to_summary(s)
    assert "(= 50,000 EGP)" in reply
    chat.handle_message(s, "yes", NULL)
    assert s.saved["budget"] == {"min": 50000, "max": 50000, "currency": "EGP", "currency_source": "stated"}


@pytest.mark.parametrize("idea,expected", [
    ("an app to book trusted home cleaners", True),
    ("a marketplace connecting women artisans with buyers", True),
    ("تطبيق لحجز عمال النضافة للبيوت", True),
    ("منصة تربط المدرسين بأولياء الأمور", True),
    ("an online course teaching artisans to sell on Instagram", False),
    ("a stock-tracking tool for pharmacies", False),
])
def test_two_sided_ideas_are_detected(idea, expected):
    s = OnboardingState()
    s.fields["idea"] = chat.FieldValue(value=idea, status="answered")
    assert chat.two_sided(s) is expected


def test_two_sided_idea_asks_who_supplies_once():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: an app to book trusted home cleaners", NULL)
    answer_required(s)
    assert s.asking == "supply_side" and "two groups" in s.messages[-1].text
    chat.handle_message(s, "skip", NULL)
    assert s.asking != "supply_side"
    assert "supply side" in to_summary(s)  # still listed (unknown) so the founder can add it later


def test_one_sided_idea_never_asks_or_shows_supply_side():
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: an online course for Instagram marketing", NULL)
    answer_required(s)
    assert s.asking != "supply_side"
    assert "supply side" not in to_summary(s)


def test_model_cannot_add_a_supply_side_to_a_one_sided_idea():
    ext = FakeExtractor({"Pharmacists": {"supply_side": {"value": "pharmacists", "quote": "Pharmacists"}}})
    s = OnboardingState()
    chat.start(s)
    chat.handle_message(s, "idea: a stock-tracking tool for small pharmacies", NULL)
    answer_required(s)
    chat.handle_message(s, "skip", NULL)  # optional -> follow-ups
    chat.handle_message(s, "Pharmacists themselves, usually the owner.", ext)
    assert s.get("supply_side").value is None
