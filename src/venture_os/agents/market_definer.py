"""Market definer (Discover step 4): segment, geography, beachhead; competitors and substitutes with sourced
prices; bottom-up TAM / SAM / SOM as ranges with the formula and the source of every input.

Data: the competitor web agent (agents/competitor_intelligence.py) and the market web agent on the market-size
and pricing topics, plus free APIs: App Store listings (price, rating count), WordPress.org plugins (installs),
GitHub repositories (open-source substitutes) and World Bank WDI internet users (digital reach).
Bottom-up method (corpus M-026): TAM = target customers x yearly price; SAM = TAM x share reachable online;
SOM = SAM x obtainable share. A missing input stays missing: the total is then "unknown", never guessed.
"""

from __future__ import annotations

import re
import statistics
from datetime import UTC, datetime

from venture_os.agents.base import Evidence, Toolbox, Trace
from venture_os.agents.brief_analyzer import DiscoverBrief
from venture_os.agents.opportunity_finder import DEV_TYPES, api_queries, item_page
from venture_os.agents.research_planner import ResearchPlan
from venture_os.agents.schemas import Claim, Competitor, MarketDefinition, SizingInput
from venture_os.tools.search import SearchError

CURRENCY = r"(?:US\$|\$|USD|EGP|E£|LE|KES|KSh|SAR|AED|€|EUR|£|GBP|جنيه|ج\.م|دولار)"
NUM = r"\d{1,3}(?:[,٬]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
PRICE_RE = re.compile(rf"(?:{CURRENCY}\s?(?P<a>{NUM})|(?P<b>{NUM})\s?{CURRENCY})", re.IGNORECASE)
MONTHLY = re.compile(r"/\s?(?:mo|month)|per month|a month|monthly|شهري|في الشهر|/شهر", re.IGNORECASE)
SCALE = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "ألف": 1e3, "الف": 1e3,
         "مليون": 1e6, "مليار": 1e9}
OBTAINABLE_SHARE = (0.01, 0.05)  # ASSUMPTION: first-years share of the reachable market


def _num(s: str) -> float:
    return float(s.replace(",", "").replace("٬", ""))


def currency_of(text: str) -> str:
    t = text.upper()
    for code, keys in (("EGP", ("EGP", "E£", " LE", "جنيه", "ج.م")), ("KES", ("KES", "KSH")), ("SAR", ("SAR",)),
                       ("AED", ("AED",)), ("EUR", ("€", "EUR")), ("GBP", ("£", "GBP")),
                       ("USD", ("$", "USD", "دولار"))):
        if any(k in t or k in text for k in keys):
            return code
    return "?"


def find_prices(text: str) -> list[tuple[float, str, bool, str]]:
    """(amount, currency, monthly, sentence) for each price in the text, sentence copied verbatim."""
    out = []
    for sent in re.split(r"(?<=[.!?؟])\s+|\n+", text):
        for m in PRICE_RE.finditer(sent):
            amount = _num(m.group("a") or m.group("b"))
            if 0 < amount < 1_000_000:
                out.append((amount, currency_of(m.group(0)), bool(MONTHLY.search(sent)), sent.strip()[:400]))
    return out


def count_near(text: str, target_words: list[str]) -> list[tuple[float, str]]:
    """Counts like '5,245 pharmacies' / '12,000 freelancers' where a target word follows the number."""
    out = []
    words = "|".join(re.escape(w) for w in target_words if len(w) > 3)
    if not words:
        return out
    pat = re.compile(rf"({NUM})\s*(thousand|million|billion|k|m|bn|ألف|الف|مليون|مليار)?\s+(?:\w+\s+){{0,3}}?"
                     rf"(?:{words})", re.IGNORECASE)
    after = re.compile(rf"(?:number|total|count|عدد)\W+(?:of\W+)?(?:\w+\W+){{0,2}}?(?:{words})(?:\W+\w+){{0,10}}?"
                       rf"\W+({NUM})\s*(thousand|million|billion|ألف|الف|مليون|مليار)?", re.IGNORECASE)
    for sent in re.split(r"(?<=[.!?؟])\s+|\n+", text):
        for m in [*pat.finditer(sent), *after.finditer(sent)]:
            v = _num(m.group(1)) * SCALE.get((m.group(2) or "").lower(), 1)
            if v >= 50 and not (1900 <= v <= 2100 and "," not in m.group(1)):  # not "3 shops", not a year
                out.append((v, sent.strip()[:400]))
    return out


