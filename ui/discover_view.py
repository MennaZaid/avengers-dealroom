"""Plain helpers for the Discover page (no Streamlit here, so they are unit-tested in replay mode).

- run_label: what the run itself did (completed / running / failed), never confused with the gate's advice.
- gate_banner: the gate recommendation as the most visible line, coloured by outcome.
- market_size_line: one honest line when no market figure was sourced.
- price_cell / exportable: competitors without a price, and tables that would export as empty files.
"""

from __future__ import annotations

# run status -> (en, ar). The gate's recommendation is shown separately; this only says what the run did.
RUN = {
    "running": ("Run: ⏳ researching", "التشغيل: ⏳ جارٍ البحث"),
    "awaiting_approval": ("Run: ✅ completed · waiting for your decision", "التشغيل: ✅ اكتمل · بانتظار قرارك"),
    "revision_requested": ("Run: ✅ completed · you chose Repeat", "التشغيل: ✅ اكتمل · اخترت الإعادة"),
    "approved": ("Run: ✅ completed · you chose Go", "التشغيل: ✅ اكتمل · اخترت المتابعة"),
    "pivoted": ("Run: ✅ completed · you chose Pivot", "التشغيل: ✅ اكتمل · اخترت التحويل"),
    "rejected": ("Run: ✅ completed · you chose Stop", "التشغيل: ✅ اكتمل · اخترت الإيقاف"),
    "failed": ("Run: ❌ failed", "التشغيل: ❌ فشل"),
}
# outcome -> Streamlit element: stop red, pivot/repeat amber, go green
COLOUR = {"stop": "error", "pivot": "warning", "repeat": "warning", "go": "success"}
REC = ("Recommendation: {o}", "التوصية: {o}")
MARKET_UNKNOWN = ("Market size unknown: no sourced figures found. The system doesn't estimate without sources.",
                  "حجم السوق غير معروف: لم يُعثر على أرقام موثقة. النظام لا يقدّر بدون مصادر.")
NO_PRICE = ("no published price found", "لم يُعثر على سعر منشور")
NOTHING = ("nothing to export yet", "لا يوجد ما يُصدَّر بعد")


def _i(lang: str) -> int:
    return 1 if lang == "ar" else 0


def run_label(status: str, lang: str = "en") -> str:
    return RUN[status][_i(lang)] if status in RUN else status


def gate_banner(gate: dict, lang: str = "en") -> tuple[str, str]:
    """(streamlit element name, markdown) for the gate recommendation; the recommendation is the heading."""
    rec = str(gate.get("recommendation") or "").lower()
    head = REC[_i(lang)].format(o=rec.upper()) + (f" → {gate['pivot_to']}" if gate.get("pivot_to") else "")
    reasons = " ".join(gate.get("reasons") or [])
    return COLOUR.get(rec, "info"), f"### {head}" + (f"\n\n{reasons}" if reasons else "")


def _known(x) -> bool:
    return isinstance(x, (list, tuple)) and len(x) == 2 and None not in x


def market_size_line(market: dict, lang: str = "en") -> str | None:
    """The single line to show when no TAM/SAM/SOM figure was sourced; None when at least one is known."""
    if any(_known(market.get(k)) for k in ("tam", "sam", "som")):
        return None
    return MARKET_UNKNOWN[_i(lang)]


def price_cell(competitor: dict, lang: str = "en") -> str:
    return competitor.get("price") or NO_PRICE[_i(lang)]


def exportable(rows: list) -> bool:
    """A table is shown (with its CSV download) only if it has at least one row; otherwise the page says
    'nothing to export yet' instead of offering an empty, zero-byte file."""
    return bool(rows) and all(isinstance(r, dict) and r for r in rows)


def nothing_to_export(lang: str = "en") -> str:
    return NOTHING[_i(lang)]
