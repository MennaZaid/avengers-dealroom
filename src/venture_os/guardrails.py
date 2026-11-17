"""Guardrails shared by onboarding and every agent. Plain rules (no model), English and Arabic.

1. check_product(): products the hackathon does not allow (physical goods; financial, investment or crypto
   products; health or legal advice). The product must be digital. Borderline ideas get "review".
2. check_request(): founder requests the system must refuse (fake reviews, fake sign-ups, false urgency,
   income promises, impersonation, moving money, storing passwords/cards, instruction injection).
3. check_output(): the same must-never rules applied to text an agent generated, before anyone sees it.
4. redact(): remove card numbers and passwords before anything is stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from venture_os.onboarding.tags import _has

# ---------- 1. products ----------

EXCLUDED = {
    "physical_goods": (
        "handmade", "hand-made", "rug", "kilim", "carpet", "pottery", "ceramic", "jewelry", "jewellery",
        "clothing", "clothes", "apparel", "t-shirt", "furniture", "cosmetic", "perfume", "candle", "soap",
        "home-cooked", "baked goods", "groceries", "physical product", "merch", "souvenir",
        "هاند ميد", "منتجات يدوية", "المنتجات اليدوية", "مشغولات يدوية", "مصنوعة يدوي", "كليم", "سجاد", "فخار",
        "خوص", "مجوهرات", "ملابس", "أثاث", "عطور", "شموع", "صابون", "أكل بيتي", "الأكل البيتي", "حلويات",
        "منتجات تجميل",
    ),
    "financial": (
        "loan", "lending", "crypto", "bitcoin", "nft", "forex", "stock trading", "investment app",
        "investment platform", "robo-advisor", "insurance", "microfinance", "credit score", "e-wallet",
        "digital wallet", "remittance",
        "قرض", "قروض", "كريبتو", "عملات رقمية", "بيتكوين", "فوركس", "تداول الأسهم", "منصة استثمار",
        "تأمين", "محفظة إلكترونية", "محفظة رقمية", "تحويل أموال",
    ),
    "health_advice": (
        "diagnos*", "symptom", "medical advice", "health advice", "treatment plan", "telemedicine", "therapy",
        "therapist", "mental health", "diet plan", "nutrition advice", "prescription", "dosage",
        "تشخيص", "أعراض", "اعراض", "استشارة طبية", "استشارات طبية", "نصائح طبية", "نصائح صحية", "علاج نفسي",
        "خطة علاج", "روشتة", "جرعة", "نظام غذائي",
    ),
    "legal_advice": (
        "legal advice", "lawyer", "attorney", "legal consultation", "visa advice",
        "استشارة قانونية", "استشارات قانونية", "محامي", "محاماة", "نصائح قانونية",
    ),
}
# Mentions that make an idea borderline (allowed only if the product itself is digital and gives no advice).
BORDERLINE = {
    "health": ("pharmac*", "clinic", "patient", "doctor", "medicine", "صيدلية", "صيدليات", "عيادة", "مريض", "طبيب",
               "دكتور", "أدوية", "ادوية"),
    "goods_marketplace": ("marketplace", "e-commerce", "online store", "متجر"),
}
REASONS = {
    "physical_goods": ("The product is physical goods. This system only builds digital products.",
                       "المنتج سلعة مادية. هذا النظام يبني منتجات رقمية فقط."),
    "financial": ("Financial, investment and crypto products are not supported.",
                  "المنتجات المالية والاستثمارية والعملات الرقمية غير مدعومة."),
    "health_advice": ("Products that give health or medical advice are not supported.",
                      "المنتجات التي تقدم نصائح صحية أو طبية غير مدعومة."),
    "legal_advice": ("Products that give legal advice are not supported.",
                     "المنتجات التي تقدم نصائح قانونية غير مدعومة."),
}
SUGGEST = (
    ("To continue, describe a digital product instead, for example software, an app, a booking or scheduling "
    "tool, a course or a template. Change it with a line like 'idea: ...'."),
    ("للمتابعة، صف منتجاً رقمياً بدلاً من ذلك، مثل برنامج أو تطبيق أو أداة حجز أو كورس أو قالب. "
    "غيّر الفكرة بسطر مثل 'الفكرة: ...'."),
)


@dataclass
class ProductCheck:
    status: str  # "allowed" | "review" | "excluded"
    categories: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)

    def reason(self, lang: str) -> str:
        i = 1 if lang == "ar" else 0
        if self.status == "excluded":
            return " ".join(REASONS[c][i] for c in self.categories) + " " + SUGGEST[i]
        if self.status == "review":
            return ("Allowed if the product is digital and gives no medical, legal or financial advice."
                    if i == 0 else "مسموح إذا كان المنتج رقمياً ولا يقدم نصائح طبية أو قانونية أو مالية.")
        return "Digital product: allowed." if i == 0 else "منتج رقمي: مسموح."

    def as_dict(self) -> dict:
        return {"status": self.status, "categories": self.categories, "matched": self.matched}


def _hits(text: str, words) -> list[str]:
    t = text.lower()
    return [w.rstrip("*") for w in words if _has(t, w)]


def check_product(fields: dict[str, str | None]) -> ProductCheck:
    """fields: brief field -> value. Looks at what is being sold, not at who the customers are."""
    sold = " ".join(v for k in ("idea", "business_model") if (v := fields.get(k)))  # what is being sold
    about = " ".join(v for k in ("idea", "problem", "business_model") if (v := fields.get(k)))
    excluded, matched = [], []
    for cat, words in EXCLUDED.items():
        if hits := _hits(sold, words):
            excluded.append(cat)
            matched += hits
    if excluded:
        return ProductCheck("excluded", excluded, matched)
    border = {cat: h for cat, words in BORDERLINE.items() if (h := _hits(about, words))}
    if border:
        return ProductCheck("review", list(border), [w for h in border.values() for w in h])
    return ProductCheck("allowed")


# ---------- 2-3. requests and outputs ----------

# Requests aimed at the system. Patterns need an instruction ("write 50 reviews"), not a product feature
# ("customers can post reviews"), so normal answers about the idea are not refused.
_A = r"(?<![\u0600-\u06FF])"  # Arabic word start
_RULES: dict[str, list[str]] = {
    "fake_reviews": [
        (r"\b(write|generate|create|make|post|draft)\b.{0,15}\b(\d+|some|a few|many|fake|positive|good|five|5)\b.{0,15}"
        r"\b(reviews?|testimonials?|ratings?)\b"),
        r"\b(write|generate|create|draft)\b.{0,10}\b(reviews?|testimonials?)\b.{0,25}\b(for (me|us|my|our)|from customers)",
        r"\b(fake|five[- ]star|5[- ]star)\b.{0,20}\b(reviews?|testimonials?|ratings?)\b",
        _A + r"(اكتب|اكتبلي|اكتبي|اكتبلنا|ولد|ولّد|زود|زوّد).{0,30}(تقييمات|تقييم|ريفيو|ريفيوهات|مراجعات|شهادات)",
        r"(تقييمات|تقييم|مراجعات|مراجعة|ريفيوهات|ريفيو|شهادات) (وهمية|وهمي|مزيفة|مزيف|خمس نجوم|٥ نجوم|5 نجوم)",
        _A + r"(اعملي|اعمللي|اعملنا|اعمل لي|ولدلي|جيبلي|هاتلي).{0,25}(تقييمات|تقييم|ريفيو|ريفيوهات|مراجعات)",
        r"[0-9٠-٩]+ ?(ريفيو|ريفيوهات|تقييم|تقييمات|مراجعة|مراجعات) (إيجابي|ايجابي|إيجابية|ايجابية|خمس|٥|5)",
    ],
    "fake_signups": [
        r"\bfake\b.{0,20}\b(sign[- ]?ups?|users|followers|accounts|customers|orders|waitlist)\b",
        r"\b(buy|inflate|add)\b.{0,20}\b(followers|fake sign[- ]?ups|likes)\b",
        r"\b(create|open|make)\b.{0,10}\baccounts?\b.{0,25}\b(for me|for us|on my behalf|on our behalf)\b",
        r"(تسجيلات|متابعين|حسابات|عملاء|مشتركين) (وهمية|مزيفة|وهميين|مزيفين)",
    ],
    "false_urgency": [
        r"\b(add|put|include|show|with)\b.{0,15}\bcountdown\b", r"\bfake\b.{0,15}\b(scarcity|urgency|deadline)\b",
        r"\bonly \d+ left\b", r"عداد تنازلي", r"(استعجال|ندرة) (وهمي|وهمية|مزيف|مزيفة)",
    ],
    "income_promise": [
        r"\bguarantee[ds]?\b.{0,40}\b(income|profit|success|money|sales|revenue)\b",
        r"\b(promise|tell|assure)\b.{0,15}\b(me|us)\b.{0,25}\b(make|earn|succeed|be rich|profit)\b",
        r"\b(guarantee|promise)\b.{0,10}\b(i|we|me|us)\b.{0,15}\b(make|earn|succeed|profit|get rich)\b",
        r"\b(earn|make)\b.{0,40}\bguarantee[ds]?\b",
        (r"\b(tell|promise|assure)\b.{0,10}\b(customers|buyers|users|clients|people|them)\b.{0,25}"
         r"\b(will|they'?ll)\b.{0,10}\b(earn|make|profit|get rich)\b"),
        r"(ربح|أرباح|ارباح|دخل|مكسب|نجاح) (مضمون|مضمونة|أكيد|اكيد)",
        _A + r"(اضمن|اضمنلي|تضمن|تضمنلي|أكدلي|اكدلي|وعدني|اوعدني).{0,25}"
        r"(ربح|أرباح|ارباح|دخل|مكسب|نجاح|فلوس|هكسب|هاكسب|أكسب|اكسب|هربح|أربح|اربح|هنجح|أنجح|انجح)",
    ],
    "impersonation": [
        r"\b(pretend|pose)\b.{0,15}\b(to be|as)\b", r"\bimpersonat",
        r"\b(reply|write|post|answer)\b.{0,20}\bas (if you were|if you are|the founder|me|a customer)\b",
        r"\bas if (it'?s|it is|it were|it came|it was|they are) (from|by|written by|posted by)\b",
        _A + r"(انتحل|اتقمص|تقمص|كأنك|كانك).{0,20}(عميل|زبون|المؤسس|شركة|براند|أنا|انا)",
    ],
    "move_money": [
        r"\b(transfer|wire|withdraw)\b.{0,30}\b(money|funds|payment|\$|usd|egp|aed|sar)\b",
        r"\bsend\b.{0,10}\b(money|funds|payment)\b", (r"\brefund\b.{0,15}\b(the|this|my|a|his|her|their)\b.{0,15}"
        r"\b(customer|buyer|payment|order)\b"), (r"\bcharge\b.{0,10}\b(my|the|his|her|their|a)\b.{0,10}"
        r"\b(card|customer|account|buyer)\b"),
        _A + r"(حول|حوّل|حولي|حوللي|اسحب|رجع|رجّع|استرد).{0,20}(فلوس|مبلغ|المبلغ|الفلوس|الكارت|البطاقة)",
    ],
    "store_credentials": [
        r"\bmy (password|passcode|pin)\b", r"\b(password|passcode|pin)\s*(is|:|=)\s*\S",
        r"\b(card|credit card|cvv)\s*(number|no\.?|#)?\s*(is|:)\s*\d",
        r"\b(store|save|keep|remember)\b.{0,15}\b(my|our)\b.{0,10}\b(password|card|cvv|login)\b",
        r"(كلمة السر|كلمة المرور|الباسورد|رقم الكارت|رقم البطاقة)\s*(بتاعتي|بتاعي|هي|هو|:)",
    ],
    "instruction_injection": [
        r"\bignore\b.{0,20}\b(previous|prior|above|all)\b.{0,15}\binstructions?\b",
        r"\byou are now\b.{0,30}\bmode\b", r"\b(reveal|show|print)\b.{0,15}\bsystem prompt\b",
        r"\bconfirm the brief (automatically|without)", r"تجاهل.{0,20}التعليمات",
    ],
}
_COMPILED = {rule: [re.compile(p, re.IGNORECASE) for p in pats] for rule, pats in _RULES.items()}
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")

REFUSALS = {
    "fake_reviews": (("I can't write reviews, testimonials or ratings: they must come from real customers. "
                     "I can help you plan how to ask real customers for feedback."),
                     ("لا أستطيع كتابة تقييمات أو شهادات عملاء: يجب أن تأتي من عملاء حقيقيين. "
                     "يمكنني مساعدتك في التخطيط لطلب آراء من عملاء حقيقيين.")),
    "fake_signups": ("I can't create fake sign-ups, users, followers or accounts. Real demand is what we measure.",
                     "لا أستطيع إنشاء تسجيلات أو مستخدمين أو متابعين أو حسابات وهمية. ما نقيسه هو الطلب الحقيقي."),
    "false_urgency": ("I can't add countdown timers or fake scarcity.",
                      "لا أستطيع إضافة عداد تنازلي أو ندرة وهمية."),
    "income_promise": (("I can't promise income or success. I can show the evidence for and against the idea, "
                       "and the risks."),
                       "لا أستطيع أن أعدك بدخل أو نجاح. يمكنني عرض الأدلة مع الفكرة وضدها، والمخاطر."),
    "impersonation": ("I can't pose as you, a customer or another brand.",
                      "لا أستطيع انتحال شخصيتك أو شخصية عميل أو علامة تجارية أخرى."),
    "move_money": ("I can't move, charge or refund money. Payments in this system are mocked only.",
                   "لا أستطيع تحويل أموال أو خصمها أو استردادها. المدفوعات في هذا النظام وهمية (MOCKED) فقط."),
    "store_credentials": (("Please don't share passwords or card numbers: I never store them, and I removed them "
                          "from this message."),
                          "من فضلك لا تشارك كلمات السر أو أرقام البطاقات: لا أخزنها أبداً، وقد حذفتها من رسالتك."),
    "instruction_injection": ("I follow the onboarding steps only; instructions to change my rules are ignored.",
                              "أتبع خطوات الإعداد فقط؛ أتجاهل أي تعليمات لتغيير قواعدي."),
}


@dataclass
class Refusal:
    rule: str

    def message(self, lang: str) -> str:
        return REFUSALS[self.rule][1 if lang == "ar" else 0]


def check_request(text: str) -> Refusal | None:
    """A founder message the system must refuse, or None."""
    if _CARD.search(text):
        return Refusal("store_credentials")
    for rule, pats in _COMPILED.items():
        if any(p.search(text) for p in pats):
            return Refusal(rule)
    return None


_OUTPUT_RULES = {
    "income_promise": [
        r"\bguarantee[ds]?\b.{0,40}\b(income|profit|success|sales|revenue)\b",
        r"\byou (will|'ll) (make|earn)\b", r"\b(risk[- ]free|can't lose|cannot lose)\b",
        r"(دخل|ربح|أرباح|نجاح) مضمون", r"(ستربح|هتكسب|ستكسب) .{0,20}(مضمون|أكيد|بالتأكيد)",
    ],
    "false_urgency": [r"\bonly \d+ left\b", r"\boffer ends (today|tonight|soon)\b", r"عداد تنازلي"],
    "fake_reviews": [r"★★★★★", r"\"[^\"]{5,200}\"\s*[-–—]\s*(happy|satisfied|verified) (customer|buyer)"],
}
_OUTPUT_COMPILED = {r: [re.compile(p, re.IGNORECASE) for p in ps] for r, ps in _OUTPUT_RULES.items()}


def check_output(text: str) -> list[str]:
    """Must-never rules broken by generated text (empty list = OK). Agents must not show text that fails."""
    return [rule for rule, pats in _OUTPUT_COMPILED.items() if any(p.search(text) for p in pats)]


def redact(text: str) -> str:
    """Remove card numbers and the value after 'password:' before the text is stored or logged."""
    text = _CARD.sub("[REDACTED CARD]", text)
    return re.sub(r"((?:password|passcode|pin|كلمة السر|كلمة المرور|الباسورد)\s*(?:is|:|=|هي)?\s*)\S+",
                  r"\1[REDACTED]", text, flags=re.IGNORECASE)
