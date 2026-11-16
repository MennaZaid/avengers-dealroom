"""Brief tags: a small fixed vocabulary that later stages use to pick questions, search queries and
sources, so nothing is hard-coded to one business idea.

Tags are computed by plain rules (keywords in English and Arabic). A model may refine them, but its answer
is accepted only if it is one of the allowed values. The founder sees the tags in the summary and can
correct them ("industry: education").
"""

from __future__ import annotations

import re

INDUSTRIES: dict[str, tuple[str, ...]] = {
    "food_beverage": ("food", "meal", "restaurant", "cook", "kitchen", "catering", "bakery", "cafe", "coffee",
                      "snack", "dessert", "أكل", "اكل", "طعام", "وجبات", "وجبة", "مطعم", "مطاعم", "طبخ", "يطبخ", "مطبخ",
                      "حلويات", "قهوة", "مخبز"),
    "delivery_logistics": ("delivery", "deliver", "logistics", "shipping", "courier", "last mile", "warehouse",
                           "توصيل", "شحن", "لوجست", "مخزن", "مستودع"),
    "retail_ecommerce": ("e-commerce", "ecommerce", "online store", "shop", "shopping", "retail", "store", "متجر", "تجارة إلكترونية",
                         "بيع", "محل"),
    "fintech": ("payment", "fintech", "wallet", "loan", "lending", "bank", "insurance", "invest", "دفع", "محفظة",
                "قرض", "تمويل", "بنك", "تأمين", "استثمار"),
    "education": ("education", "tutor", "course", "school", "student", "learning", "teach", "university",
                  "تعليم", "دروس", "كورس", "مدرسة", "طلاب", "طالب", "تعلم", "جامعة"),
    "health": ("health", "clinic", "doctor", "medical", "pharmac*", "medicine", "medication", "drug", "fitness", "patient", "therapy", "صحة",
               "عيادة", "طبيب", "دكتور", "طبي", "صيدلية", "لياقة", "مريض", "علاج"),
    "travel_tourism": ("travel", "tourism", "tourist", "hotel", "trip", "booking", "سياحة", "سفر", "فندق", "رحلة",
                       "رحلات", "حجز"),
    "real_estate_construction": ("real estate", "property", "rent", "apartment", "construction", "عقار", "عقارات",
                                 "إيجار", "ايجار", "شقة", "شقق", "بناء", "مقاولات"),
    "agriculture": ("agri*", "farm", "crop", "livestock", "زراع", "مزرعة", "محاصيل", "مواشي"),
    "manufacturing": ("manufactur*", "factory", "production line", "تصنيع", "مصنع"),
    "handmade_crafts": ("handmade", "handcraft", "craft", "artisan", "pottery", "embroidery", "يدوي", "يدوية",
                        "حرف", "فخار", "تطريز"),
    "fashion_beauty": ("fashion", "clothing", "clothes", "apparel", "beauty", "cosmetic", "salon", "أزياء", "ملابس",
                       "موضة", "تجميل", "صالون"),
    "media_entertainment": ("media", "content", "video", "music", "game", "gaming", "podcast", "إعلام", "محتوى",
                            "فيديو", "موسيقى", "ألعاب", "العاب"),
    "software_saas": ("saas", "software", "platform", "dashboard", "api", "crm", "erp", "app", "application",
                      "tool", "inventory", "stock-tracking", "tracking", "تطبيق", "أبلكيشن", "ابلكيشن", "برنامج", "برمجيات",
                      "نظام إدارة"),
    "professional_services": ("consulting", "agency", "accounting", "legal", "recruit", "hr ", "استشار", "وكالة",
                              "محاسبة", "قانون", "توظيف"),
    "energy_environment": ("solar", "energy", "recycl*", "waste", "green", "طاقة", "شمسية", "تدوير",
                           "نفايات", "بيئة"),
    "transport_mobility": ("ride", "taxi", "car", "bike", "scooter", "transport", "مواصلات", "تاكسي",
                           "سيارة", "عربية", "نقل"),
    "home_services": ("cleaning", "maintenance", "plumb", "repair", "babysit", "nanny", "تنظيف", "صيانة", "سباك",
                      "تصليح", "جليسة"),
}
CUSTOMER_TYPES = ("b2c", "b2b", "b2b2c", "b2g", "unknown")
REVENUE_MODELS = ("subscription", "commission", "one_off_sales", "saas_license", "advertising", "freemium",
                  "service_fees", "unknown")

