"""Application settings (non-secret knobs only — see AGENTS.md).

Override anything with ZLENS_-prefixed environment variables or a local .env file.
VLM keys are secrets: they live in the environment or the gitignored
config_json_path file, never in code or in pricing.json.
"""

import json
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
    minimax_sessions_dir: Path = Path.home() / ".minimax" / "v2" / "sessions"
    opencode_db_path: Path = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

    # Optional VLM used for screenshot price extraction (OpenAI-compatible chat).
    vlm_base_url: str = ""
    vlm_model: str = ""
    vlm_api_key: str = ""

    # Gitignored JSON overlay where the settings page persists VLM config.
    config_json_path: Path = Path("zlens.config.json")

    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def load_settings() -> Settings:
    return Settings()


_VLM_OVERLAY_FIELDS = ("vlm_base_url", "vlm_model", "vlm_api_key")


def with_config_overlay(settings: Settings) -> Settings:
    """Layer the gitignored settings JSON over env/defaults; env still wins."""
    if not settings.config_json_path.exists():
        return settings
    try:
        data = json.loads(settings.config_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings
    vlm = data.get("vlm") or {}
    updates: dict[str, str] = {}
    for field in _VLM_OVERLAY_FIELDS:
        if not getattr(settings, field):
            overlay_key = field.removeprefix("vlm_")
            if vlm.get(overlay_key):
                updates[field] = vlm[overlay_key]
    if not updates:
        return settings
    return settings.model_copy(update=updates)
