"""The research critic's judge gets today's date; a model finding that calls a past date "in the future" is
dropped and logged (replay mode: the judge here is a scripted stand-in, no live model)."""

import json
import os
from datetime import date
from pathlib import Path

from venture_os.agents.research_critic import calls_past_date_future, review
from venture_os.agents.schemas import Claim

TODAY = date(2026, 11, 17)


def test_past_dates_called_future_are_detected():
    assert calls_past_date_future("The source dated 2024-12-31 is in the future.", TODAY)
    assert calls_past_date_future("C3 is future-dated (2025).", TODAY)
    assert not calls_past_date_future("The launch on 2027-03-01 is in the future.", TODAY)
    assert not calls_past_date_future("C3 from 2024-12-31 is stale.", TODAY)


def test_judge_gets_today_and_wrong_findings_are_dropped_and_logged():
    seen = []

    def judge(messages):
        seen.append(json.loads(messages[1]["content"].removeprefix("<untrusted>").removesuffix("</untrusted>")))
        return json.dumps({"findings": [
            {"detail": "C1 (2024-12-31) is in the future, so it cannot be used.", "claim_ids": ["C1"]},
            {"detail": "C1 overclaims: the quote does not mention prices.", "claim_ids": ["C1"]}],
            "summary": "weak evidence"})

    c = Claim(id="C1", type="fact", topic="pain", text="t", quote="q", url="https://example.org/a",
              published_at="2024-12-31", retrieved_at="2026-11-17T00:00:00")
    r = review([c], [], judge, "judge-x", "llama", "qwen", today=TODAY)
    assert seen[0]["today"] == "2026-11-17"
    details = [f.detail for f in r.findings if f.kind == "model"]
    assert details == ["C1 overclaims: the quote does not mention prices."]      # real findings stay
    assert r.dropped == ["C1 (2024-12-31) is in the future, so it cannot be used."]
    log = json.loads(Path(os.environ["DECISION_LOG_PATH"]).read_text(encoding="utf-8"))
    assert any(e["action"] == "drop_model_finding" and "2024-12-31" in e["finding"] for e in log)
