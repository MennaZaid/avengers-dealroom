"""Turn the founder's budget text into numbers the Commercial stage can use.

"حوالي خمسين الف جنيه" -> {"min": 50000, "max": 50000, "currency": "EGP"}; "20-30k USD" -> 20000..30000 USD.
Plain rules (no model). The founder's own words stay the field value; this is an extra, and None when unsure.
If no currency is written, the target country's currency is used and marked as such (not as stated).
"""

from __future__ import annotations

import re

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

CURRENCIES = {  # code -> words founders use (lower case)
    "EGP": ("egp", "le", "l.e", "جنيه", "جنية", "ج.م", "egyptian pound"),
    "USD": ("usd", "$", "dollar", "dollars", "دولار"),
    "EUR": ("eur", "€", "euro", "euros", "يورو"),
    "GBP": ("gbp", "£", "sterling", "british pound", "استرليني"),
    "SAR": ("sar", "riyal", "riyals", "ريال سعودي", "ريال"),
    "AED": ("aed", "dirham", "dirhams", "درهم"),
    "KES": ("kes", "ksh", "kshs", "shilling", "shillings", "شلن"),
    "QAR": ("qar", "ريال قطري"), "KWD": ("kwd", "دينار كويتي"), "JOD": ("jod", "دينار أردني"),
    "MAD": ("mad", "درهم مغربي"),
}
COUNTRY_CURRENCY = {"EG": "EGP", "US": "USD", "GB": "GBP", "SA": "SAR", "AE": "AED", "KE": "KES", "QA": "QAR",
                    "KW": "KWD", "JO": "JOD", "MA": "MAD", "DE": "EUR", "FR": "EUR"}

_MULT = {"k": 1e3, "thousand": 1e3, "الف": 1e3, "ألف": 1e3, "آلاف": 1e3, "الاف": 1e3, "m": 1e6, "mn": 1e6,
         "million": 1e6, "مليون": 1e6, "ملايين": 1e6}
_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
    "واحد": 1, "اتنين": 2, "اثنين": 2, "تلاتة": 3, "ثلاثة": 3, "اربعة": 4, "أربعة": 4, "خمسة": 5, "ستة": 6,
    "سبعة": 7, "تمانية": 8, "ثمانية": 8, "تسعة": 9, "عشرة": 10, "عشرين": 20, "عشرون": 20, "تلاتين": 30,
    "ثلاثين": 30, "اربعين": 40, "أربعين": 40, "خمسين": 50, "ستين": 60, "سبعين": 70, "تمانين": 80, "ثمانين": 80,
    "تسعين": 90, "مية": 100, "مائة": 100, "مئة": 100, "ميت": 100,
}
_NUM = r"\d+(?:[.,]\d+)?"
_MULT_RE = "|".join(sorted((re.escape(m) for m in _MULT), key=len, reverse=True))
_AMOUNT = re.compile(rf"({_NUM})\s*({_MULT_RE})?(?![a-z؀-ۿ])", re.IGNORECASE)


def _to_number(num: str, mult: str | None) -> float:
    n = num.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", num) else num.replace(",", ".")
    return float(n) * (_MULT.get((mult or "").lower(), 1))


def _words_to_digits(text: str) -> str:
    """'خمسين الف' -> '50 الف'; 'twenty five thousand' -> '25 thousand' (simple tens + units)."""
    tokens = re.split(r"(\s+|و(?=[؀-ۿ]))", text)
    out, acc = [], None
    for tok in tokens:
        w = tok.strip().lower()
        if w in _WORDS:
            acc = (acc or 0) + _WORDS[w]
            continue
        if acc is not None and (not w or w == "و" or w == "and"):
            continue
        if acc is not None:
            out.append(f"{acc} ")
            acc = None
        out.append(tok)
    if acc is not None:
        out.append(str(acc))
    return "".join(out)


def _currency(text: str) -> str | None:
    t = f" {text.lower()} "
    for code, words in sorted(CURRENCIES.items(), key=lambda kv: -max(len(w) for w in kv[1])):
        for w in sorted(words, key=len, reverse=True):
            if w in ("$", "€", "£"):
                if w in t:
                    return code
            elif re.search(rf"(?<![a-z؀-ۿ]){re.escape(w)}(?![a-z])", t):
                return code
    return None


def parse_budget(text: str | None, country_code: str | None = None) -> dict | None:
    """{'min', 'max', 'currency', 'currency_source': 'stated'|'country_default'} or None if no amount."""
    if not text:
        return None
    t = _words_to_digits(text.translate(_DIGITS))
    amounts = []
    for m in _AMOUNT.finditer(t):
        amounts.append(_to_number(m.group(1), m.group(2)))
    if not amounts:
        return None
    # "20-30k": the multiplier written once applies to both ends.
    if len(amounts) >= 2 and amounts[1] >= 1000 > amounts[0] and amounts[1] / 1000 > amounts[0]:
        amounts[0] *= 1000 if amounts[1] < 1e6 else 1e6
    lo, hi = min(amounts[:2]), max(amounts[:2])
    currency = _currency(text)
    source = "stated"
    if currency is None:
        currency, source = COUNTRY_CURRENCY.get((country_code or "").upper()), "country_default"
    return {"min": int(lo) if lo == int(lo) else lo, "max": int(hi) if hi == int(hi) else hi,
            "currency": currency, "currency_source": source if currency else None}


def format_budget(b: dict | None) -> str:
    if not b:
        return ""
    amount = f"{b['min']:,}" if b["min"] == b["max"] else f"{b['min']:,}-{b['max']:,}"
    cur = b["currency"] or "?"
    return f"{amount} {cur}" + (" (currency assumed from the country)" if b.get("currency_source") ==
                                "country_default" else "")