_REVENUE_WORDS = {
    "subscription": ("subscription", "subscribe", "monthly plan", "membership", "اشتراك", "عضوية"),
    "commission": ("commission", "marketplace", "take rate", "per order", "عمولة", "نسبة"),
    "one_off_sales": ("sell", "sales", "one-off", "one off", "per item", "بيع", "مبيعات"),
    "saas_license": ("license", "licence", "per seat", "ترخيص"),
    "advertising": ("ads", "advertis*", "sponsor", "إعلان", "اعلان", "رعاية"),
    "freemium": ("freemium", "free tier", "premium", "مجاني"),
    "service_fees": ("fee", "fees", "per hour", "hourly", "رسوم", "بالساعة"),
}
_B2B_WORDS = ("business", "businesses", "companies", "company", "smes", "sme", "shops", "restaurants", "clinics",
              "schools", "b2b", "enterprise", "شركات", "شركة", "مشاريع", "محلات", "مطاعم", "عيادات", "مدارس")
_B2G_WORDS = ("government", "ministry", "municipal", "public sector", "حكومة", "حكومي", "وزارة", "محافظة")
_B2C_WORDS = ("people", "families", "students", "parents", "women", "men", "employees", "consumers", "individuals",
              "young", "mothers", "أشخاص", "أسر", "عائلات", "طلاب", "أهالي", "ستات", "سيدات", "موظفين", "شباب",
              "أمهات", "افراد", "أفراد", "ناس")

# ISO 3166 alpha-2 -> names founders may type (English, Arabic, Egyptian dialect spellings).
COUNTRIES: dict[str, tuple[str, ...]] = {
    "EG": ("egypt", "مصر", "masr"), "SA": ("saudi", "ksa", "السعودية", "السعوديه"),
    "AE": ("uae", "emirates", "dubai", "abu dhabi", "الإمارات", "الامارات", "دبي"),
    "JO": ("jordan", "الأردن", "الاردن"), "MA": ("morocco", "المغرب"), "TN": ("tunisia", "تونس"),
    "DZ": ("algeria", "الجزائر"), "LB": ("lebanon", "لبنان"), "QA": ("qatar", "قطر"), "KW": ("kuwait", "الكويت"),
    "BH": ("bahrain", "البحرين"), "OM": ("oman", "عمان", "عُمان"), "IQ": ("iraq", "العراق"),
    "SY": ("syria", "سوريا"), "PS": ("palestine", "فلسطين"), "LY": ("libya", "ليبيا"), "SD": ("sudan", "السودان"),
    "YE": ("yemen", "اليمن"), "US": ("united states", "usa", "america", "أمريكا", "امريكا"),
    "GB": ("united kingdom", "uk", "britain", "england", "بريطانيا"), "DE": ("germany", "ألمانيا", "المانيا"),
    "FR": ("france", "فرنسا"), "TR": ("turkey", "türkiye", "تركيا"), "IN": ("india", "الهند"),
    "NG": ("nigeria", "نيجيريا"), "KE": ("kenya", "كينيا"),
}
ARABIC_SPEAKING = {"EG", "SA", "AE", "JO", "MA", "TN", "DZ", "LB", "QA", "KW", "BH", "OM", "IQ", "SY", "PS", "LY",
                   "SD", "YE"}


_SUFFIX = r"(?:s|es|ing|ed|er|ers|y|ment|ments|ors|al)?"


