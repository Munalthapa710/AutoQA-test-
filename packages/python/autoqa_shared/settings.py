from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "autoqa-agent"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/autoqa"
    database_fallback_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    api_public_base_url: str = "http://localhost:8000"
    artifacts_root: Path = Field(default=Path("/workspace/artifacts"))
    generated_tests_root: Path = Field(default=Path("/workspace/generated-tests"))
    runtime_root: Path = Field(default=Path(".runtime"))
    playwright_headless: bool = True
    safe_mode_default: bool = True
    worker_queue_name: str = "autoqa:runs"
    worker_poll_timeout: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.artifacts_root.mkdir(parents=True, exist_ok=True)
    settings.generated_tests_root.mkdir(parents=True, exist_ok=True)
    settings.runtime_root.mkdir(parents=True, exist_ok=True)
    return settings
