"""OpenAI-compatible JSON chat call with model profiles and per-call usage tracking.

Default endpoint: the local Ollama service from docker-compose.yml (open-weight model, $0 per call).
Any OpenAI-compatible endpoint works through .env (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL_*).
Zero spend (decision D9): only local models or free tiers; LLM_PRICE_PER_1M_TOKENS stays 0 for those.

Profiles pick the model: extract (default), reasoning, validate, code, judge. An unset profile falls back to
the extract model, so one local model is enough to run everything.

Routing with fallback (each role on the model it is best at, and a demo never stops on one provider):
  1. the profile's own endpoint, when LLM_<PROFILE>_BASE_URL is set
     (LLM_<PROFILE>_API_KEY, LLM_<PROFILE>_MODEL, optional LLM_<PROFILE>_REASONING_EFFORT)
  2. the base endpoint: LLM_BASE_URL / LLM_API_KEY / the profile's model
  3. the local open-weight fallback: LLM_FALLBACK_BASE_URL (default: Ollama) / LLM_FALLBACK_MODEL (qwen3:4b-instruct)
An endpoint that errors, times out or rejects the request is skipped; if all fail, the caller's rule-based path
runs. The decision log records the model that actually answered.

Every call appends a `CallUsage` (tokens, seconds, cost) to an in-process ledger, so a pipeline run
can report its own cost:  mark = usage_mark(); ...run...; usage_summary(since=mark)
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from typing import Literal

import httpx

from venture_os.config import Settings

Profile = Literal["extract", "reasoning", "validate", "code", "judge"]

FALLBACK_MODEL = "qwen3:4b-instruct"
FALLBACK_BASE_URL = "http://localhost:11434/v1"  # Ollama from the host; docker-compose sets the container address


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
        "validate": s.llm_model_reasoning,
        "code": s.llm_model_code,
        "judge": s.llm_model_judge,
    }
    name = by_profile.get(profile)
    if not name or looks_like_key(name):
        name = s.llm_model_extract
    return "" if looks_like_key(name) else name


def looks_like_key(value: str | None) -> bool:
    """A secret typed into a model-name field must never be sent as a model or written to the decision log."""
    v = (value or "").strip()
    return v.startswith(("sk-", "gsk_", "sk_", "xai-", "AIza")) or (len(v) > 60 and " " not in v and "/" not in v)


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    api_key: str
    model: str
    reasoning_effort: str = ""


def endpoints(profile: str = "extract", model: str | None = None, s: Settings | None = None) -> list[Endpoint]:
    """Where a profile's calls go, in order: its own endpoint, the base endpoint, the local fallback."""
    s = s or Settings()
    env = os.environ.get
    p = profile.upper()
    out: list[Endpoint] = []
    if env(f"LLM_{p}_BASE_URL"):
        out.append(Endpoint(env(f"LLM_{p}_BASE_URL", ""), env(f"LLM_{p}_API_KEY", ""),
                            model or env(f"LLM_{p}_MODEL") or model_for(profile, s),  # type: ignore[arg-type]
                            env(f"LLM_{p}_REASONING_EFFORT", "")))
    if s.llm_base_url:
        out.append(Endpoint(s.llm_base_url, s.llm_api_key, model or model_for(profile, s),  # type: ignore[arg-type]
                            s.llm_reasoning_effort))
    out.append(Endpoint(env("LLM_FALLBACK_BASE_URL") or FALLBACK_BASE_URL, env("LLM_FALLBACK_API_KEY", "ollama"),
                        env("LLM_FALLBACK_MODEL") or FALLBACK_MODEL, "none"))
    seen, unique = set(), []
    for e in out:
        if e.model and not looks_like_key(e.model) and (e.base_url, e.model) not in seen:
            seen.add((e.base_url, e.model))
            unique.append(e)
    return unique


def _post(e: Endpoint, messages: list[dict], timeout: float) -> httpx.Response:
    payload = {"model": e.model, "messages": messages, "response_format": {"type": "json_object"}, "temperature": 0}
    if e.reasoning_effort:
        payload["reasoning_effort"] = e.reasoning_effort
    url = e.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {e.api_key}"} if e.api_key else {}
    r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code == 400 and "reasoning_effort" in payload:  # some providers reject the parameter
        payload.pop("reasoning_effort")
        r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code == 429:  # free-tier rate limit: wait the few seconds asked for, retry once, else fall back
        wait = retry_wait(r.headers)
        if wait is not None and wait <= MAX_RATE_LIMIT_WAIT:
            time.sleep(wait)
            r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    return r


MAX_RATE_LIMIT_WAIT = 20.0


def _duration(text: str) -> float | None:
    """'7.66s', '1m2s', '450ms', '12' -> seconds."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    parts = re.findall(r"([\d.]+)(ms|h|m|s)", text)
    if not parts or "".join(n + u for n, u in parts) != text:
        return None
    return sum(float(n) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[u] for n, u in parts)


def retry_wait(headers) -> float | None:
    """Seconds a 429 asks us to wait: `retry-after`, else Groq's `x-ratelimit-reset-tokens` / `-requests`."""
    for name in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        wait = _duration(headers.get(name, ""))
        if wait is not None:
            return wait
    return None


def chat_json(
    messages: list[dict],
    model: str | None = None,
    timeout: float | None = None,
    profile: Profile = "extract",
) -> str:
    """Send a chat request in JSON mode and return the cleaned JSON text. Records usage.
    Tries the profile's endpoints in order (see the module docstring); raises the last error if all fail."""
    s = Settings()
    error: Exception | None = None
    for e in endpoints(profile, model, s):
        started = time.monotonic()
        try:
            body = _post(e, messages, timeout or s.llm_chat_timeout).json()
            text = body["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            error = exc
            continue
        entry = record_usage(profile, e.model, token_usage(body), time.monotonic() - started, s)
        log_model_call(entry)
        return clean_json_text(text)
    raise error or RuntimeError("no model endpoint configured")


def token_usage(body: dict) -> dict:
    """Token counts from an OpenAI-compatible "usage" block, or Ollama's native prompt_eval_count/eval_count."""
    usage = body.get("usage") or {}
    return {"prompt_tokens": int(usage.get("prompt_tokens") or body.get("prompt_eval_count") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or body.get("eval_count") or 0)}


def log_model_call(entry: CallUsage) -> None:
    """One decision_log.json entry per model call: the 7 required keys plus token counts (never the prompt)."""
    from venture_os.decision_log import log_action
    log_action("llm_client", "model_call", sources=[], model=entry.model, cost=entry.cost_usd, approved_by=None,
               profile=entry.profile, prompt_tokens=entry.prompt_tokens, completion_tokens=entry.completion_tokens,
               seconds=entry.seconds)


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
