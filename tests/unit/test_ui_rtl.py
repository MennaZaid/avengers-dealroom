"""Arabic right-to-left helpers in ui/common.py (no API or browser needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "ui"))

import common


def test_arabic_card_is_rtl_and_its_value_keeps_its_own_direction():
    html = common.card("نموذج العمل", "commission of 15% per booking", "", "ar")
    assert 'class="vos-card" dir="rtl"' in html and 'class="val" dir="auto"' in html


def test_english_card_is_ltr():
    assert 'class="vos-card" dir="ltr"' in common.card("business model", "subscription", "", "en")


def test_founder_text_in_cards_is_escaped():
    assert "<script>" not in common.card("x", "<script>alert(1)</script>", "", "ar")


def test_rtl_css_flips_the_page_but_keeps_code_and_tables_ltr():
    css = common.RTL_CSS
    assert "direction: rtl" in css and "unicode-bidi: plaintext" in css
    assert '[data-testid="stDataFrame"]' in css and "direction: ltr" in css


def test_chat_input_takes_direction_from_what_is_typed():
    assert '[data-testid="stChatInput"] textarea { unicode-bidi: plaintext' in common.CSS
