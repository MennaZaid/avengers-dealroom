"""The founder brief: which fields exist, which are required, and what to ask for each (English and Arabic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

# answered: the founder said it. from_document: read from an upload. inferred: deduced, not stated
# (e.g. country from a city name) and shown to the founder to confirm. unknown: never guessed.
Status = Literal["answered", "from_document", "inferred", "unknown"]
Lang = Literal["en", "ar"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    required: bool
    description: str  # what the extractor should look for
    ask_en: str
    ask_ar: str
    aliases: tuple[str, ...] = ()  # words that name this field in an unlabelled correction (en + ar)

    def ask(self, lang: Lang) -> str:
        return self.ask_ar if lang == "ar" else self.ask_en


FIELDS: list[FieldSpec] = [
    FieldSpec("idea", True, "The business idea in one or two sentences",
              "What is your business idea? One or two sentences is enough.",
              "ما هي فكرة مشروعك؟ جملة أو جملتان تكفي.",
              ("idea", "فكرة", "الفكرة")),
    FieldSpec("problem", True, "The customer problem the idea solves",
              "What problem does it solve, and for whom?",
              "ما المشكلة التي تحلها الفكرة، ولمن؟",
              ("problem", "مشكلة", "المشكلة")),
    FieldSpec("target_customer", True, "Who the customers are",
              "Who exactly are your target customers? For example: age, job, business type.",
              "من هم عملاؤك المستهدفون بالتحديد؟ مثلاً: العمر، المهنة، نوع النشاط.",
              ("target customer", "customer", "customers", "audience", "عملاء", "العملاء", "العميل", "الجمهور")),
    FieldSpec("country", True, "Country of the target market",
              "Which country will you launch in first?",
              "في أي دولة ستبدأ أولاً؟",
              ("country", "دولة", "الدولة", "بلد", "البلد")),
    FieldSpec("city", False, "City or region, if specific",
              "Is there a specific city or region?",
              "هل هناك مدينة أو منطقة محددة؟",
              ("city", "region", "مدينة", "المدينة", "منطقة", "المنطقة")),
    FieldSpec("budget", True, "Money available to start, with currency",
              "What budget do you have to start, and in which currency? A rough range is fine.",
              "ما الميزانية المتاحة للبدء، وبأي عملة؟ يكفي نطاق تقريبي.",
              ("budget", "money", "capital", "ميزانية", "الميزانية", "رأس المال", "فلوس")),
    FieldSpec("time_available", True, "Hours per week and months available",
              "How much time can you give it: hours per week, and for how many months?",
              "كم من الوقت يمكنك تخصيصه: ساعات في الأسبوع، ولكم شهراً؟",
              ("time", "hours", "وقت", "الوقت", "ساعات")),
    FieldSpec("founder_skills", True, "Founder skills and technical abilities",
              "What skills do you and your team have? For example: design, coding, sales, operations.",
              "ما المهارات المتوفرة لديك ولدى فريقك؟ مثلاً: تصميم، برمجة، مبيعات، تشغيل.",
              ("skills", "skill", "team", "مهارات", "المهارات", "الفريق")),
    FieldSpec("business_model", False, "How the business makes money (B2C, B2B, marketplace, subscription...)",
              "Do you already know how it will make money? For example: subscription, commission, one-off sales.",
              "هل تعرف كيف سيحقق المشروع دخلاً؟ مثلاً: اشتراك، عمولة، بيع مباشر.",
              ("business model", "revenue", "monetization", "نموذج العمل", "الدخل", "الربح")),
    FieldSpec("values", False, "Personal or business values that limit choices",
              "Are there values the business must respect? For example: fair pay, no data selling.",
              "هل هناك قيم يجب أن يلتزم بها المشروع؟ مثلاً: أجور عادلة، عدم بيع البيانات.",
              ("values", "قيم", "القيم")),
    FieldSpec("technical_preferences", False,
              "Technology the founder explicitly wants or rules out for the product (app, website, no-code). "
              "Not the team's skills: 'nobody on the team codes' belongs in founder_skills",
              "Any technical preferences? For example: mobile app, website only, no-code.",
              "هل لديك تفضيلات تقنية؟ مثلاً: تطبيق جوال، موقع فقط، بدون برمجة.",
              ("technical", "tech", "technology", "platform", "تقنية", "التقنية", "منصة")),
    FieldSpec("known_competitors", False, "Competitors the founder already knows",
              "Do you know any competitors already? Names or links help.",
              "هل تعرف منافسين حاليين؟ الأسماء أو الروابط تساعد.",
              ("competitors", "competitor", "competition", "منافسين", "المنافسين", "منافس")),
    # Asked only for two-sided ideas (a marketplace or booking platform): who supplies, as opposed to who pays.
    FieldSpec("supply_side", False,
              "For a marketplace or booking platform: who provides the product or service (the other side from "
              "the paying customers)",
              "Your idea connects two groups. Who provides the product or service on your platform (for example "
              "cleaners, tutors, designers), and how will you find the first ones?",
              "فكرتك تربط بين مجموعتين. من سيقدم المنتج أو الخدمة على منصتك (مثلاً عمال نظافة، مدرسين، مصممين)، "
              "وكيف ستجد أول مجموعة منهم؟",
              ("supply side", "providers", "provider", "sellers", "suppliers", "مقدمي الخدمة", "البائعين",
               "الموردين", "جانب العرض")),
]
BY_NAME = {f.name: f for f in FIELDS}

# Labels shown to the founder. English labels are the field names with spaces.
LABELS_AR = {
    "idea": "الفكرة", "problem": "المشكلة", "target_customer": "العملاء المستهدفون", "country": "الدولة",
    "city": "المدينة", "budget": "الميزانية", "time_available": "الوقت المتاح", "founder_skills": "مهارات الفريق",
    "business_model": "نموذج العمل", "values": "القيم", "technical_preferences": "التفضيلات التقنية",
    "known_competitors": "المنافسون المعروفون", "supply_side": "مقدمو الخدمة",
    # tags
    "industries": "القطاعات", "customer_type": "نوع العملاء", "revenue_model": "نموذج الإيرادات",
    "country_code": "رمز الدولة", "languages": "اللغات",
}


def label(name: str, lang: str = "en") -> str:
    return LABELS_AR.get(name, name.replace("_", " ")) if lang == "ar" else name.replace("_", " ")
REQUIRED = [f.name for f in FIELDS if f.required]


class FieldValue(BaseModel):
    value: str | None = None
    status: Status = "unknown"
    source: str = "chat"  # "chat" or "document:<filename>"
    quote: str | None = None  # exact text it came from, for documents


class FollowUp(BaseModel):
    """An idea-specific question asked after the standard fields. Never a fact, only a question."""

    question: str
    answer: str | None = None  # None = not answered (skipped or not asked yet)
    asked: bool = False
    source: str = "rules"  # who wrote the question: "rules" or "model"


class Tag(BaseModel):
    value: str | list[str]
    basis: Literal["rules", "model", "founder"] = "rules"


class Message(BaseModel):
    role: Literal["founder", "assistant", "system"]
    text: str


class OnboardingState(BaseModel):
    # collecting -> confirming -> confirmed. After confirming, any change reopens "confirming";
    # each new "yes" saves the next brief version.
    phase: Literal["collecting", "confirming", "confirmed"] = "collecting"
    session_id: str | None = None  # stamped on every decision-log entry of this conversation
    brief_id: str | None = None  # set once the founder confirms; later stages log under it
    lang: Lang = "en"
    asking: str | None = None  # field the last question was about
    skipped: list[str] = []
    fields: dict[str, FieldValue] = {}
    documents: list[str] = []
    messages: list[Message] = []
    tags: dict[str, Tag] = {}
    followups: list[FollowUp] = []
    followups_ready: bool = False  # follow-up questions generated (once per session)
    version: int = 0  # last saved brief version (0 = never confirmed)
    saved: dict | None = None  # last saved brief, to undo an edit with "cancel"
    changed: list[str] = []  # fields/tags changed since the last saved version
    tags_stale: bool = True  # fields changed since tags were computed
    # Required fields the model picked up in passing with only 1-3 words ("Pharmacist"): still asked, showing
    # what we have, so details like "and I can write basic Python" are not lost.
    thin: list[str] = []
    # Fields that described an earlier idea: asked again ("is the problem still ...?") after the idea changes.
    recheck: list[str] = []
    optional_offered: bool = False
    last_changes: list[str] = []  # what the last saved version changed (for its change note)
    # Questions only research can answer (prices, market size, regulations). Not asked to the founder;
    # handed to the Discover stage as open questions.
    open_questions: list[str] = []
    budget_parsed: dict | None = None  # money.parse_budget(): min, max, currency (None = could not read it)
    product_check: dict = {}  # guardrails.check_product(): status allowed/review/excluded, categories, matched

    def get(self, name: str) -> FieldValue:
        return self.fields.get(name) or FieldValue()

    def filled(self, name: str) -> bool:
        return self.get(name).status in ("answered", "from_document", "inferred")

    def brief(self) -> dict:
        """The confirmed brief: every field with its value and where it came from."""
        return {f.name: self.get(f.name).model_dump() for f in FIELDS}

    def snapshot(self) -> dict:
        """Everything a brief version stores: fields, tags, follow-up answers."""
        return {
            "fields": self.brief(),
            "tags": {k: v.model_dump() for k, v in self.tags.items()},
            "followups": [f.model_dump() for f in self.followups],
            "open_questions": list(self.open_questions),
            "product_check": dict(self.product_check),
            "budget": self.budget_parsed,
        }
