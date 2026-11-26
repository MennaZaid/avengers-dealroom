"""Runtime settings from the environment / .env (model endpoints and the local search engine)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_reasoning: str = ""
    llm_model_extract: str = ""
    llm_model_code: str = ""
    llm_model_judge: str = ""
    llm_reasoning_effort: str = ""
    llm_price_per_1m_tokens: float = 0.0   # 0 for free tiers
    llm_chat_timeout: float = 120.0
    llm_mode: str = "live"
    searxng_url: str = "http://localhost:8080"
