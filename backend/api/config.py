from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

env_file = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    llm_base_url: str | None = None
    llm_api_key: str = ""  # Must explicitly provide, empty string will raise an error

    aws_endpoint_url: str | None = None

    dynamodb_conversations_table: str = "conversations"
    dynamodb_messages_table: str = "messages"

    ollama_test_model: str = "qwen3:0.6b"

    model_config = SettingsConfigDict(
        secrets_dir=Path("/run/secrets"), extra="ignore", env_file=env_file
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
