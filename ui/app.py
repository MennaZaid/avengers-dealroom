"""Venture OS UI. Run the API first, then:  streamlit run ui/app.py -- --api http://localhost:8010"""

import streamlit as st

st.set_page_config(page_title="Venture OS", page_icon="🧭", layout="wide")

pages = [
    st.Page("pages/1_onboarding.py", title="Founder brief", icon="💬", default=True),
    st.Page("pages/2_pipeline.py", title="Pipeline", icon="🧭"),
    st.Page("pages/3_decision_log.py", title="Decision log & outputs", icon="📜"),
    st.Page("pages/4_sources.py", title="Sources", icon="📚"),
]
st.navigation(pages, position="sidebar").run()
