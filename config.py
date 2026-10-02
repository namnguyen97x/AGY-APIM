import os
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

# Google OAuth Credentials (can be overridden via environment variables)
_ID_B = [107, 106, 109, 107, 106, 106, 108, 106, 108, 106, 111, 99, 107, 119, 46, 55, 50, 41, 41, 51, 52, 104, 50, 104, 107, 54, 57, 40, 63, 104, 105, 111, 44, 46, 53, 54, 53, 48, 50, 110, 61, 110, 106, 105, 63, 42, 116, 59, 42, 42, 41, 116, 61, 53, 53, 61, 54, 63, 47, 41, 63, 40, 57, 53, 52, 46, 63, 52, 46, 116, 57, 53, 55]
_SEC_B = [29, 21, 25, 9, 10, 2, 119, 17, 111, 98, 28, 13, 8, 110, 98, 108, 22, 62, 22, 16, 107, 55, 22, 24, 98, 41, 2, 25, 110, 32, 108, 43, 30, 27, 60]
_K = 0x5A

CLIENT_ID = os.environ.get("ANTIGRAVITY_CLIENT_ID") or "".join(chr(b ^ _K) for b in _ID_B)
CLIENT_SECRET = os.environ.get("ANTIGRAVITY_CLIENT_SECRET") or "".join(chr(b ^ _K) for b in _SEC_B)

USER_HOME = Path.home()
DEFAULT_DATA_DIR = USER_HOME / ".antigravity_api_manager"
DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Path to existing Antigravity Tools accounts if present
LEGACY_ACCOUNTS_DIR = USER_HOME / ".antigravity_tools" / "accounts"
GEMINI_DIR = USER_HOME / ".gemini"

# Default Model Aliases (OpenAI / Anthropic -> Antigravity internal models)
DEFAULT_MODEL_MAPPING = {
    # Gemini models
    "gemini-3.8-flash": "gemini-3.8-flash-high",
    "gemini-3.8-flash-high": "gemini-3.8-flash-high",
    "gemini-3.8-flash-medium": "gemini-3.8-flash-medium",
    "gemini-3.8-flash-low": "gemini-3.8-flash-low",
    "gemini-3.7-flash": "gemini-3.7-flash-high",
    "gemini-3.6-flash": "gemini-3.6-flash-high",
    "gemini-3-flash": "gemini-3-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-3.1-pro": "gemini-3.1-pro-high",
    "gemini-3.1-pro-high": "gemini-3.1-pro-high",
    
    # Claude models
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-opus-4-6": "claude-opus-4-6-thinking",
    "claude-opus-4-6-thinking": "claude-opus-4-6-thinking",
    "claude-3-7-sonnet": "claude-sonnet-4-6",
    "claude-3-7-sonnet-latest": "claude-sonnet-4-6",
    "claude-3-5-sonnet": "claude-sonnet-4-6",
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
    
    # OpenAI Aliases
    "gpt-4o": "gemini-3.8-flash-high",
    "gpt-4o-mini": "gemini-3-flash",
    "gpt-4": "gemini-2.5-pro",
    "o1": "claude-opus-4-6-thinking",
    "o3-mini": "gemini-3.8-flash-high"
}

class AppConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8088
    api_key: Optional[str] = None  # None means no auth required for local access
    min_quota_threshold: float = 0.05  # Rotate when quota <= 5%
    auto_rotate_on_429: bool = True
    cooldown_seconds_on_429: int = 900  # 15 minutes cooldown if resetTime not given
    rotation_strategy: str = "highest_quota"  # "highest_quota" | "round_robin" | "priority"
    auto_refresh_quota_interval: int = 300  # seconds between auto quota refresh (default 300s = 5m, 0 to disable)
    model_mappings: Dict[str, str] = Field(default_factory=lambda: DEFAULT_MODEL_MAPPING.copy())
    enable_web_ui: bool = True

config_file = DEFAULT_DATA_DIR / "config.json"

def load_config() -> AppConfig:
    if config_file.exists():
        try:
            return AppConfig.model_validate_json(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg = AppConfig()
    save_config(cfg)
    return cfg

def save_config(cfg: AppConfig):
    config_file.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
