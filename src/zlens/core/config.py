"""Application settings (non-secret knobs only — see AGENTS.md).

Override anything with ZLENS_-prefixed environment variables or a local .env file.
VLM keys are secrets: they live in the environment or the gitignored
config_json_path file, never in code or in pricing.json.
"""

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DB_PATH = Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"


def _app_data_dir() -> Path:
    """VS Code-family per-user config root (state.vscdb lives under <app>/User)."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path.home() / ".config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ZLENS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    db_path: Path = DEFAULT_DB_PATH
    pricing_path: Path = Path("pricing.json")
    minimax_sessions_dir: Path = Path.home() / ".minimax" / "v2" / "sessions"
    opencode_db_path: Path = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    # WorkBuddy root: holds projects/**/*.jsonl (the only metered source) and
    # workbuddy.db, whose session_usage duplicates credit totals and is never read.
    workbuddy_dir: Path = Path.home() / ".workbuddy"
    # Qoder CN CLI root: projects transcripts metered in credits (tokens absent);
    # official 30-day retention truncates the local window.
    qoder_cn_config_dir: Path = Path.home() / ".qoder-cn"
    # International Qoder CLI root: same shape as the CN CLI, separate source id
    # (the two products' credits are priced differently and never merge).
    qoder_config_dir: Path = Path.home() / ".qoder"
    # v3 D4 系数快照:两处明文客户端缓存 + 快照落点(gitignored)。抓取是用户显式
    # 动作,快照只用于展示与誊抄,永不参与金额计算。
    qoder_ide_state_vscdb: Path = (
        _app_data_dir() / "Qoder" / "User" / "globalStorage" / "state.vscdb"
    )
    trae_cn_state_vscdb: Path = (
        _app_data_dir() / "Trae CN" / "User" / "globalStorage" / "state.vscdb"
    )
    credit_rates_path: Path = Path("credit_rates.json")

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
