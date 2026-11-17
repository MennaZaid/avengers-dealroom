"""Phase 4 Commercial, steps 1-2: pricing research (sourced prices only) and the price setter (plain code).

- research_prices(items): only Phase 1/2 evidence items that are EVIDENCED (source URL + date) and contain a
  price figure. Nothing else becomes a price row: no URL or no date -> left out, and counted.
- set_price(prices, brief): min / median / max in the most common currency, a proposed price (the median) and a
  break-even estimate: the founder's stated budget divided by the median price, as paying customer-months, and
  per month over the founder's stated months. Every figure is labelled ESTIMATE. No income is promised.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from typing import Any

from pydantic import BaseModel

PRICE_KINDS = {"price", "competitor", "revenue"}
_CUR = {"$": "USD", "usd": "USD", "dollar": "USD", "egp": "EGP", "le": "EGP", "جنيه": "EGP", "kes": "KES",
        "ksh": "KES", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "sar": "SAR", "aed": "AED"}
_PRICE = re.compile(
    r"(?P<pre>\$|€|£|usd|egp|kes|ksh|sar|aed|le)\s?(?P<a>\d[\d,]*(?:\.\d+)?)"
    r"|(?P<b>\d[\d,]*(?:\.\d+)?)\s?(?P<post>usd|egp|kes|ksh|sar|aed|eur|gbp|dollars?|جنيه|le\b)", re.IGNORECASE)
_FREE = re.compile(r"\bfree\b|مجاني", re.IGNORECASE)
_MONTHS = re.compile(r"(\d+)\s*(months?|شهور|أشهر|شهر)", re.IGNORECASE)


class PriceRow(BaseModel):
    item_id: str
    text: str
    amount: float
    currency: str
    url: str
    date: str


class PriceSetting(BaseModel):
    currency: str | None = None
    n: int = 0
    min: float | None = None
    median: float | None = None
    max: float | None = None
    proposed: float | None = None
    all_free: bool = False
    budget: float | None = None
    months: int | None = None
    customer_months: int | None = None  # budget / median, rounded up (ESTIMATE)
    per_month: int | None = None  # customer_months / months, rounded up (ESTIMATE)
    note: str = ""


def _get(item: Any, key: str, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def parse_price(text: str) -> tuple[float, str] | None:
    """(amount, currency) from text like '$9.99/month', '150 EGP', 'Free'. None when no price is stated."""
    m = _PRICE.search(text)
    if m:
        raw = m.group("a") or m.group("b")
        unit = (m.group("pre") or m.group("post") or "").lower()
        unit = "usd" if unit.startswith("dollar") else unit
        return float(raw.replace(",", "")), _CUR.get(unit, unit.upper())
    if _FREE.search(text):
        return 0.0, ""
    return None


def research_prices(items: list) -> tuple[list[PriceRow], int]:
    """Sourced price rows, and how many price-like items were left out (no URL, no date or not evidenced)."""
    rows, skipped = [], 0
    for i, it in enumerate(items or [], start=1):
        if _get(it, "kind") not in PRICE_KINDS:
            continue
        text = str(_get(it, "text") or "")
        parsed = parse_price(text)
        if parsed is None:
            continue
        url = next((u for u in (_get(it, "sources") or []) if str(u).startswith(("http://", "https://"))), None)
        date = _get(it, "date")
        if _get(it, "label") != "evidenced" or not url or not date:
            skipped += 1
            continue
        rows.append(PriceRow(item_id=str(_get(it, "id") or f"E{i}"), text=text[:200], amount=parsed[0],
                             currency=parsed[1], url=url, date=str(date)))
    return rows, skipped


def months_from(text: str | None) -> int | None:
    m = _MONTHS.search(text or "")
    return int(m.group(1)) if m else None


def set_price(rows: list[PriceRow], brief: Any) -> PriceSetting:
    paid = [r for r in rows if r.amount > 0]
    if rows and not paid:
        return PriceSetting(n=len(rows), all_free=True, note="Every sourced price is free: no viable price.")
    if not paid:
        return PriceSetting(n=0, note="No sourced price.")
    currency = Counter(r.currency for r in paid).most_common(1)[0][0]
    amounts = sorted(r.amount for r in paid if r.currency == currency)
    median = round(statistics.median(amounts), 2)
    s = PriceSetting(currency=currency, n=len(rows), min=amounts[0], median=median, max=amounts[-1], proposed=median)
    budget = getattr(brief, "budget", None) or {}
    months = months_from(brief.known("time_available") if hasattr(brief, "known") else None)
    s.months = months
    if budget.get("currency") == currency and (budget.get("max") or budget.get("min")):
        s.budget = float(budget.get("max") or budget.get("min"))
        s.customer_months = math.ceil(s.budget / median)
        if months:
            s.per_month = math.ceil(s.customer_months / months)
    else:
        s.note = ("Break-even not computed: the founder's budget is unknown or in a different currency "
                  f"({budget.get('currency') or 'unknown'} vs {currency}).")
    return s
