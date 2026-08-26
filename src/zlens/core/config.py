"""Application settings (non-secret knobs only — see AGENTS.md).

Override anything with ZLENS_-prefixed environment variables or a local .env file.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DB_PATH = Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ZLENS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    db_path: Path = DEFAULT_DB_PATH
    pricing_path: Path = Path("pricing.json")
    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def load_settings() -> Settings:
    return Settings()
