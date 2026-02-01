"""Subtitles tool - generates SRT files and styled CapCut subtitles."""

from pathlib import Path
from typing import Literal, Optional

from smartcut.config import SUBTITLE_MAX_CHARS, SUBTITLE_MAX_WORDS, get_settings
from smartcut.core.llm_client import LLMClient
from smartcut.core.models import CutSegment, Transcription, TranscriptionWord


def map_words_to_timeline(
    words: list[TranscriptionWord],
    keep_segments: list[CutSegment],
) -> list[dict]:
    """
    Map original word timestamps to the new timeline after cuts.

    Args:
        words: Original words with timestamps.
        keep_segments: Segments that are kept in the final video.

    Returns:
        List of words with new timeline positions.
    """
    timeline_words = []
    timeline_offset = 0.0

    for segment in keep_segments:
        # Find words that fall within this segment
        segment_words = [
            w for w in words
            if segment.start <= w.start < segment.end
        ]

        for word in segment_words:
            # Calculate new position on timeline
            relative_start = word.start - segment.start
            relative_end = word.end - segment.start

            # Clamp to segment bounds
            relative_end = min(relative_end, segment.end - segment.start)

            timeline_words.append({
                "word": word.word,
                "start": timeline_offset + relative_start,
                "end": timeline_offset + relative_end,
            })

        timeline_offset += segment.end - segment.start

    return timeline_words


def group_words_into_lines(
    words: list[dict],
    max_words: int = SUBTITLE_MAX_WORDS,
    max_chars: int = SUBTITLE_MAX_CHARS,
) -> list[dict]:
    """
    Group words into subtitle lines with duration.

    Args:
        words: Words with timeline positions.
        max_words: Maximum words per line.
        max_chars: Maximum characters per line.

    Returns:
        List of subtitle lines with start, end, text.
    """
    if not words:
        return []

    lines = []
    current_line_words = []
    current_line_text = ""

    for word in words:
        word_text = word["word"].strip()
        test_text = f"{current_line_text} {word_text}".strip()

        # Check if adding this word exceeds limits
        if (len(current_line_words) >= max_words or len(test_text) > max_chars) and current_line_words:
            # Finalize current line
            lines.append({
                "start": current_line_words[0]["start"],
                "end": current_line_words[-1]["end"],
                "text": current_line_text,
            })
            current_line_words = []
            current_line_text = ""

        current_line_words.append(word)
        current_line_text = f"{current_line_text} {word_text}".strip()

    # Add final line
    if current_line_words:
        lines.append({
            "start": current_line_words[0]["start"],
            "end": current_line_words[-1]["end"],
            "text": current_line_text,
        })

    return lines


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt_content(lines: list[dict]) -> str:
    """Generate SRT file content from subtitle lines."""
    srt_lines = []

    for i, line in enumerate(lines, start=1):
        start_ts = format_srt_timestamp(line["start"])
        end_ts = format_srt_timestamp(line["end"])

        srt_lines.append(str(i))
        srt_lines.append(f"{start_ts} --> {end_ts}")
        srt_lines.append(line["text"])
        srt_lines.append("")

    return "\n".join(srt_lines)


async def generate_subtitles(
    transcription_data: dict,
    cut_plan_data: dict,
    style: Literal["dynamic", "simple"] = "dynamic",
    output_srt_path: Optional[str] = None,
    identify_accents: bool = True,
) -> dict:
    """
    Generate subtitles from transcription aligned to cut plan.

    Args:
        transcription_data: Transcription data from transcribe tool.
        cut_plan_data: Cut plan from analyze_content tool.
        style: Subtitle style - 'dynamic' (with accents) or 'simple'.
        output_srt_path: Path for SRT file output.
        identify_accents: Whether to identify accent words for dynamic style.

    Returns:
        Subtitle generation result with file path and statistics.
    """
    transcription = Transcription(**transcription_data)
    keep_segments = [
        CutSegment(**s) for s in cut_plan_data.get("keep_segments", [])
    ]

    # Map words to timeline
    timeline_words = map_words_to_timeline(
        transcription.get_all_words(),
        keep_segments,
    )

    if not timeline_words:
        return {
            "srt_path": None,
            "subtitle_segments_count": 0,
            "accent_words_count": 0,
            "message": "No words to create subtitles from",
        }

    # Group into lines
    subtitle_lines = group_words_into_lines(timeline_words)

    # Identify accent words if dynamic style
    accent_words_count = 0
    if style == "dynamic" and identify_accents:
        settings = get_settings()
        if settings.openai_api_key:
            try:
                llm = LLMClient(settings.openai_api_key)
                for line in subtitle_lines:
                    accents = llm.identify_accent_words(line["text"])
                    line["accent_words"] = accents
                    accent_words_count += len(accents)
            except Exception as e:
                # Continue without accents on error
                print(f"Warning: Accent identification failed: {e}")

    # Generate SRT file
    srt_content = generate_srt_content(subtitle_lines)
    srt_path = None

    if output_srt_path:
        srt_path = Path(output_srt_path)
        srt_path.write_text(srt_content, encoding="utf-8")

    return {
        "srt_path": str(srt_path) if srt_path else None,
        "srt_content": srt_content,
        "subtitle_segments_count": len(subtitle_lines),
        "accent_words_count": accent_words_count,
        "lines": subtitle_lines,
    }
