"""Source registry (read-only here; admins change it through the admin API, and every change is logged).
Arabic or English (sidebar language; the layout flips right-to-left automatically)."""

import streamlit as st
from common import api, setup, ui_lang

L = ui_lang()
i = 1 if L == "ar" else 0
T = {
    "title": ("Sources", "المصادر"),
    "sub": ("The sources behind this research: what backed a claim, and what else the searches found.",
            "مصادر هذا البحث: ما دعم ادعاءً، وما وجده البحث أيضاً."),
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


R = {
    "r_head": ("Sources of this research", "مصادر هذا البحث"),
    "r_none": ("No research yet for the brief confirmed in this session. Confirm a brief, then run Discover.",
               "لا يوجد بحث بعد للموجز المؤكد في هذه الجلسة. أكّد موجزاً ثم شغّل الاكتشاف."),
    "used": ("Used as evidence ({n}): each backs at least one claim",
             "استُخدمت كدليل ({n}): كل منها يدعم ادعاءً واحداً على الأقل"),
    "found": ("Found during retrieval, not used ({n})", "وُجدت أثناء البحث ولم تُستخدم ({n})"),
    "claims": ("claims", "الادعاءات"), "title_c": ("title", "العنوان"), "via": ("found by", "وجدها"),
    "query": ("query", "الاستعلام"), "registry": ("Allowed source registry (where agents may look)",
                                                  "سجل المصادر المسموح بها (أين يمكن للوكلاء البحث)"),
}
T.update(R)
setup(t("title"), t("sub"), lang=L)


def research_sources() -> None:
    """Only this session's brief: URLs that back a claim, then every other URL the searches returned."""
    st.subheader(t("r_head"))
    brief = (st.session_state.get("brief") or {}).get("id")
    runs = [r for r in (api("GET", "/stages/runs", params={"brief_id": brief, "stage": "discover"}) if brief else [])
            if r["status"] != "failed" and (r.get("output") or {}).get("research", {}).get("trace")]
    if not runs:
        st.info(t("r_none"))
        return
    run = max(runs, key=lambda r: (r["brief_version"], r["created_at"]))
    used: dict[str, dict] = {}
    for c in api("GET", f"/stages/runs/{run['id']}/claims"):
        if c.get("url"):
            u = used.setdefault(c["url"], {"title": c.get("title") or "", "n": 0})
            u["n"] += 1
    found: dict[str, dict] = {}
    for e in run["output"]["research"]["trace"]:
        for url in e.get("sources") or ([e["url"]] if e.get("url") else []):
            if url and url not in used:
                found.setdefault(url, {"via": f"{e.get('agent', '')} · {e.get('api', '')}".strip(" ·"),
                                       "query": e.get("query") or ""})
    link = {t("url"): st.column_config.LinkColumn(t("url"))}
    st.markdown(f"**{t('used', n=len(used))}**")
    st.dataframe([{t("url"): u, t("title_c"): v["title"], t("claims"): v["n"]}
                  for u, v in sorted(used.items(), key=lambda kv: -kv[1]["n"])],
                 hide_index=True, width="stretch", column_config=link)
    st.markdown(f"**{t('found', n=len(found))}**")
    st.dataframe([{t("url"): u, t("via"): v["via"], t("query"): v["query"]} for u, v in found.items()],
                 hide_index=True, width="stretch", column_config=link)


try:
    research_sources()
    summary = api("GET", "/registry/summary")
except RuntimeError as e:
    st.error(t("down", e=e))
    st.stop()

reg = st.expander(t("registry"))
with reg:
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
