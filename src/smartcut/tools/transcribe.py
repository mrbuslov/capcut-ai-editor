"""Transcribe tool - transcribes video/audio using Whisper API."""

import tempfile
from pathlib import Path
from typing import Optional

from smartcut.config import get_settings
from smartcut.core.ffmpeg_utils import check_ffmpeg_installed, extract_audio
from smartcut.core.models import Transcription
from smartcut.core.whisper_client import WhisperClient


async def transcribe(
    file_path: str,
    language: Optional[str] = None,
) -> dict:
    """
    Transcribe a video or audio file using OpenAI Whisper API.

    Args:
        file_path: Path to the video or audio file.
        language: Language code (e.g., 'ru', 'en'). Auto-detect if not specified.

    Returns:
        Transcription result with segments and word-level timestamps.
    """
    # Validate file exists
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Check FFmpeg
    if not check_ffmpeg_installed():
        raise RuntimeError(
            "FFmpeg is not installed or not in PATH. "
            "Install it with: brew install ffmpeg (Mac) or winget install ffmpeg (Windows)"
        )

    # Get settings
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    # Extract audio to temp file
    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = Path(temp_dir) / "audio.wav"
        extract_audio(path, audio_path)

        # Transcribe
        client = WhisperClient(settings.openai_api_key)
        transcription = client.transcribe(audio_path, language)

    return transcription.model_dump()


def format_transcription_result(transcription: Transcription) -> dict:
    """Format transcription for tool output."""
    return {
        "language": transcription.language,
        "duration": transcription.duration,
        "duration_formatted": f"{int(transcription.duration // 60)}:{int(transcription.duration % 60):02d}",
        "segments_count": len(transcription.segments),
        "segments": [
            {
                "id": seg.id,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words_count": len(seg.words),
            }
            for seg in transcription.segments
        ],
        "full_text": " ".join(seg.text for seg in transcription.segments),
    }
