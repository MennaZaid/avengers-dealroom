"""Source registry (read-only here; admins change it through the admin API, and every change is logged)."""

import streamlit as st
from common import api, setup

setup("Sources", "Where the agents are allowed to look. Tier A official or peer-reviewed, B established, C crowd/news.")

try:
    summary = api("GET", "/registry/summary")
except RuntimeError as e:
    st.error(f"Registry unavailable: {e}")
    st.stop()

tiers = {r["tier"]: r["n"] for r in summary["sources_by_tier"]}
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Tier A", tiers.get("A", 0))
c2.metric("Tier B", tiers.get("B", 0))
c3.metric("Tier C", tiers.get("C", 0))
c4.metric("Provisional", summary["provisional_sources"])
c5.metric("Corpus items", summary["corpus_items"])

brief_country = ""
f1, f2, f3 = st.columns(3)
country = f1.text_input("Country code (also shows global sources)", value=brief_country, max_chars=2).upper()
tier = f2.selectbox("Tier", ["All", "A", "B", "C"])
use = f3.selectbox("Use", ["All", "market", "analogy", "ethics", "legal"])
params = {k: v for k, v in {"country": country or None, "tier": None if tier == "All" else tier,
                            "use": None if use == "All" else use}.items() if v}
rows = api("GET", "/registry/sources", params=params)
st.caption(f"{len(rows)} sources · URLs and licences are unverified until marked verified")
st.dataframe([{"id": r["id"], "source": r["source_name"], "tier": r["tier"], "use": r["use"], "url": r["url"],
               "max age (months)": r["max_age_months"], "verified": r["verified"],
               "provisional": r["provisional"]} for r in rows],
             hide_index=True, width="stretch",
             column_config={"url": st.column_config.LinkColumn("url")})