def _has(text: str, word: str) -> bool:
    """English: whole word plus common endings ('cook' matches 'cooks', not 'cookie'); a trailing '*' marks a
    stem that matches any ending ('manufactur*'). Arabic: word start, allowing attached prefixes (و، ف، ب، ل،
    ك، ال، لل) and any ending, so 'طبي' matches 'الطبية' but not 'تطبيق'."""
    if re.search(r"[a-z]", word):
        if word.endswith("*"):
            return re.search(r"(?<![a-z])" + re.escape(word[:-1]), text) is not None
        return re.search(r"(?<![a-z])" + re.escape(word) + _SUFFIX + r"(?![a-z])", text) is not None
    w = word[2:] if word.startswith("ال") and len(word) > 3 else word
    return re.search(r"(?<![؀-ۿ])(?:[وفبلك])?(?:ال|لل)?" + re.escape(w), text) is not None


def country_code(text: str | None) -> str | None:
    if not text:
        return None
    t = text.lower()
    if re.fullmatch(r"\s*[a-z]{2}\s*", t) and t.strip().upper() in COUNTRIES:
        return t.strip().upper()
    hits = [code for code, names in COUNTRIES.items() if any(_has(t, n) for n in names)]
    return hits[0] if len(hits) == 1 else None


def mentions_country(text: str, code: str) -> bool:
    return any(_has(text.lower(), n) for n in COUNTRIES.get(code, ()))


def industries(text: str) -> list[str]:
    t = text.lower()
    scores = {k: sum(_has(t, w) for w in words) for k, words in INDUSTRIES.items()}
    ranked = [k for k, v in sorted(scores.items(), key=lambda kv: -kv[1]) if v > 0]
    return ranked[:3] or ["other"]


def customer_type(text: str) -> str:
    t = text.lower()
    b2b = any(_has(t, w) for w in _B2B_WORDS)
    b2c = any(_has(t, w) for w in _B2C_WORDS)
    if any(_has(t, w) for w in _B2G_WORDS):
        return "b2g"
    if b2b and b2c:
        return "b2b2c"
    return "b2b" if b2b else "b2c" if b2c else "unknown"


def revenue_model(text: str) -> str:
    t = text.lower()
    for model, words in _REVENUE_WORDS.items():
        if any(_has(t, w) for w in words):
            return model
    return "unknown"


ALLOWED = {
    "industries": set(INDUSTRIES) | {"other"},
    "customer_type": set(CUSTOMER_TYPES),
    "revenue_model": set(REVENUE_MODELS),
}


def rule_tags(fields: dict[str, str | None], lang: str) -> dict[str, str | list[str]]:
    """fields: field name -> value (None if unknown)."""
    about = " ".join(v for k in ("idea", "problem", "target_customer", "known_competitors") if (v := fields.get(k)))
    code = country_code(fields.get("country"))
    langs = [lang]
    if code in ARABIC_SPEAKING and "ar" not in langs:
        langs.append("ar")
    if "en" not in langs:
        langs.append("en")  # English sources are always searched as well
    return {
        "industries": industries(about) if about else ["other"],
        "customer_type": customer_type(" ".join(v for k in ("target_customer", "idea") if (v := fields.get(k)))),
        "revenue_model": revenue_model(fields.get("business_model") or ""),
        "country_code": code or "unknown",
        "languages": langs,
    }


def clean_tag(name: str, value) -> str | list[str] | None:
    """Validate a tag value from the model or the founder. Returns None if not allowed."""
    if name == "industries":
        items = value if isinstance(value, list) else re.split(r"[,،]\s*", str(value))
        items = [str(i).strip().lower().replace(" ", "_") for i in items if str(i).strip()]
        items = [i for i in items if i in ALLOWED["industries"]][:3]
        return items or None
    if name in ("customer_type", "revenue_model"):
        v = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        return v if v in ALLOWED[name] else None
    if name == "country_code":
        return country_code(str(value))
    if name == "languages":
        items = value if isinstance(value, list) else re.split(r"[,،]\s*", str(value))
        items = [str(i).strip().lower() for i in items if str(i).strip().lower() in ("en", "ar")]
        return items or None
    return None


TAG_NAMES = ("industries", "customer_type", "revenue_model", "country_code", "languages")
