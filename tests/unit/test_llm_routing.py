"""Model routing: each profile tries its own endpoint, then the base endpoint, then the local fallback."""

import httpx
import pytest

from venture_os.llm import client


@pytest.fixture
def env(monkeypatch):
    for k, v in {"LLM_MODE": "live", "LLM_BASE_URL": "https://base.example/v1", "LLM_API_KEY": "kb",
                 "LLM_MODEL_EXTRACT": "base-model", "LLM_MODEL_REASONING": "", "LLM_REASONING_EFFORT": "",
                 "LLM_VALIDATE_BASE_URL": "https://validate.example/v1", "LLM_VALIDATE_API_KEY": "kv",
                 "LLM_VALIDATE_MODEL": "gpt-oss-120b", "LLM_FALLBACK_BASE_URL": "http://local/v1"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(client, "log_model_call", lambda entry: None)
    return monkeypatch


def _fake(monkeypatch, failing: set[str]):
    calls = []

    def post(url, headers=None, json=None, timeout=None):
        calls.append((url, json["model"], headers.get("Authorization")))
        if any(url.startswith(f) for f in failing):
            return httpx.Response(503, request=httpx.Request("POST", url))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}],
                                         "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(client.httpx, "post", post)
    return calls


def test_order_is_own_endpoint_then_base_then_local(env):
    eps = client.endpoints("validate")
    assert [e.base_url for e in eps] == ["https://validate.example/v1", "https://base.example/v1", "http://local/v1"]
    assert eps[0].model == "gpt-oss-120b" and eps[-1].model == client.FALLBACK_MODEL
    assert [e.base_url for e in client.endpoints("extract")] == ["https://base.example/v1", "http://local/v1"]


def test_profile_uses_its_own_provider_and_key(env):
    calls = _fake(env, failing=set())
    assert client.chat_json([{"role": "user", "content": "x"}], profile="validate") == '{"ok": true}'
    assert calls == [("https://validate.example/v1/chat/completions", "gpt-oss-120b", "Bearer kv")]


def test_failed_provider_falls_back_and_logs_the_model_that_answered(env):
    calls = _fake(env, failing={"https://validate.example", "https://base.example"})
    mark = client.usage_mark()
    client.chat_json([{"role": "user", "content": "x"}], profile="validate")
    assert [c[0].split("/v1")[0] for c in calls] == ["https://validate.example", "https://base.example", "http://local"]
    assert [c.model for c in client.usage_calls(mark)] == [client.FALLBACK_MODEL]


def test_a_key_in_a_model_field_is_never_used_as_a_model(env):
    env.setenv("LLM_MODEL_REASONING", "sk-proj-" + "x" * 80)
    assert all(not e.model.startswith("sk-") for e in client.endpoints("reasoning"))
    assert client.model_for("reasoning") == "base-model"


def test_all_failing_raises_so_the_rule_based_path_runs(env):
    _fake(env, failing={"https://", "http://"})
    with pytest.raises(httpx.HTTPError):
        client.chat_json([{"role": "user", "content": "x"}], profile="reasoning")
