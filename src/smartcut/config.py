"""Configuration and settings for SmartCut MCP Server."""

import platform
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
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
            return Path.cwd() / "capcut_drafts"


SILENCE_THRESHOLD_SEC = 1.0
MIN_SEGMENT_DURATION_SEC = 0.5
# 0.6 matched unrelated sentences that merely shared common words; on a 29-min
# talking-head project every match below 0.75 was a false positive.
DUPLICATE_SIMILARITY_THRESHOLD = 0.8

# A retake follows the flubbed line almost immediately, so only look for a
# restart within this window. Without it, two unrelated sentences minutes apart
# can share enough common words to look like a duplicate.
DUPLICATE_LOOKAHEAD_SEC = 30.0

# Reject any single duplicate range longer than this — a real retake is short.
MAX_DUPLICATE_SPAN_SEC = 90.0

# Short subtitles ("и вот", "да") match almost anything, so never treat one as
# the start of a take.
MIN_DUPLICATE_WORDS = 4

# Refuse to apply a cut that would remove more than this fraction of the project.
MAX_TOTAL_CUT_RATIO = 0.5
WHISPER_MODEL = "whisper-1"
LLM_MODEL = "gpt-4.1-mini"
MICROSECONDS_PER_SECOND = 1_000_000


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
