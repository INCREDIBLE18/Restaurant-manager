import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore", env_ignore_empty=True)

    database_url: str = f"sqlite:///{(ROOT / 'data' / 'restaurant.db').as_posix()}"
    secret_key: str = "change-me-in-env"
    token_ttl_hours: int = 12
    cors_origins: str = "*"
    data_dir: str = "/tmp/data" if os.environ.get("VERCEL") else str(ROOT / "data")
    max_upload_mb: int = 15
    gemini_api_key: str = ""
    gemini_enabled: bool = False
    gemini_model: str = "gemini-2.5-flash"

    @property
    def attachments_dir(self) -> Path:
        p = Path(self.data_dir) / "attachments"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def backups_dir(self) -> Path:
        p = Path(self.data_dir) / "backups"
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
