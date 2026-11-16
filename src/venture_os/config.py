"""Runtime settings loaded from environment / .env."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_mode: Literal["replay", "live"] = "replay"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_reasoning: str = ""
    llm_model_extract: str = ""
    colab_llm_base_url: str = ""
    colab_llm_api_key: str = ""
    database_url: str = "postgresql://venture:venture@localhost:5432/venture_os"
    searxng_url: str = "http://localhost:8080"
    admin_token: str = ""  # empty = admin routes disabled
