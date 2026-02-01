"""Configuration and settings for SmartCut MCP Server."""

import platform
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    auphonic_api_key: Optional[str] = Field(default=None, alias="AUPHONIC_API_KEY")
    auphonic_preset_uuid: Optional[str] = Field(default=None, alias="AUPHONIC_PRESET_UUID")

    # CapCut
    capcut_drafts_dir: Optional[str] = Field(default=None, alias="CAPCUT_DRAFTS_DIR")

    model_config = {"env_file": ".env", "extra": "ignore"}

    def get_capcut_drafts_path(self) -> Path:
        """Get CapCut drafts directory path, auto-detecting if not set."""
        if self.capcut_drafts_dir:
            return Path(self.capcut_drafts_dir)

        system = platform.system()
        if system == "Darwin":  # macOS
            return Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        elif system == "Windows":
            local_app_data = Path.home() / "AppData" / "Local"
            return local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        else:
            # Linux or other - use current directory
            return Path.cwd() / "capcut_drafts"


# Default constants
SILENCE_THRESHOLD_SEC = 3.0
MIN_SEGMENT_DURATION_SEC = 0.5
SUBTITLE_MAX_WORDS = 8
SUBTITLE_MAX_CHARS = 45
TARGET_LUFS = -16.0
WHISPER_MODEL = "whisper-1"
LLM_MODEL = "gpt-4o-mini"

# Time conversion
MICROSECONDS_PER_SECOND = 1_000_000


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
