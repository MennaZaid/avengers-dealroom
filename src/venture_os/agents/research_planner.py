"""Research planner (Discover step 0): topics, queries and sources. Rules only, no model.

Input: a confirmed brief (the shape of GET /onboarding/briefs/{id}) and registry sources.
Output: a ResearchPlan: which sources to read and which searches to run, per topic and language.

Rules that keep it honest:
- Only brief fields whose status is not `unknown` are used; `unknown` is never filled in.
- Sources come only from the registry. If the country has none, the plan says "no verified source".
- A query is written in one language: a founder's value is used in a query only when it is written in that
  language; otherwise a neutral label (industry, country name) stands in, or the query is left out.
- Every query records the brief fields and tags it was built from.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from venture_os.onboarding.tags import COUNTRIES

Lang = Literal["ar", "en"]
NO_COUNTRY_SOURCE = "no verified source"
PLANNER = "rules-v1"

INDUSTRY_LABELS: dict[str, tuple[str, str]] = {  # tag -> (English, Arabic)
    "food_beverage": ("food and beverage", "الأغذية والمشروبات"),
    "delivery_logistics": ("delivery and logistics", "التوصيل والخدمات اللوجستية"),
    "retail_ecommerce": ("retail and e-commerce", "التجارة الإلكترونية والتجزئة"),
    "fintech": ("fintech", "التكنولوجيا المالية"),
    "education": ("education", "التعليم"),
    "health": ("health", "الصحة"),
    "travel_tourism": ("travel and tourism", "السفر والسياحة"),
    "real_estate_construction": ("real estate and construction", "العقارات والبناء"),
    "agriculture": ("agriculture", "الزراعة"),
    "manufacturing": ("manufacturing", "التصنيع"),
    "handmade_crafts": ("handmade crafts", "الحرف اليدوية"),
    "fashion_beauty": ("fashion and beauty", "الأزياء والتجميل"),
    "media_entertainment": ("media and entertainment", "الإعلام والترفيه"),
    "software_saas": ("software", "البرمجيات"),
    "professional_services": ("professional services", "الخدمات المهنية"),
    "energy_environment": ("energy and environment", "الطاقة والبيئة"),
    "transport_mobility": ("transport and mobility", "النقل والمواصلات"),
    "home_services": ("home services", "الخدمات المنزلية"),
}
REVENUE_LABELS: dict[str, tuple[str, str]] = {
    "subscription": ("subscription price", "سعر الاشتراك"),
    "commission": ("commission rate", "نسبة العمولة"),
    "one_off_sales": ("price", "سعر"),
    "saas_license": ("license price", "سعر الترخيص"),
    "advertising": ("advertising rates", "أسعار الإعلانات"),
    "freemium": ("premium plan price", "سعر الباقة المدفوعة"),
    "service_fees": ("service fees", "رسوم الخدمة"),
}
TOPICS: dict[str, tuple[str, str]] = {  # key -> (title, source use)
    "market_size": ("Market size", "market"),
    "competitors": ("Competitors", "market"),
    "customer_pain": ("Customer pain", "market"),
    "pricing": ("Pricing", "market"),
    "regulation": ("Regulation", "legal"),
}
SOURCE_USES = {"market", "legal"}  # analogy / ethics sources are for later stages
PRODUCT_SCOPES = {"digital", "any"}  # sources.product_scope: the system builds digital products only
# Brief industry tag -> ISIC sections. A registry source scoped to sections (sources.industries) is used only when
# the brief's industry maps to one of them; unscoped sources serve every digital product.
ISIC_BY_INDUSTRY: dict[str, set[str]] = {
    "food_beverage": {"I", "C"}, "delivery_logistics": {"H"}, "retail_ecommerce": {"G"}, "fintech": {"K"},
    "education": {"P"}, "health": {"Q"}, "travel_tourism": {"I", "N"}, "real_estate_construction": {"L", "F"},
    "agriculture": {"A"}, "manufacturing": {"C"}, "handmade_crafts": {"C", "G"}, "fashion_beauty": {"C", "G", "S"},
    "media_entertainment": {"J", "R"}, "software_saas": {"J"}, "professional_services": {"M"},
    "energy_environment": {"D", "E"}, "transport_mobility": {"H"}, "home_services": {"N", "S"},
}

_AR = re.compile(r"[؀-ۿ]")


class SourceRef(BaseModel):
    id: str
    source_name: str
    url: str | None = None
    tier: str
    use: str | None = None
    country_codes: list[str] = []
    verified: bool = False
    crawl: str = "full"


class PlannedQuery(BaseModel):
    language: Lang
    text: str
    built_from: list[str]  # e.g. ["fields.idea", "tags.country_code"]


class Topic(BaseModel):
    key: str
    title: str
    kind: Literal["standard", "open_question"]
    queries: list[PlannedQuery] = []
    source_ids: list[str] = []
    skipped_reason: str | None = None


class ResearchPlan(BaseModel):
    planner: str = PLANNER
    brief_id: str
    brief_version: int
    country_code: str
    languages: list[Lang]
    country_sources: list[SourceRef] | Literal["no verified source"]
    global_sources: list[SourceRef]
    topics: list[Topic]
    unknown_fields: list[str]  # left out of every query
    product_check: dict = {}  # from onboarding (guardrails.check_product); product type: agents/brief_analyzer
    notes: list[str] = []


def lang_of(text: str) -> Lang:
    return "ar" if _AR.search(text) else "en"


class _Brief:
    """Read-only view of a brief that refuses `unknown` values."""

    def __init__(self, brief: dict):
        self.fields = brief.get("fields") or {}
        self.tags = brief.get("tags") or {}

    def field(self, name: str) -> str | None:
        f = self.fields.get(name) or {}
        v = f.get("value")
        if f.get("status", "unknown") == "unknown" or not isinstance(v, str) or not v.strip():
            return None
        return v.strip()

    def tag(self, name: str):
        v = (self.tags.get(name) or {}).get("value")
        return None if v in (None, "", "unknown", [], ["unknown"]) else v

    def unknown_fields(self) -> list[str]:
        return sorted(n for n in self.fields if self.field(n) is None)


class _Words:
    """The pieces queries are built from, in one language, each with where it came from."""

    def __init__(self, b: _Brief, lang: Lang):
        idx = 1 if lang == "ar" else 0

        def own(name: str):  # a founder value, only if written in this language
            v = b.field(name)
            return (v, [f"fields.{name}"]) if v and lang_of(v) == lang else (None, [])

        industries = [i for i in (b.tag("industries") or []) if i != "other"]
        labels = [INDUSTRY_LABELS.get(i, (i.replace("_", " "),) * 2)[idx] for i in industries]
        self.industry = (labels[0], ["tags.industries"]) if labels else (None, [])
        idea = own("idea")
        self.subject = idea if idea[0] else self.industry

        cc = b.tag("country_code")
        names = COUNTRIES.get(cc, ()) if isinstance(cc, str) else ()
        name = next((n for n in names if lang_of(n) == lang), None)
        if name:
            self.country = (name.title() if lang == "en" else name, ["tags.country_code"])
        else:
            self.country = own("country")
        city = own("city")
        self.place = city if city[0] else self.country
        self.target = own("target_customer")
        self.problem = own("problem")
        rm = b.tag("revenue_model")
        self.revenue = (REVENUE_LABELS[rm][idx], ["tags.revenue_model"]) if rm in REVENUE_LABELS else (None, [])


_TRIM = re.compile(r"^(?:a|an|the)\s+|[\s.،,;:!؟?]+$", re.IGNORECASE)
_DANGLING = re.compile(r"\s+(?:in|في)\s*$")


def _clean(v: str) -> str:
    return _TRIM.sub("", _TRIM.sub("", v.strip()))


def _q(lang: Lang, template: str, **parts: tuple[str | None, list[str]]) -> PlannedQuery | None:
    """Fill a template; None if any part is missing. A place (p/c) already named in another part is dropped."""
    if any(v is None for v, _ in parts.values()):
        return None
    vals = {k: _clean(v) for k, (v, _) in parts.items()}
    built = {k: srcs for k, (_, srcs) in parts.items()}
    for k in ("p", "c"):
        if k in vals and any(vals[k].lower() in v.lower() for o, v in vals.items() if o != k):
            vals[k], built[k] = "", []
    text = _DANGLING.sub("", " ".join(template.format(**vals).split()))
    return PlannedQuery(language=lang, text=text, built_from=sorted({s for srcs in built.values() for s in srcs}))


def _standard_queries(key: str, lang: Lang, w: _Words, competitors: list[str]) -> list[PlannedQuery | None]:
    en = lang == "en"
    if key == "market_size":
        return [
            _q(lang, "{s} market size {c}" if en else "حجم سوق {s} في {c}", s=w.subject, c=w.country),
            _q(lang, "number of {t} in {p}" if en else "عدد {t} في {p}", t=w.target, p=w.place),
        ]
    if key == "competitors":
        out = [_q(lang, "{s} companies in {c}" if en else "شركات {s} في {c}", s=w.subject, c=w.country),
               _q(lang, "best {i} apps {c}" if en else "أفضل تطبيقات {i} في {c}", i=w.industry, c=w.country)]
        for name in competitors:  # proper names stay as written; the place is in the query language
            out.append(_q(lang, "{n} {c}", n=(name, ["fields.known_competitors"]), c=w.country))
            if en:
                out.append(_q(lang, "{n} alternatives", n=(name, ["fields.known_competitors"])))
        return out
    if key == "customer_pain":
        return [
            _q(lang, "{t} challenges {p}" if en else "تحديات {t} في {p}", t=w.target, p=w.place),
            _q(lang, "{pr} {p}", pr=w.problem, p=w.place),
            _q(lang, "{i} customer complaints {c}" if en else "شكاوى عملاء {i} في {c}", i=w.industry, c=w.country),
            _q(lang, "{pr} reddit" if en else "{pr} تجربتي", pr=w.problem),  # people describing the problem
        ]
    if key == "pricing":
        return [
            _q(lang, "{s} prices in {p}" if en else "أسعار {s} في {p}", s=w.subject, p=w.place),
            _q(lang, "{i} {r} {c}" if en else "{r} في قطاع {i} في {c}", i=w.industry, r=w.revenue, c=w.country),
        ]
    if key == "regulation":
        return [
            _q(lang, "{i} license requirements {c}" if en else "تراخيص {i} في {c}", i=w.industry, c=w.country),
            _q(lang, "{i} laws and regulations {c}" if en else "قوانين ولوائح {i} في {c}", i=w.industry,
               c=w.country),
        ]
    raise ValueError(key)


def split_competitors(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"\s*(?:,|،|;|\n|\band\b|\bو(?=\s))\s*", value)
    return [p.strip(" .") for p in parts if p and p.strip(" .")]


def _ref(row: dict) -> SourceRef:
    return SourceRef(id=row["id"], source_name=row["source_name"], url=row.get("url"), tier=row["tier"],
                     use=row.get("use"), country_codes=list(row.get("country_codes") or []),
                     verified=bool(row.get("verified")), crawl=row.get("crawl") or "full")


def build_plan(brief: dict, sources: list[dict]) -> ResearchPlan:
    """`sources` is what GET /registry/sources?country=<code> returns (country + global sources)."""
    b = _Brief(brief)
    cc = b.tag("country_code")
    cc = cc.upper() if isinstance(cc, str) else None
    languages = [x for x in (b.tag("languages") or []) if x in ("ar", "en")] or ["en"]
    notes: list[str] = []
    if not b.tag("languages"):
        notes.append("languages unknown in the brief: searching in English only")

    sections = {sec for i in (b.tag("industries") or []) for sec in ISIC_BY_INDUSTRY.get(i, set())}
    usable = [s for s in sources if (s.get("use") or "market") in SOURCE_USES
              and (s.get("product_scope") or "any") in PRODUCT_SCOPES  # digital products only
              and (not s.get("industries") or sections & set(s["industries"]))]
    scoped_out = [s["id"] for s in sources if (s.get("product_scope") or "any") not in PRODUCT_SCOPES
                  or (s.get("industries") and not sections & set(s["industries"]))]
    if scoped_out:
        notes.append(f"{len(scoped_out)} sources left out (physical-goods scope or another sector)")
    product_check = brief.get("product_check") or {}
    if product_check.get("status") not in (None, "allowed"):
        notes.append(f"product check from onboarding: {product_check.get('status')} "
                     f"({', '.join(product_check.get('categories') or [])})")
    country = [_ref(s) for s in usable if cc and cc in (s.get("country_codes") or [])]
    global_ = [_ref(s) for s in usable if not s.get("country_codes")]
    if not cc:
        notes.append("country unknown in the brief: no country sources, global sources only")
    elif not country:
        notes.append(f"no {cc} source in the registry: country facts must come from web search and be checked")
    elif not any(s.verified for s in country):
        notes.append(f"{len(country)} {cc} sources listed, none verified by an admin yet")

    words = {lang: _Words(b, lang) for lang in languages}
    competitors = split_competitors(b.field("known_competitors"))
    topics: list[Topic] = []
    for key, (title, use) in TOPICS.items():
        ids = [s.id for s in country + global_ if (s.use or "market") == use]
        queries, seen = [], set()
        for lang in languages:
            for q in _standard_queries(key, lang, words[lang], competitors):
                if q and q.text.lower() not in seen:
                    seen.add(q.text.lower())
                    queries.append(q)
        topics.append(Topic(key=key, title=title, kind="standard", queries=queries, source_ids=ids,
                            skipped_reason=None if queries else "the brief fields this topic needs are unknown"))

    open_ids = [s.id for s in country + global_]
    for i, question in enumerate(brief.get("open_questions") or [], 1):
        if not isinstance(question, str) or not question.strip():
            continue
        q = question.strip()
        topics.append(Topic(key=f"open_question_{i}", title=q, kind="open_question", source_ids=open_ids,
                            queries=[PlannedQuery(language=lang_of(q), text=q,
                                                  built_from=[f"open_questions[{i - 1}]"])]))

    return ResearchPlan(
        brief_id=str(brief.get("brief_id")), brief_version=int(brief.get("version") or 0),
        country_code=cc or "unknown", languages=languages,
        country_sources=country or NO_COUNTRY_SOURCE, global_sources=global_,
        topics=topics, unknown_fields=b.unknown_fields(), product_check=product_check, notes=notes,
    )
