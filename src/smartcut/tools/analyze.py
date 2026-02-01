"""Analyze tool - analyzes transcription for duplicates and pauses."""

from typing import Optional

from smartcut.config import SILENCE_THRESHOLD_SEC, get_settings
from smartcut.core.llm_client import LLMClient
from smartcut.core.models import (
    AnalysisResult,
    CutPlan,
    CutSegment,
    CutStats,
    Paragraph,
    Transcription,
    TranscriptionWord,
)


def find_paragraphs(
    transcription: Transcription,
    silence_threshold: float = SILENCE_THRESHOLD_SEC,
) -> list[Paragraph]:
    """
    Split transcription into paragraphs based on pauses.

    Args:
        transcription: Transcription with word-level timestamps.
        silence_threshold: Minimum pause duration to consider as paragraph break.

    Returns:
        List of paragraphs.
    """
    all_words = transcription.get_all_words()
    if not all_words:
        return []

    paragraphs = []
    current_words: list[TranscriptionWord] = []
    paragraph_id = 0

    for i, word in enumerate(all_words):
        current_words.append(word)

        # Check for pause before next word
        if i < len(all_words) - 1:
            next_word = all_words[i + 1]
            pause_duration = next_word.start - word.end

            if pause_duration >= silence_threshold:
                # End current paragraph
                if current_words:
                    paragraphs.append(
                        Paragraph(
                            id=paragraph_id,
                            start=current_words[0].start,
                            end=current_words[-1].end,
                            text=" ".join(w.word for w in current_words),
                            action="keep",  # Default, will be updated by duplicate detection
                            reason="",
                        )
                    )
                    paragraph_id += 1
                    current_words = []

    # Add last paragraph
    if current_words:
        paragraphs.append(
            Paragraph(
                id=paragraph_id,
                start=current_words[0].start,
                end=current_words[-1].end,
                text=" ".join(w.word for w in current_words),
                action="keep",
                reason="",
            )
        )

    return paragraphs


def detect_duplicates_in_paragraphs(
    paragraphs: list[Paragraph],
    api_key: str,
) -> list[Paragraph]:
    """
    Use LLM to detect duplicate takes in paragraphs.

    Args:
        paragraphs: List of paragraphs.
        api_key: OpenAI API key.

    Returns:
        Updated paragraphs with duplicate detection results.
    """
    if not paragraphs:
        return paragraphs

    client = LLMClient(api_key)

    # Prepare data for LLM
    paragraph_data = [{"id": p.id, "text": p.text} for p in paragraphs]

    # Detect duplicates
    duplicate_result = client.detect_duplicates(paragraph_data)

    # Update paragraphs based on detection
    remove_ids = set()
    group_map = {}

    for group in duplicate_result.groups:
        for block_id in group.remove:
            remove_ids.add(block_id)
        for block_id in group.block_ids:
            group_map[block_id] = group

    updated_paragraphs = []
    for p in paragraphs:
        if p.id in remove_ids:
            group = group_map.get(p.id)
            reason = f"duplicate_take: {group.reason}" if group else "duplicate_take"
            updated_paragraphs.append(
                Paragraph(
                    id=p.id,
                    start=p.start,
                    end=p.end,
                    text=p.text,
                    action="remove",
                    reason=reason,
                    group_id=group.keep if group else None,
                )
            )
        elif p.id in group_map:
            # This is the "keep" version
            updated_paragraphs.append(
                Paragraph(
                    id=p.id,
                    start=p.start,
                    end=p.end,
                    text=p.text,
                    action="keep",
                    reason="best_take",
                    group_id=p.id,
                )
            )
        else:
            updated_paragraphs.append(p)

    return updated_paragraphs


