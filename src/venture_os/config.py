"""Runtime settings loaded from environment / .env."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # live = call the models; none = rule-based only, no model at all (replay is the same, kept for CI and old .env)
    llm_mode: Literal["none", "replay", "live"] = "replay"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_reasoning: str = ""
    llm_model_extract: str = ""
    llm_model_code: str = ""
    llm_model_judge: str = ""
    # Sent as `reasoning_effort` only when set. "none" turns off qwen3 thinking on Ollama (much faster on CPU).
    llm_reasoning_effort: str = ""
    # USD per 1M tokens for cost-per-run reporting. 0 for local models and free tiers (zero spend, D9).
    llm_price_per_1m_tokens: float = 0.0
    # Seconds before a chat_json call gives up and the caller uses its rule-based fallback (LLM_CHAT_TIMEOUT).
    # Keeps the first founder message from waiting minutes while the local model is still loading.
    llm_chat_timeout: float = 120.0
    colab_llm_base_url: str = ""
    colab_llm_api_key: str = ""
    database_url: str = "postgresql://venture:venture@localhost:5432/venture_os"
    searxng_url: str = "http://localhost:8080"
    admin_token: str = ""  # empty = admin routes disabled
