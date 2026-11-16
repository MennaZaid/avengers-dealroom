"""Shared UI pieces: API client, theme (CSS), header, six-phase bar, cards and chips, right-to-left support.

All founder-provided text is HTML-escaped before it is placed in custom HTML.
"""

from __future__ import annotations

import html
import os
import sys

import httpx
import streamlit as st

# API address: `streamlit run ui/app.py -- --api http://localhost:8010`, or the API_URL env var.
_args = sys.argv[1:]
API = _args[_args.index("--api") + 1] if "--api" in _args else os.environ.get("API_URL", "http://localhost:8000")

PHASES = [
    ("0", "Brief", "موجز المؤسس"),
    ("1", "Discover", "الاكتشاف"),
    ("2", "Validate", "التحقق"),
    ("3", "Build", "البناء"),
    ("4", "Commercial", "الإعداد التجاري"),
    ("5", "Sell & deliver", "البيع والتسليم"),
    ("6", "Operate", "التشغيل والتعلّم"),
]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stChatMessage, button, input, textarea {
  font-family: 'Cairo', system-ui, sans-serif !important;
}
:root { --vos-ink:#1C2321; --vos-quiet:#5B6661; --vos-line:#DCE1DA; --vos-card:#FFFFFF; --vos-accent:#0F766E;
        --vos-accent-soft:#E3F1EE; --vos-warn:#B45309; --vos-warn-soft:#FDF1E1; --vos-bad:#B42318;
        --vos-bad-soft:#FDECEA; --vos-doc:#3B5BAA; --vos-doc-soft:#E8EDF8; }
.block-container { padding-top: 1.2rem; max-width: 1280px; }
.vos-header { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 18px;
  border-radius:14px; background:linear-gradient(120deg,#0F766E,#134E4A); color:#fff; margin-bottom:14px; }
.vos-header h1 { font-size:1.35rem; margin:0; color:#fff; font-weight:700; }
.vos-header .sub { font-size:.9rem; opacity:.85; }
.vos-badge { font-size:.75rem; padding:3px 10px; border-radius:999px; background:rgba(255,255,255,.18); }
.vos-phases { display:flex; gap:6px; margin:0 0 16px; flex-wrap:wrap; }
.vos-phase { flex:1 1 110px; padding:8px 10px; border-radius:10px; border:1px solid var(--vos-line);
  background:var(--vos-card); font-size:.82rem; color:var(--vos-quiet); line-height:1.25; }
.vos-phase b { display:block; color:var(--vos-ink); font-size:.86rem; }
.vos-phase.done { border-color:var(--vos-accent); background:var(--vos-accent-soft); }
.vos-phase.now { border:2px solid var(--vos-accent); box-shadow:0 1px 0 rgba(0,0,0,.04); }
.vos-phase .st { font-size:.7rem; text-transform:uppercase; letter-spacing:.04em; }
.vos-card { background:var(--vos-card); border:1px solid var(--vos-line); border-radius:12px; padding:10px 12px;
  margin-bottom:8px; }
.vos-card .lbl { font-size:.78rem; color:var(--vos-quiet); display:flex; justify-content:space-between; gap:8px; }
.vos-card .val { font-size:.95rem; color:var(--vos-ink); margin-top:2px; word-wrap:break-word; }
.vos-card .val.empty { color:#9AA39E; font-style:italic; }
.vos-chip { display:inline-block; font-size:.7rem; padding:1px 8px; border-radius:999px; white-space:nowrap; }
.chip-answered { background:var(--vos-accent-soft); color:var(--vos-accent); }
.chip-from_document { background:var(--vos-doc-soft); color:var(--vos-doc); }
.chip-inferred { background:var(--vos-warn-soft); color:var(--vos-warn); }
.chip-unknown { background:#EEF0ED; color:var(--vos-quiet); }
.chip-stub { background:var(--vos-warn-soft); color:var(--vos-warn); font-weight:600; }
.chip-tag { background:#EEF0ED; color:var(--vos-ink); margin:0 4px 4px 0; }
.vos-section { font-weight:700; font-size:.95rem; margin:6px 0 6px; color:var(--vos-ink); }
[data-testid="stChatMessage"] { border-radius:12px; }
/* Each paragraph takes its direction from its own first letters: Arabic right-to-left, English left-to-right. */
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li {
  unicode-bidi: plaintext; text-align: start; }
</style>
"""

RTL_CSS = """
<style>
[data-testid="stChatInput"] textarea { direction: rtl; text-align: right; }
</style>
"""


def esc(text) -> str:
    return html.escape(str(text or ""))


def setup(title: str, subtitle: str = "", active_phase: int | None = None, lang: str = "en") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if lang == "ar":
        st.markdown(RTL_CSS, unsafe_allow_html=True)
    model = st.session_state.get("model_label", "")
    st.markdown(
        f'<div class="vos-header"><div><h1>🧭 {esc(title)}</h1><div class="sub">{esc(subtitle)}</div></div>'
        f'<span class="vos-badge">{esc(model) or "Venture OS"}</span></div>', unsafe_allow_html=True)
    if active_phase is not None:
        phase_bar(active_phase, lang)


def phase_bar(active: int, lang: str = "en", status: dict[int, str] | None = None) -> None:
    """Six phases plus the brief. `status` maps phase number to a short label (e.g. 'STUBBED')."""
    status = status or {}
    cells = []
    for num, en, ar in PHASES:
        n = int(num)
        cls = "done" if n < active else "now" if n == active else ""
        name = ar if lang == "ar" else en
        st_label = status.get(n, "")
        cells.append(f'<div class="vos-phase {cls}" dir="{"rtl" if lang == "ar" else "ltr"}"><span class="st">'
                     f'{"Phase" if lang != "ar" else "مرحلة"} {num}</span><b>{esc(name)}</b>{esc(st_label)}</div>')
    st.markdown('<div class="vos-phases">' + "".join(cells) + "</div>", unsafe_allow_html=True)


def chip(text: str, kind: str) -> str:
    return f'<span class="vos-chip chip-{esc(kind)}">{esc(text)}</span>'


def card(label: str, value: str | None, chip_html: str = "", lang: str = "en") -> str:
    d = "rtl" if lang == "ar" else "ltr"
    val = f'<div class="val">{esc(value)}</div>' if value else f'<div class="val empty">{"—"}</div>'
    return f'<div class="vos-card" dir="{d}"><div class="lbl"><span>{esc(label)}</span>{chip_html}</div>{val}</div>'


def api(method: str, path: str, **kw) -> dict | list:
    r = httpx.request(method, f"{API}{path}", timeout=180, **kw)
    if r.status_code >= 400:
        detail = r.json().get("detail", r.text) if "json" in r.headers.get("content-type", "") else r.text
        raise RuntimeError(detail)
    return r.json()
