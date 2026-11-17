"""OpenAI-compatible JSON chat call with model profiles and per-call usage tracking.

Default endpoint: the local Ollama service from docker-compose.yml (open-weight model, $0 per call).
Any OpenAI-compatible endpoint works through .env (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL_*).
Zero spend (decision D9): only local models or free tiers; LLM_PRICE_PER_1M_TOKENS stays 0 for those.

Profiles pick the model: extract (default), reasoning, code, judge. An unset profile falls back to
the extract model, so one local model is enough to run everything.

Every call appends a `CallUsage` (tokens, seconds, cost) to an in-process ledger, so a pipeline run
can report its own cost:  mark = usage_mark(); ...run...; usage_summary(since=mark)
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Literal

import httpx

from venture_os.config import Settings

Profile = Literal["extract", "reasoning", "code", "judge"]


@dataclass(frozen=True)
class CallUsage:
    profile: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


_LEDGER: list[CallUsage] = []
_LOCK = threading.Lock()


def live_enabled(s: Settings | None = None) -> bool:
    s = s or Settings()
    return s.llm_mode == "live" and bool(s.llm_base_url) and bool(s.llm_model_extract)


def model_for(profile: Profile = "extract", s: Settings | None = None) -> str:
    """Model name for a profile; falls back to the extract model when the profile is not configured."""
    s = s or Settings()
    by_profile = {
        "extract": s.llm_model_extract,
        "reasoning": s.llm_model_reasoning,
        "code": s.llm_model_code,
        "judge": s.llm_model_judge,
    }
    return by_profile.get(profile) or s.llm_model_extract


def chat_json(
    messages: list[dict],
    model: str | None = None,
    timeout: float = 300.0,
    profile: Profile = "extract",
) -> str:
    """Send a chat request in JSON mode and return the cleaned JSON text. Records usage."""
    s = Settings()
    model = model or model_for(profile, s)
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    if s.llm_reasoning_effort:
        payload["reasoning_effort"] = s.llm_reasoning_effort
    started = time.monotonic()
    r = httpx.post(
        s.llm_base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {s.llm_api_key}"},
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    record_usage(profile, model, body.get("usage") or {}, time.monotonic() - started, s)
    return clean_json_text(body["choices"][0]["message"]["content"] or "")


def record_usage(profile: str, model: str, usage: dict, seconds: float, s: Settings | None = None) -> CallUsage:
    s = s or Settings()
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    cost = round((prompt + completion) * s.llm_price_per_1m_tokens / 1_000_000, 6)
    entry = CallUsage(profile, model, prompt, completion, round(seconds, 2), cost)
    with _LOCK:
        _LEDGER.append(entry)
    return entry


def usage_mark() -> int:
    """Position in the ledger; pass it to usage_summary(since=...) to measure one run."""
    with _LOCK:
        return len(_LEDGER)


def usage_calls(since: int = 0) -> list[CallUsage]:
    with _LOCK:
        return list(_LEDGER[since:])


def usage_summary(since: int = 0) -> dict:
    calls = usage_calls(since)
    return {
        "calls": len(calls),
        "prompt_tokens": sum(c.prompt_tokens for c in calls),
        "completion_tokens": sum(c.completion_tokens for c in calls),
        "total_tokens": sum(c.total_tokens for c in calls),
        "seconds": round(sum(c.seconds for c in calls), 2),
        "cost_usd": round(sum(c.cost_usd for c in calls), 6),
        "models": sorted({c.model for c in calls}),
        "per_call": [asdict(c) for c in calls],
    }


def clean_json_text(text: str) -> str:
    """Strip reasoning blocks and code fences some models wrap around JSON."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()