def api_competitors(plan: ResearchPlan, db: DiscoverBrief, toolbox: Toolbox, trace: Trace) -> list[tuple]:
    """(Item, Evidence) for App Store apps, WordPress plugins and GitHub repos."""
    apis = getattr(toolbox, "apis", None)
    if apis is None:
        return []
    country = plan.country_code.lower() if plan.country_code != "unknown" else "us"
    qs = api_queries(plan, db)[:2]
    calls = [("itunes_search", lambda q: apis.itunes_search(q, country))]
    if db.product_type.label in DEV_TYPES | {"template_or_asset", "web_app"}:
        calls.append(("wordpress_plugins", apis.wordpress_plugins))
    if db.product_type.label in DEV_TYPES:
        calls.append(("github_repos", apis.github_repos))
    found = []
    for q in qs:
        for name, call in calls:
            try:
                items = call(q)
            except SearchError as e:
                trace.add("market_definer", "api_failed", api=name, query=q, error=str(e)[:150])
                continue
            trace.add("market_definer", "api_call", api=name, query=q, results=len(items),
                      sources=[i.url for i in items])
            for it in items:
                found.append((it, Evidence("competitors", q, "market_definer", toolbox.save_page(item_page(it)))))
    return found


def _claim_id(prefix: str, n: int) -> str:
    return f"{prefix}{n}"


