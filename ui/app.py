"""Venture OS UI. Run the API first, then:  streamlit run ui/app.py -- --api http://localhost:8010"""

import streamlit as st
from common import language_picker, ui_lang

st.set_page_config(page_title="Venture OS", page_icon="🧭", layout="wide")

NAMES = {
    "brief": ("Founder brief", "موجز المؤسس"),
    "pipeline": ("Pipeline", "المراحل"),
    "log": ("Decision log & outputs", "سجل القرارات والمخرجات"),
    "sources": ("Sources", "المصادر"),
}
i = 1 if ui_lang() == "ar" else 0
pages = [
    st.Page("pages/1_onboarding.py", title=NAMES["brief"][i], icon="💬", default=True),
    st.Page("pages/2_pipeline.py", title=NAMES["pipeline"][i], icon="🧭"),
    st.Page("pages/3_decision_log.py", title=NAMES["log"][i], icon="📜"),
    st.Page("pages/4_sources.py", title=NAMES["sources"][i], icon="📚"),
]
language_picker()
st.navigation(pages, position="sidebar").run()
