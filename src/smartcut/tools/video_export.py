"""Video Export tool - exports cut video using FFmpeg."""

import tempfile
from pathlib import Path
from typing import Optional

from smartcut.config import can_modify_source
from smartcut.core.ffmpeg_utils import (
    check_ffmpeg_installed,
    concat_segments,
    cut_segment,
    get_file_format,
    get_media_info,
)
from smartcut.core.models import CutSegment


async def export_video(
    file_path: str,
    cut_plan_data: dict,
    output_path: Optional[str] = None,
    preserve_format: bool = True,
) -> dict:
    """
    Export cut video as a new file using FFmpeg.

    Uses stream copy (no re-encoding) for fast, lossless export.

    Args:
        file_path: Path to the source video file.
        cut_plan_data: Cut plan from analyze_content tool.
        output_path: Output file path. Auto-generated if not set.
        preserve_format: Keep original format (MOV stays MOV). Default True.

    Returns:
        Output file path and information.
    """
    # Check if source file modification is allowed
    if not can_modify_source():
        return {
            "error": "Source file modification is disabled",
            "suggestion": "Set SMARTCUT_ALLOWED_TARGETS=source or SMARTCUT_ALLOWED_TARGETS=all to enable",
        }

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not check_ffmpeg_installed():
        raise RuntimeError(
            "FFmpeg is not installed or not in PATH. "
            "Install it with: brew install ffmpeg (Mac) or winget install ffmpeg (Windows)"
        )

    # Parse cut plan
    keep_segments = [
        CutSegment(**s) for s in cut_plan_data.get("keep_segments", [])
    ]

    if not keep_segments:
        raise ValueError("No segments to keep in cut plan")

    # Determine output path and format
    if output_path:
        out_path = Path(output_path)
    else:
        # Auto-generate output path
        original_format = get_file_format(path)
        output_suffix = f".{original_format}" if preserve_format else ".mp4"
        out_path = path.with_stem(f"{path.stem}_cut").with_suffix(output_suffix)

    # Get media info for duration calculation
    media_info = get_media_info(path)

    # Cut and concatenate segments
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        segment_paths = []

        # Cut each segment
        for i, segment in enumerate(keep_segments):
            segment_path = temp_path / f"segment_{i:04d}{path.suffix}"
            cut_segment(
                input_path=path,
                output_path=segment_path,
                start=segment.start,
                end=segment.end,
                stream_copy=True,
            )
            segment_paths.append(segment_path)

        # Concatenate all segments
        concat_segments(segment_paths, out_path)

    # Calculate output duration
    output_duration = sum(s.end - s.start for s in keep_segments)

    return {
        "output_path": str(out_path.absolute()),
        "duration": output_duration,
        "duration_formatted": f"{int(output_duration // 60)}:{int(output_duration % 60):02d}",
        "format": get_file_format(out_path),
        "segments_count": len(keep_segments),
        "original_duration": media_info.duration,
        "time_saved": media_info.duration - output_duration,
    }