def define_market(plan: ResearchPlan, db: DiscoverBrief, web_competitors: list[dict], claims: list[Claim],
                  api_found: list[tuple], reach: Claim | None) -> tuple[MarketDefinition, list[Claim]]:
    """Returns the market definition and the new claims it created (prices, counts)."""
    new: list[Claim] = []
    now = datetime.now(UTC).isoformat(timespec="seconds")
    competitors: dict[str, Competitor] = {}
    for it, ev in api_found:
        if it.kind != "competitor" or it.url in competitors:
            continue
        price = it.extra.get("formatted_price")
        cid = None
        if price is not None:
            cid = _claim_id("C", len(claims) + len(new) + 1)
            quote = f"{it.title}: price {price}" + (f"; {it.extra['rating_count']} ratings"
                                                    if it.extra.get("rating_count") is not None else "")
            new.append(Claim(id=cid, type="fact", topic="competitor_price", text=quote, quote=quote, url=it.url,
                             title=it.title, retrieved_at=now, published_at=str(it.published or "") or None,
                             source_id=it.source_id, source_kind="api_store", extracted_by="rules",
                             document_id=ev.chunks[0].document_id if ev.chunks else None,
                             chunk_id=ev.chunks[0].chunk_id if ev.chunks else None))
        signal = ", ".join(f"{k} {v}" for k, v in it.extra.items()
                           if k in ("rating_count", "active_installs", "stars") and v is not None)
        free = (it.extra.get("price") == 0)
        competitors[it.url] = Competitor(
            name=it.title[:120], url=it.url, kind="open_source" if it.source_id == "R-074" else "direct",
            price=price, pricing_model="free" if free else ("paid" if it.extra.get("price") else "unknown"),
            price_claim_id=cid, signal=signal, source_id=it.source_id)
    # prices quoted on competitor / pricing pages found by the web agents
    for c in claims:
        if c.topic not in ("competitors", "pricing") or not c.quote or not c.url:
            continue
        for amount, cur, monthly, sent in find_prices(c.quote):
            cid = _claim_id("C", len(claims) + len(new) + 1)
            new.append(Claim(id=cid, type="fact", topic="competitor_price", text=sent, quote=sent, url=c.url,
                             title=c.title, retrieved_at=c.retrieved_at, published_at=c.published_at,
                             source_id=c.source_id, source_kind=c.source_kind, flags=c.flags,
                             extracted_by="rules", document_id=c.document_id, chunk_id=c.chunk_id))
            comp = competitors.get(c.url) or Competitor(name=(c.title or c.url)[:120], url=c.url, kind="direct")
            comp.price = f"{cur} {amount:g}" + ("/month" if monthly else "")
            comp.pricing_model = "subscription" if monthly else "paid"
            comp.price_claim_id = cid
            competitors[c.url] = comp
            break
    for w in web_competitors:
        if w.get("url") and w["url"] not in competitors:
            competitors[w["url"]] = Competitor(name=w["name"][:120], url=w["url"], kind="direct",
                                               signal=w.get("status", ""))

    # ---- bottom-up sizing ----
    target = db.optional.get("target_customer") or db.required.get("target_market") or ""
    tw = [w.lower() for w in re.findall(r"[\w؀-ۿ]+", target)]
    count_inputs = []
    for c in claims:
        if c.topic in ("market_size", "customer_pain") and c.quote and "stale" not in c.flags:
            for v, sent in count_near(c.quote, tw):
                count_inputs.append((v, c))
    inputs: list[SizingInput] = []
    if count_inputs:
        vals = sorted(v for v, _ in count_inputs)
        src = count_inputs[0][1]
        inputs.append(SizingInput(name="target customers", low=vals[0], high=vals[-1], unit="customers",
                                  claim_id=src.id, basis="sourced", note=src.quote[:200]))
    else:
        inputs.append(SizingInput(name="target customers", low=None, high=None, unit="customers",
                                  note="no sourced count of the target customers found: ASSUMPTION needed"))
    prices = []
    for comp in competitors.values():
        if comp.price_claim_id and comp.price and comp.pricing_model != "free":
            m = re.search(rf"({NUM})", comp.price.replace(",", ""))
            if m:
                amt = _num(m.group(1)) * (12 if comp.pricing_model == "subscription" else 1)
                prices.append((amt, comp))
    currency = "?"
    if prices:
        amounts = [p for p, _ in prices]
        currency = currency_of(prices[0][1].price or "") if prices[0][1].price else "?"
        if currency == "?":
            currency = "USD" if any("$" in (c.price or "") for _, c in prices) else "?"
        inputs.append(SizingInput(name="price per customer per year", low=min(amounts),
                                  high=statistics.median(amounts) if len(amounts) > 2 else max(amounts),
                                  unit=f"{currency}/year", claim_id=prices[0][1].price_claim_id, basis="sourced",
                                  note=f"from {len(prices)} paid competitors (subscriptions x 12); currencies "
                                       "may differ: check before using"))
    else:
        inputs.append(SizingInput(name="price per customer per year", low=None, high=None, unit="?/year",
                                  note="no sourced paid price found: ASSUMPTION needed"))
    if reach:
        v = reach.quote.rsplit(":", 1)[-1].strip() if reach.quote else ""
        try:
            pct = float(v) / 100
            inputs.append(SizingInput(name="share online (internet users)", low=pct, high=pct, unit="share",
                                      claim_id=reach.id, basis="sourced", note=reach.quote))
        except ValueError:
            reach = None
    if not reach:
        inputs.append(SizingInput(name="share online (internet users)", low=None, high=None, unit="share",
                                  note="no internet-use figure for the country"))
    inputs.append(SizingInput(name="obtainable share (first years)", low=OBTAINABLE_SHARE[0],
                              high=OBTAINABLE_SHARE[1], unit="share", basis="ASSUMPTION",
                              note="ASSUMPTION: 1-5% of the reachable market in the first years"))

    def rng(*vals):
        if any(v is None for v in vals):
            return None
        out = 1.0
        for v in vals:
            out *= v
        return round(out, 2)
    cust, price, share, obt = inputs[0], inputs[1], inputs[2], inputs[3]
    tam = (rng(cust.low, price.low), rng(cust.high, price.high))
    sam = (rng(tam[0], share.low), rng(tam[1], share.high))
    som = (rng(sam[0], obt.low), rng(sam[1], obt.high))
    geography = ", ".join(x for x in (db.optional.get("city"), db.optional.get("country")) if x) or \
        (plan.country_code if plan.country_code != "unknown" else "unknown")
    beach = (f"{target} in {db.optional.get('city')}" if db.optional.get("city") and target else
             (target or "unknown - the target customer is not in the brief"))
    notes = []
    if not count_inputs or not prices:
        notes.append("TAM/SAM/SOM stay unknown until every input is sourced; collect the missing inputs above.")
    return MarketDefinition(
        segment=target or "unknown", geography=geography, beachhead=beach,
        competitors=list(competitors.values())[:25], inputs=inputs,
        formula="TAM = target customers x price per year; SAM = TAM x share online; SOM = SAM x obtainable share",
        tam=tam, sam=sam, som=som, currency=currency, notes=notes), new
