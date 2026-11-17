"""Product type: excluded categories (EN + AR) can't enter Discover; borderline digital ideas are ambiguous."""

import pytest

from venture_os.agents.brief_analyzer import analyze, classify


def fields(**values):
    return {k: {"value": v, "status": "answered"} for k, v in values.items()}


@pytest.mark.parametrize("idea,expected", [
    ("Selling handmade rugs at weekend markets", "physical_goods"),
    ("بيع المنتجات اليدوية والسجاد في المعارض", "physical_goods"),
    ("A crypto trading signals app", "financial_investment_crypto"),
    ("منصة تداول الأسهم للمبتدئين", "financial_investment_crypto"),
    ("An app that gives medical advice and a diagnosis from your symptoms", "health_advice"),
    ("تطبيق استشارة طبية وتشخيص الأعراض", "health_advice"),
    ("Online legal advice from a lawyer for tenants", "legal_advice"),
    ("موقع استشارات قانونية مع محامي", "legal_advice"),
])
def test_excluded(idea, expected):
    pt = classify(fields(idea=idea))
    assert pt.group == "excluded" and pt.label == expected and pt.trigger


def test_booking_software_for_clinics_is_ambiguous_not_excluded():
    pt = classify(fields(idea="Booking software for small clinics"))
    assert pt.group == "ambiguous" and pt.clarifying_question
    ar = classify(fields(idea="برنامج حجز مواعيد للعيادات"))
    assert ar.group == "ambiguous"


@pytest.mark.parametrize("idea,label", [
    ("Arabic CV templates in Notion for freelancers", "template_or_asset"),
    ("قوالب سيرة ذاتية بالعربي للفريلانسرز", "template_or_asset"),
    ("An online course teaching Excel to accountants", "online_course"),
    ("A Chrome extension that tracks Etsy prices", "browser_extension"),
    ("A mobile app for booking home cleaners", "mobile_app"),
    ("تطبيق لحجز عمال النظافة", "mobile_app"),
])
def test_digital_subtypes(idea, label):
    pt = classify(fields(idea=idea))
    assert pt.group == "digital_product" and pt.label == label and pt.decided_by == "rules"


def test_no_digital_product_named_is_ambiguous():
    pt = classify(fields(idea="Help small shops do better"))
    assert pt.group == "ambiguous" and "digital product" in pt.clarifying_question


def test_brief_maps_the_six_required_fields_and_lists_unknowns():
    brief = {"brief_id": "b", "version": 2, "fields": {
        **fields(idea="Notion templates for freelancers", founder_skills="design", budget="100 USD",
                 target_customer="freelancers", country="Egypt"),
        "time_available": {"value": None, "status": "unknown"}, "values": {"value": "x", "status": "unknown"}}}
    db = analyze(brief)
    assert db.required["skills"] == "design" and db.required["target_market"] == "freelancers, Egypt"
    assert set(db.unknown) == {"time_available", "values"}  # unknown stays unknown, never filled in
    assert db.required["time_available"] is None
