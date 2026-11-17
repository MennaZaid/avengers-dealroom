"""Model profiles for the Discover agents (extract, reasoning, judge), on top of the team's model settings.

By default every profile uses the shared settings from .env / docker-compose.yml (see llm/client.py):
LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_EXTRACT / _REASONING / _JUDGE, LLM_REASONING_EFFORT. The default model
is the local open-weight qwen3:4b-instruct served by the `ollama` service ($0). An unset profile falls back to
the extract model, as in client.model_for.

Optional per-profile endpoint (e.g. a judge from another free provider):
  LLM_<PROFILE>_BASE_URL, LLM_<PROFILE>_API_KEY, LLM_<PROFILE>_MODEL   (PROFILE = EXTRACT | REASONING | JUDGE)

The research critic needs a judge from a DIFFERENT model family; when LLM_MODEL_JUDGE is unset the judge is
the same family as the generator and the critic's model review is skipped (and says so).
Models are used only when LLM_MODE=live; otherwise every agent runs its rule-based path (CI, offline demo).
Keys are read at call time and never logged.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass

from venture_os.config import Settings
from venture_os.llm import client

DEFAULT_MODEL = "qwen3:4b-instruct"  # same default as docker-compose.yml
DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollama from the host


@dataclass(frozen=True)
class Profile:
    name: str
    base_url: str
    model: str
    api_key_env: str | None  # per-profile key env var NAME; None = the shared LLM_API_KEY setting
    family: str
    reasoning_effort: str = ""

    def chat_json(self, messages: list[dict], timeout: float | None = None) -> str:
        """One JSON-mode chat call. Returns the JSON text (reasoning blocks and fences stripped).
        Timeout: LLM_TIMEOUT seconds (default 900; a 4B model on a laptop CPU writes ~4 tokens/s)."""
        timeout = timeout or float(os.environ.get("LLM_TIMEOUT", "900"))
        mark = client.usage_mark()
        text = client.chat_json(messages, timeout=timeout, profile=self.name)  # type: ignore[arg-type]
        for c in client.usage_calls(mark):  # the model that actually answered (after any fallback)
            _USAGE.append({"profile": self.name, "model": c.model, "prompt_tokens": c.prompt_tokens,
                           "completion_tokens": c.completion_tokens})
        return text


_USAGE: list[dict] = []  # token counts per call for the run report (cost stays $0 on free/local models)


def usage() -> list[dict]:
    return list(_USAGE)


def _family(model: str) -> str:
    m = model.lower()
    for fam in ("qwen", "llama", "gemma", "gpt-oss", "mistral", "fanar", "allam", "phi", "deepseek"):
        if fam in m:
            return fam
    return m.split(":")[0]


def get_profile(name: str) -> Profile | None:
    """The profile, or None when models are off (LLM_MODE != live)."""
    s = Settings()
    if os.environ.get("LLM_MODE", s.llm_mode) != "live":
        return None
    p = name.upper()
    base = os.environ.get(f"LLM_{p}_BASE_URL")
    if base:  # optional dedicated endpoint for this profile
        model = os.environ.get(f"LLM_{p}_MODEL") or DEFAULT_MODEL
        return Profile(name, base, model, f"LLM_{p}_API_KEY", _family(model))
    model = client.model_for(name, s) or DEFAULT_MODEL  # type: ignore[arg-type]
    return Profile(name, s.llm_base_url or DEFAULT_BASE_URL, model, None, _family(model), s.llm_reasoning_effort)


def chat_fn(name: str) -> Callable[[list[dict]], str] | None:
    prof = get_profile(name)
    return prof.chat_json if prof else None


def parse_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
