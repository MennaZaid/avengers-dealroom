"""LLM client: profiles fall back to the extract model; every call is metered (no network)."""

import httpx

from venture_os.config import Settings
from venture_os.llm import client


def _settings(**kw) -> Settings:
    base = {"llm_mode": "live", "llm_base_url": "http://ollama:11434/v1", "llm_model_extract": "qwen3:4b"}
    return Settings(_env_file=None, **{**base, **kw})


def test_profile_falls_back_to_extract_model():
    s = _settings(llm_model_judge="gpt-oss:20b")
    assert client.model_for("reasoning", s) == "qwen3:4b"
    assert client.model_for("judge", s) == "gpt-oss:20b"


def test_chat_json_records_usage_and_zero_cost(monkeypatch):
    monkeypatch.setattr(client, "Settings", lambda: _settings())

    def fake_post(url, headers, json, timeout):
        assert url == "http://ollama:11434/v1/chat/completions"
        assert json["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '<think>x</think>```json\n{"ok": true}\n```'}}],
                  "usage": {"prompt_tokens": 120, "completion_tokens": 30}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(client.httpx, "post", fake_post)
    mark = client.usage_mark()
    assert client.chat_json([{"role": "user", "content": "hi"}]) == '{"ok": true}'
    summary = client.usage_summary(since=mark)
    assert summary["calls"] == 1
    assert summary["total_tokens"] == 150
    assert summary["cost_usd"] == 0
    assert summary["models"] == ["qwen3:4b"]


def test_price_setting_gives_a_cost():
    entry = client.record_usage("extract", "m", {"prompt_tokens": 500_000, "completion_tokens": 500_000}, 1.0,
                                _settings(llm_price_per_1m_tokens=0.2))
    assert entry.cost_usd == 0.2
