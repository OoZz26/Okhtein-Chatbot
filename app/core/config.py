"""Typed application settings, loaded from environment variables / `.env`.

This is the ONLY place that reads the environment. Everything else receives a `Settings`
object (or a value from it), which keeps the rest of the code easy to test.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Store ---
    store_url: str = "https://eg.okhtein.com"
    store_currency: str = "EGP"
    products_path: str = "data/products.json"
    categories_path: str = "data/categories.json"
    knowledge_path: str = "data/knowledge.md"

    # --- LLM: OpenAI primary, OpenRouter fallback ---
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.5-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_timeout_seconds: float = 45.0
    llm_provider_order: str = "openai,openrouter"
    llm_max_retries: int = 2
    llm_retry_base_delay_seconds: float = 0.5
    max_tool_rounds: int = 5
    search_result_limit: int = 5
    prompt_version: str = "v2"
    eval_judge_model: str = "gpt-5-mini"

    # --- Embeddings ---
    embedding_model: str = "text-embedding-3-small"
    embeddings_path: str = "data/embeddings.npy"

    # --- Redis (short-term memory) ---
    redis_host: str = "localhost"
    redis_port: int = 6379

    # --- Postgres (long-term memory) ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "okhtein"
    postgres_password: str = "okhtein"
    postgres_db: str = "okhtein"

    # --- WAHA (WhatsApp gateway) ---
    waha_url: str = "http://localhost:3000"
    waha_api_key: str = ""
    waha_session: str = "default"
    waha_webhook_url: str = "http://host.docker.internal:8000/webhook"
    waha_webhook_hmac_key: str = ""
    waha_timeout_seconds: float = 15.0

    # --- Bot behaviour ---
    session_ttl_seconds: int = 24 * 60 * 60
    history_limit: int = Field(default=20, description="Messages kept in short-term history")
    max_discovery_questions: int = 3
    debounce_seconds: float = 4.0
    webhook_dedup_ttl_seconds: int = 3600
    lock_ttl_seconds: int = 120
    lock_wait_seconds: float = 90.0
    max_bubbles: int = 3
    typing_seconds_per_char: float = 0.03
    typing_max_delay_seconds: float = 3.0
    send_rate_limit_per_minute: int = 20
    allowed_numbers: str = Field(default="", description="Comma-separated; if set, reply only to these")

    @property
    def allowed_number_set(self) -> frozenset[str]:
        entries = (e.strip().lstrip("+") for e in self.allowed_numbers.split(","))
        return frozenset(e for e in entries if e)

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
