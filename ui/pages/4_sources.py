"""Source registry (read-only here; admins change it through the admin API, and every change is logged).
Arabic or English (sidebar language; the layout flips right-to-left automatically)."""

import streamlit as st
from common import api, setup, ui_lang

L = ui_lang()
i = 1 if L == "ar" else 0
T = {
    "title": ("Sources", "المصادر"),
    "sub": ("Where the agents are allowed to look. Tier A official or peer-reviewed, B established, C crowd/news.",
            "أين يُسمح للوكلاء بالبحث. الفئة A رسمية أو محكّمة، B مؤسسات معروفة، C مجتمعات وأخبار."),
    "down": ("Registry unavailable: {e}", "سجل المصادر غير متاح: {e}"),
    "tier_a": ("Tier A", "الفئة A"), "tier_b": ("Tier B", "الفئة B"), "tier_c": ("Tier C", "الفئة C"),
    "provisional": ("Provisional", "مؤقتة"), "corpus": ("Corpus items", "مراجع المنهجية"),
    "country": ("Country code (also shows global sources)", "رمز الدولة (تظهر المصادر العالمية أيضاً)"),
    "tier": ("Tier", "الفئة"), "use": ("Use", "الاستخدام"), "all": ("All", "الكل"),
    "count": ("{n} sources · URLs and licences are unverified until marked verified",
              "{n} مصدراً · الروابط والتراخيص غير مُتحقق منها حتى تُوسم بأنها مُتحقق منها"),
    "id": ("id", "المعرّف"), "source": ("source", "المصدر"), "url": ("url", "الرابط"),
    "max_age": ("max age (months)", "أقصى عمر (بالأشهر)"), "verified": ("verified", "مُتحقق منه"),
}
USES = {"market": ("market", "السوق"), "analogy": ("analogy", "تشبيه"), "ethics": ("ethics", "الأخلاقيات"),
        "legal": ("legal", "قانوني")}


def t(key, **kw):
    v = T[key][i]
    return v.format(**kw) if kw else v


setup(t("title"), t("sub"), lang=L)

try:
    summary = api("GET", "/registry/summary")
except RuntimeError as e:
    st.error(t("down", e=e))
    st.stop()

tiers = {r["tier"]: r["n"] for r in summary["sources_by_tier"]}
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(t("tier_a"), tiers.get("A", 0))
c2.metric(t("tier_b"), tiers.get("B", 0))
c3.metric(t("tier_c"), tiers.get("C", 0))
c4.metric(t("provisional"), summary["provisional_sources"])
c5.metric(t("corpus"), summary["corpus_items"])

f1, f2, f3 = st.columns(3)
country = f1.text_input(t("country"), value="", max_chars=2).upper()
tier = f2.selectbox(t("tier"), ["All", "A", "B", "C"], format_func=lambda x: t("all") if x == "All" else x)
use = f3.selectbox(t("use"), ["All", *USES], format_func=lambda x: t("all") if x == "All" else USES[x][i])
params = {k: v for k, v in {"country": country or None, "tier": None if tier == "All" else tier,
                            "use": None if use == "All" else use}.items() if v}
rows = api("GET", "/registry/sources", params=params)
st.caption(t("count", n=len(rows)))
st.dataframe([{t("id"): r["id"], t("source"): r["source_name"], t("tier"): r["tier"], t("use"): r["use"],
               t("url"): r["url"], t("max_age"): r["max_age_months"], t("verified"): r["verified"],
               t("provisional"): r["provisional"]} for r in rows],
             hide_index=True, width="stretch",
             column_config={t("url"): st.column_config.LinkColumn(t("url"))})