def build_cut_plan(
    paragraphs: list[Paragraph],
    transcription: Transcription,
    silence_threshold: float = SILENCE_THRESHOLD_SEC,
) -> CutPlan:
    """
    Build a cut plan from analyzed paragraphs.

    Args:
        paragraphs: Analyzed paragraphs.
        transcription: Original transcription.
        silence_threshold: Silence threshold for gap detection.

    Returns:
        CutPlan with keep/remove segments and statistics.
    """
    keep_segments = []
    remove_segments = []

    # Sort paragraphs by start time
    sorted_paragraphs = sorted(paragraphs, key=lambda p: p.start)

    prev_end = 0.0
    duplicates_removed = 0
    silences_removed = 0

    for p in sorted_paragraphs:
        # Check for silence gap before this paragraph
        if p.start - prev_end >= silence_threshold:
            remove_segments.append(
                CutSegment(
                    start=prev_end,
                    end=p.start,
                    reason="long_silence",
                )
            )
            silences_removed += 1

        if p.action == "keep":
            # Find first and last words for this paragraph
            all_words = transcription.get_all_words()
            paragraph_words = [
                w for w in all_words
                if p.start <= w.start <= p.end
            ]
            start_word = paragraph_words[0].word if paragraph_words else ""
            end_word = paragraph_words[-1].word if paragraph_words else ""

            keep_segments.append(
                CutSegment(
                    start=p.start,
                    end=p.end,
                    start_word=start_word,
                    end_word=end_word,
                )
            )
            prev_end = p.end
        else:
            remove_segments.append(
                CutSegment(
                    start=p.start,
                    end=p.end,
                    reason=p.reason,
                )
            )
            duplicates_removed += 1
            prev_end = p.end

    # Calculate statistics
    kept_duration = sum(s.end - s.start for s in keep_segments)
    removed_duration = sum(s.end - s.start for s in remove_segments)

    stats = CutStats(
        original_duration=transcription.duration,
        kept_duration=kept_duration,
        removed_duration=removed_duration,
        duplicates_removed=duplicates_removed,
        silences_removed=silences_removed,
    )

    return CutPlan(
        keep_segments=keep_segments,
        remove_segments=remove_segments,
        stats=stats,
    )


async def analyze_content(
    transcription_data: dict,
    silence_threshold_sec: float = SILENCE_THRESHOLD_SEC,
    duplicate_detection: bool = True,
) -> dict:
    """
    Analyze transcription to identify paragraphs, duplicates, and pauses.

    Args:
        transcription_data: Transcription data from transcribe tool.
        silence_threshold_sec: Minimum pause to consider as paragraph break.
        duplicate_detection: Whether to detect duplicate takes using LLM.

    Returns:
        Analysis result with paragraphs and cut plan.
    """
    # Parse transcription
    transcription = Transcription(**transcription_data)

    # Find paragraphs
    paragraphs = find_paragraphs(transcription, silence_threshold_sec)

    # Detect duplicates if enabled
    if duplicate_detection and paragraphs:
        settings = get_settings()
        if settings.openai_api_key:
            paragraphs = detect_duplicates_in_paragraphs(paragraphs, settings.openai_api_key)

    # Build cut plan
    cut_plan = build_cut_plan(paragraphs, transcription, silence_threshold_sec)

    result = AnalysisResult(paragraphs=paragraphs, cut_plan=cut_plan)

    return {
        "paragraphs": [p.model_dump() for p in result.paragraphs],
        "cut_plan": {
            "keep_segments": [s.model_dump() for s in result.cut_plan.keep_segments],
            "remove_segments": [s.model_dump() for s in result.cut_plan.remove_segments],
            "stats": result.cut_plan.stats.model_dump(),
        },
        "summary": {
            "original_duration": result.cut_plan.stats.original_duration_formatted,
            "final_duration": result.cut_plan.stats.kept_duration_formatted,
            "time_saved": result.cut_plan.stats.time_saved_formatted,
            "paragraphs_total": len(paragraphs),
            "paragraphs_kept": len([p for p in paragraphs if p.action == "keep"]),
            "duplicates_removed": result.cut_plan.stats.duplicates_removed,
            "silences_removed": result.cut_plan.stats.silences_removed,
        },
    }
