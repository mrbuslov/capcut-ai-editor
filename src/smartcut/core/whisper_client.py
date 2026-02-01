"""OpenAI Whisper API client for transcription."""

import time
from pathlib import Path
from typing import Optional

from openai import OpenAI

from smartcut.config import WHISPER_MODEL
from smartcut.core.models import Transcription, TranscriptionSegment, TranscriptionWord

MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds


class WhisperClient:
    """Client for OpenAI Whisper API transcription."""

    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.model = WHISPER_MODEL

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
    ) -> Transcription:
        """
        Transcribe audio file using Whisper API.

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)
            language: Language code (e.g., 'ru', 'en'). Auto-detect if None.

        Returns:
            Transcription object with segments and word-level timestamps.
        """
        file_size = audio_path.stat().st_size

        if file_size > MAX_FILE_SIZE_BYTES:
            return self._transcribe_chunked(audio_path, language)

        return self._transcribe_single(audio_path, language)

    def _transcribe_single(
        self,
        audio_path: Path,
        language: Optional[str] = None,
    ) -> Transcription:
        """Transcribe a single audio file (under 25MB)."""
        for attempt in range(MAX_RETRIES):
            try:
                with open(audio_path, "rb") as audio_file:
                    kwargs = {
                        "model": self.model,
                        "file": audio_file,
                        "response_format": "verbose_json",
                        "timestamp_granularities": ["word", "segment"],
                    }
                    if language:
                        kwargs["language"] = language

                    response = self.client.audio.transcriptions.create(**kwargs)

                return self._parse_response(response)

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE ** (attempt + 1)
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Whisper API error after {MAX_RETRIES} attempts: {e}")

        raise RuntimeError("Unexpected error in transcription")

    def _transcribe_chunked(
        self,
        audio_path: Path,
        language: Optional[str] = None,
    ) -> Transcription:
        """
        Transcribe large audio file by splitting into chunks.

        Note: For simplicity, this implementation processes the file as-is
        and relies on Whisper's ability to handle longer files. If this fails,
        the caller should pre-split the audio using FFmpeg.
        """
        # For now, attempt single transcription and raise clear error if it fails
        try:
            return self._transcribe_single(audio_path, language)
        except Exception as e:
            raise RuntimeError(
                f"Audio file is too large ({audio_path.stat().st_size / 1024 / 1024:.1f}MB). "
                f"Maximum supported size is {MAX_FILE_SIZE_MB}MB. "
                f"Please split the audio file or use a shorter video. Error: {e}"
            )

    def _parse_response(self, response) -> Transcription:
        """Parse Whisper API response into Transcription model."""
        segments = []

        # Get words if available
        all_words = getattr(response, "words", []) or []

        for i, seg in enumerate(response.segments or []):
            # Find words belonging to this segment
            segment_words = []
            for word_data in all_words:
                word_start = getattr(word_data, "start", None)
                word_end = getattr(word_data, "end", None)
                word_text = getattr(word_data, "word", "")

                if word_start is not None and word_end is not None:
                    # Check if word falls within segment timerange
                    if seg.start <= word_start < seg.end:
                        segment_words.append(
                            TranscriptionWord(
                                word=word_text.strip(),
                                start=word_start,
                                end=word_end,
                            )
                        )

            segments.append(
                TranscriptionSegment(
                    id=i,
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    words=segment_words,
                )
            )

        # Detect language from response or default
        detected_language = getattr(response, "language", "unknown")

        # Calculate duration from last segment end time
        duration = segments[-1].end if segments else 0.0

        return Transcription(
            language=detected_language,
            duration=duration,
            segments=segments,
        )
