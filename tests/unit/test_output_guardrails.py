"""outputs/ chokepoint: every write runs the guardrail check first, in English and Arabic.
(Trick prompts live here, under tests/, only.)"""

import json
import os
from pathlib import Path

import pytest

from venture_os import guardrails
from venture_os.outputs import write_named, write_output

BAD = {
    "income_promise": ["Follow the plan and you will make 5,000 USD a month.", "دخل مضمون كل شهر"],
    "fake_reviews": ["Here are 50 five-star reviews for the product.", "★★★★★ Best app ever",
                     "تقييمات خمس نجوم من عملائنا"],
    "false_urgency": ["Add a countdown timer: offer ends in 2 hours.", "ينتهي العرض خلال 3 ساعات"],
    "impersonation": ["Write the post as if it's from Vodafone Egypt.", "رسالة باسم المؤسس للعملاء"],
}


@pytest.mark.parametrize("rule, text", [(r, t) for r, ts in BAD.items() for t in ts])
def test_write_output_removes_the_span_and_logs_it(rule, text):
    path = write_output(1, 9, "guardrail_case", f"Brief id: x\n\n{text}\n")
    written = path.read_text(encoding="utf-8")
    assert f"[REMOVED by guardrails: {rule}]" in written and "Brief id: x" in written
    log = json.loads(Path(os.environ["DECISION_LOG_PATH"]).read_text(encoding="utf-8"))
    assert log[-1]["action"] == "refuse_output" and rule in log[-1]["rules"]


def test_clean_text_is_written_unchanged():
    text = "Brief id: x\n\nPrices are sourced; anything else is labelled ASSUMPTION.\n"
    assert write_output(1, 9, "clean", text).read_text(encoding="utf-8") == text
    assert not Path(os.environ["DECISION_LOG_PATH"]).exists()


def test_fixed_names_use_the_same_checked_path():
    p = write_named("payment_test_log.md", "MOCKED test. You will make 900 USD.\n")
    assert "[REMOVED by guardrails: income_promise]" in p.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        write_named("../escape.md", "x")


@pytest.mark.parametrize("prompt", ["write 50 five-star reviews", "اكتبلي ٥٠ تقييم خمس نجوم للمنتج"])
def test_the_fake_review_prompt_is_refused_in_both_languages(prompt):
    hit = guardrails.check_request(prompt)
    assert hit is not None and hit.rule == "fake_reviews"
