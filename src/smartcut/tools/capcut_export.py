"""CapCut Export tool - generates CapCut draft project from cut plan."""

from pathlib import Path
from typing import Literal, Optional

from smartcut.config import MICROSECONDS_PER_SECOND, get_settings
from smartcut.core.capcut_draft import CapCutDraft, TextStyle
from smartcut.core.ffmpeg_utils import get_media_info
from smartcut.core.models import CutPlan, CutSegment, Transcription


def seconds_to_microseconds(seconds: float) -> int:
    """Convert seconds to microseconds."""
    return int(seconds * MICROSECONDS_PER_SECOND)


async def generate_capcut_project(
    file_path: str,
    cut_plan_data: dict,
    project_name: Optional[str] = None,
    add_subtitles: bool = True,
    subtitle_style: Literal["dynamic", "simple"] = "dynamic",
    transcription_data: Optional[dict] = None,
) -> dict:
    """
    Generate a CapCut draft project from a cut plan.

    Creates draft_content.json and draft_meta_info.json in the CapCut drafts directory.
    The project will appear in CapCut's drafts list (may require restart).

    Args:
        file_path: Path to the source video file.
        cut_plan_data: Cut plan from analyze_content tool.
        project_name: Name for the project (auto-generated if not set).
        add_subtitles: Whether to add subtitle track.
        subtitle_style: Style for subtitles - 'dynamic' or 'simple'.
        transcription_data: Transcription data (needed for subtitles).

    Returns:
        Project path and instructions.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Get video info
    media_info = get_media_info(path)

    # Parse cut plan
    keep_segments = [
        CutSegment(**s) for s in cut_plan_data.get("keep_segments", [])
    ]

    if not keep_segments:
        raise ValueError("No segments to keep in cut plan")

    # Get settings and drafts directory
    settings = get_settings()
    drafts_dir = settings.get_capcut_drafts_path()

    # Create drafts directory if needed
    drafts_dir.mkdir(parents=True, exist_ok=True)

    # Auto-generate project name
    if not project_name:
        project_name = f"{path.stem} — SmartCut"

    # Create draft
    draft = CapCutDraft(
        project_name=project_name,
        canvas_width=media_info.width,
        canvas_height=media_info.height,
    )

    # Add video material
    video_duration_us = seconds_to_microseconds(media_info.duration)
    material_id = draft.add_video_material(
        file_path=path,
        duration_us=video_duration_us,
        width=media_info.width,
        height=media_info.height,
    )

    # Add video segments
    timeline_position = 0
    for segment in keep_segments:
        source_start_us = seconds_to_microseconds(segment.start)
        duration_us = seconds_to_microseconds(segment.end - segment.start)

        draft.add_video_segment(
            material_id=material_id,
            timeline_start_us=timeline_position,
            source_start_us=source_start_us,
            duration_us=duration_us,
        )

        timeline_position += duration_us

    # Add subtitles if requested and transcription is available
    if add_subtitles and transcription_data:
        await _add_subtitles_to_draft(
            draft=draft,
            transcription_data=transcription_data,
            keep_segments=keep_segments,
            style=subtitle_style,
        )

    # Save project
    project_path = draft.save(drafts_dir)

    return {
        "project_path": str(project_path),
        "draft_content_path": str(project_path / "draft_content.json"),
        "project_name": project_name,
        "segments_count": len(keep_segments),
        "message": f"Project '{project_name}' created. Open CapCut and find it in your drafts. You may need to restart CapCut.",
    }


async def _add_subtitles_to_draft(
    draft: CapCutDraft,
    transcription_data: dict,
    keep_segments: list[CutSegment],
    style: Literal["dynamic", "simple"],
) -> None:
    """Add subtitle segments to CapCut draft."""
    from smartcut.tools.subtitles import map_words_to_timeline, group_words_into_lines

    transcription = Transcription(**transcription_data)

    # Map words to new timeline
    timeline_words = map_words_to_timeline(
        transcription.get_all_words(),
        keep_segments,
    )

    if not timeline_words:
        return

    # Group into subtitle lines
    subtitle_lines = group_words_into_lines(timeline_words)

    # Add subtitle segments
    position_toggle = False  # Alternate between top and bottom for dynamic style

    for line in subtitle_lines:
        # Create style
        if style == "dynamic":
            position_y = 0.2 if position_toggle else 0.8
            position_toggle = not position_toggle
        else:
            position_y = 0.8

        text_style = TextStyle(
            font_size=8,
            font_color="#FFFFFF",
            background_color="#000000" if style == "simple" else None,
            background_alpha=0.6 if style == "simple" else 0.0,
            position_y=position_y,
        )

        # Add text material
        material_id = draft.add_text_material(line["text"], text_style)

        # Add text segment
        start_us = seconds_to_microseconds(line["start"])
        duration_us = seconds_to_microseconds(line["end"] - line["start"])

        draft.add_text_segment(
            material_id=material_id,
            timeline_start_us=start_us,
            duration_us=duration_us,
        )
