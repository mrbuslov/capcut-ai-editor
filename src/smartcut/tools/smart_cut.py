"""Smart Cut tool - main orchestrator for the full video processing pipeline."""

from pathlib import Path
from typing import Literal, Optional

from smartcut.config import SILENCE_THRESHOLD_SEC
from smartcut.tools.analyze import analyze_content
from smartcut.tools.capcut_export import generate_capcut_project
from smartcut.tools.subtitles import generate_subtitles
from smartcut.tools.transcribe import transcribe
from smartcut.tools.video_export import export_video


async def smart_cut(
    file_path: str,
    language: Optional[str] = None,
    silence_threshold_sec: float = SILENCE_THRESHOLD_SEC,
    detect_duplicates: bool = True,
    output_format: Literal["capcut", "video", "both"] = "capcut",
    project_name: Optional[str] = None,
    add_subtitles: bool = True,
    subtitle_style: Literal["dynamic", "simple"] = "dynamic",
) -> dict:
    """
    Main orchestrator - performs full pipeline: transcribe -> analyze -> export.

    This is the primary tool for processing talking head videos. It:
    1. Transcribes the video using Whisper API
    2. Analyzes content to find pauses and duplicate takes
    3. Exports to CapCut project and/or video file

    Args:
        file_path: Path to the video file (MOV, MP4, etc.).
        language: Language code (e.g., 'ru', 'en'). Auto-detect if not specified.
        silence_threshold_sec: Minimum pause duration to cut (default 3.0 seconds).
        detect_duplicates: Whether to detect and remove duplicate takes.
        output_format: Output format - 'capcut', 'video', or 'both'.
        project_name: Name for the CapCut project (auto-generated if not set).
        add_subtitles: Whether to add subtitles to CapCut project.
        subtitle_style: Subtitle style - 'dynamic' (with accents) or 'simple'.

    Returns:
        Complete result with transcription, analysis, and output paths.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Auto-generate project name if not provided
    if not project_name:
        project_name = f"{path.stem} — SmartCut"

    result = {
        "input_file": str(path.absolute()),
        "transcription": None,
        "analysis": None,
        "output": {
            "capcut_project_path": None,
            "video_path": None,
            "srt_path": None,
        },
        "stats": None,
    }

    # Step 1: Transcribe
    transcription_result = await transcribe(file_path, language)
    result["transcription"] = transcription_result

    # Step 2: Analyze
    analysis_result = await analyze_content(
        transcription_result,
        silence_threshold_sec=silence_threshold_sec,
        duplicate_detection=detect_duplicates,
    )
    result["analysis"] = analysis_result

    # Step 3: Generate subtitles if needed
    srt_path = None
    if add_subtitles:
        subtitles_result = await generate_subtitles(
            transcription_data=transcription_result,
            cut_plan_data=analysis_result["cut_plan"],
            style=subtitle_style,
            output_srt_path=str(path.with_suffix(".srt")),
        )
        srt_path = subtitles_result.get("srt_path")
        result["output"]["srt_path"] = srt_path

    # Step 4: Export based on format
    if output_format in ("capcut", "both"):
        capcut_result = await generate_capcut_project(
            file_path=file_path,
            cut_plan_data=analysis_result["cut_plan"],
            project_name=project_name,
            add_subtitles=add_subtitles,
            subtitle_style=subtitle_style,
            transcription_data=transcription_result,
        )
        result["output"]["capcut_project_path"] = capcut_result.get("project_path")

    if output_format in ("video", "both"):
        output_video_path = str(path.with_stem(f"{path.stem}_cut"))
        video_result = await export_video(
            file_path=file_path,
            cut_plan_data=analysis_result["cut_plan"],
            output_path=output_video_path,
        )
        result["output"]["video_path"] = video_result.get("output_path")

    # Add summary stats
    stats = analysis_result.get("summary", {})
    result["stats"] = {
        "original_duration": stats.get("original_duration", ""),
        "final_duration": stats.get("final_duration", ""),
        "time_saved": stats.get("time_saved", ""),
        "duplicates_removed": stats.get("duplicates_removed", 0),
        "silences_removed": stats.get("silences_removed", 0),
    }

    return result


def format_smart_cut_result(result: dict) -> str:
    """Format smart_cut result for human-readable output."""
    stats = result.get("stats", {})
    output = result.get("output", {})

    lines = [
        "SmartCut processing complete!",
        "",
        "Statistics:",
        f"  Original duration: {stats.get('original_duration', 'N/A')}",
        f"  Final duration: {stats.get('final_duration', 'N/A')}",
        f"  Time saved: {stats.get('time_saved', 'N/A')}",
        f"  Duplicates removed: {stats.get('duplicates_removed', 0)}",
        f"  Silences removed: {stats.get('silences_removed', 0)}",
        "",
        "Output:",
    ]

    if output.get("capcut_project_path"):
        lines.append(f"  CapCut project: {output['capcut_project_path']}")
        lines.append("  Open CapCut and find the project in your drafts.")

    if output.get("video_path"):
        lines.append(f"  Video file: {output['video_path']}")

    if output.get("srt_path"):
        lines.append(f"  Subtitles: {output['srt_path']}")

    return "\n".join(lines)
