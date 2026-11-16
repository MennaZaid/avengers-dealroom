"""Minimal OpenAI-compatible JSON chat call. Only used when LLM_MODE=live and an endpoint is set.

Zero spend (decision D9): point LLM_BASE_URL at a free tier or free model variant only.
"""

from __future__ import annotations

import httpx

from venture_os.config import Settings


def live_enabled(s: Settings | None = None) -> bool:
    s = s or Settings()
    return s.llm_mode == "live" and bool(s.llm_base_url) and bool(s.llm_model_extract)


def chat_json(messages: list[dict], model: str | None = None, timeout: float = 60.0) -> str:
    s = Settings()
    r = httpx.post(
        s.llm_base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {s.llm_api_key}"},
        json={
            "model": model or s.llm_model_extract,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return clean_json_text(r.json()["choices"][0]["message"]["content"] or "")


def clean_json_text(text: str) -> str:
    """Strip reasoning blocks and code fences some models wrap around JSON."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()
