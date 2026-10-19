import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore", env_ignore_empty=True)

    database_url: str = f"sqlite:///{(ROOT / 'data' / 'restaurant.db').as_posix()}"
    database_url_unpooled: str = ""
    neon_branch: str = "production"
    neon_auth_base_url: str = ""
    neon_auth_jwks_url: str = ""
    secret_key: str = "change-me-in-env"
    token_ttl_hours: int = 12
    cors_origins: str = "*"
    data_dir: str = "/tmp/data" if os.environ.get("VERCEL") else str(ROOT / "data")
    max_upload_mb: int = 15
    gemini_api_key: str = ""
    gemini_enabled: bool = False
    gemini_model: str = "gemini-2.5-flash"

    @field_validator("gemini_enabled", mode="before")
    @classmethod
    def clean_bool(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "t", "on")
        return bool(v)

    @field_validator("database_url", "database_url_unpooled", "secret_key", "cors_origins", "neon_auth_base_url", "neon_auth_jwks_url", "gemini_api_key", mode="before")
    @classmethod
    def clean_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("token_ttl_hours", "max_upload_mb", mode="before")
    @classmethod
    def clean_ints(cls, v):
        if isinstance(v, str):
            return int(v.strip())
        return v

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
