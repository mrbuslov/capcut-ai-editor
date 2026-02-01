"""MCP tools for working with existing CapCut projects."""

from pathlib import Path
from typing import Literal, Optional

from smartcut.config import can_modify_capcut, get_settings
from smartcut.core.capcut_draft import TextStyle
from smartcut.core.capcut_finder import (
    find_project_by_name,
    get_capcut_drafts_dir,
    list_projects,
)
from smartcut.core.capcut_reader import CapCutProject
from smartcut.tools.analyze import analyze_content
from smartcut.tools.subtitles import generate_subtitles
from smartcut.tools.transcribe import transcribe


async def list_capcut_projects(
    drafts_dir: Optional[str] = None,
    include_incomplete: bool = False,
) -> dict:
    """
    List all CapCut projects in drafts directory.

    Args:
        drafts_dir: Path to drafts directory. Auto-detected if not specified.
        include_incomplete: If True, also list projects without draft_info.json.

    Returns:
        List of projects with metadata.
    """
    drafts_path = Path(drafts_dir) if drafts_dir else None

    # Get drafts directory
    detected_dir = drafts_path or get_capcut_drafts_dir()

    if detected_dir is None:
        return {
            "projects": [],
            "drafts_dir": None,
            "message": "CapCut drafts directory not found. Is CapCut installed?",
        }

    # Get complete projects
    projects = list_projects(detected_dir, require_content=True)

    # Optionally get incomplete projects too
    incomplete_count = 0
    if include_incomplete:
        all_projects = list_projects(detected_dir, require_content=False)
        incomplete_count = len(all_projects) - len(projects)
    else:
        # Just count incomplete
        all_projects = list_projects(detected_dir, require_content=False)
        incomplete_count = len(all_projects) - len(projects)

    message = f"Found {len(projects)} projects"
    if incomplete_count > 0:
        message += f" ({incomplete_count} incomplete projects skipped - missing draft_info.json)"

    return {
        "projects": [p.model_dump() for p in projects],
        "drafts_dir": str(detected_dir),
        "count": len(projects),
        "incomplete_count": incomplete_count,
        "message": message if projects else "No complete projects found",
    }


async def open_capcut_project(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
) -> dict:
    """
    Open existing CapCut project and return its structure.

    Args:
        project_path: Full path to project folder.
        project_name: Project name to search for (partial match).

    Returns:
        Project structure with segments and materials.
    """
    # Find project path
    if project_path:
        path = Path(project_path)
    elif project_name:
        path = find_project_by_name(project_name)
        if path is None:
            return {
                "error": f"Project '{project_name}' not found",
                "suggestion": "Use list_capcut_projects to see available projects",
            }
    else:
        return {
            "error": "Either project_path or project_name must be provided",
        }

    if not path.exists():
        return {"error": f"Project path not found: {path}"}

    # Check for required files
    content_file = path / "draft_info.json"
    meta_file = path / "draft_meta_info.json"

    if not content_file.exists():
        return {
            "error": f"Project missing draft_info.json file",
            "path": str(path),
            "suggestion": "This project may be incomplete or use a different CapCut version. Try opening it in CapCut first to regenerate the content file.",
        }

    try:
        project = CapCutProject.load(path)
        data = project.to_project_data()

        return {
            "project": data.model_dump(),
            "source_videos": [str(p) for p in project.get_source_video_paths()],
            "message": f"Loaded project '{data.project_name}' with {len(data.video_segments)} video segments",
        }

    except Exception as e:
        return {
            "error": f"Failed to load project: {e}",
            "path": str(path),
            "files_found": {
                "draft_info.json": content_file.exists(),
                "draft_meta_info.json": meta_file.exists(),
            },
        }


async def add_subtitles_to_project(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
    transcription_data: Optional[dict] = None,
    srt_path: Optional[str] = None,
    style: Literal["dynamic", "simple"] = "dynamic",
    language: Optional[str] = None,
) -> dict:
    """
    Add subtitles to existing CapCut project.

    Creates a copy of the project before making changes.
    Original project remains untouched.

    Args:
        project_path: Full path to project folder.
        project_name: Project name to search for.
        transcription_data: Transcription data. If None, will transcribe video from project.
        srt_path: Path to SRT file to import. Alternative to transcription.
        style: Subtitle style - 'dynamic' or 'simple'.
        language: Language for transcription.

    Returns:
        Path to modified project copy.
    """
    # Check if CapCut modification is allowed
    if not can_modify_capcut():
        return {
            "error": "CapCut project modification is disabled",
            "suggestion": "Set SMARTCUT_ALLOWED_TARGETS=capcut or SMARTCUT_ALLOWED_TARGETS=all to enable",
        }

    # Find project
    if project_path:
        path = Path(project_path)
    elif project_name:
        path = find_project_by_name(project_name)
        if path is None:
            return {"error": f"Project '{project_name}' not found"}
    else:
        return {"error": "Either project_path or project_name must be provided"}

    try:
        # Load original project
        original = CapCutProject.load(path)
        original_name = original.project_name

        # Create backup copy
        copy_name = f"{original_name} — SmartCut"
        project = original.create_copy(copy_name)

        # Get subtitles
        if srt_path:
            # Parse SRT file
            subtitles = _parse_srt_file(Path(srt_path))
        elif transcription_data:
            # Use provided transcription
            subtitles_result = await generate_subtitles(
                transcription_data=transcription_data,
                cut_plan_data={"keep_segments": []},  # No cuts, use full timeline
                style=style,
            )
            subtitles = subtitles_result.get("lines", [])
        else:
            # Transcribe video from project
            video_paths = project.get_source_video_paths()
            if not video_paths:
                return {"error": "No video files found in project"}

            # Transcribe first video
            transcription_result = await transcribe(str(video_paths[0]), language)

            subtitles_result = await generate_subtitles(
                transcription_data=transcription_result,
                cut_plan_data={"keep_segments": []},
                style=style,
            )
            subtitles = subtitles_result.get("lines", [])

        if not subtitles:
            return {"error": "No subtitles generated"}

        # Create text style
        text_style = TextStyle(
            font_size=8,
            font_color="#FFFFFF",
            background_color="#000000" if style == "simple" else None,
            background_alpha=0.6 if style == "simple" else 0.0,
            position_y=0.8,
        )

        # Add subtitles to project copy
        project.add_text_track(subtitles, text_style)
        project.save()

        return {
            "original_project": str(path),
            "modified_project": str(project.project_path),
            "project_name": copy_name,
            "subtitles_added": len(subtitles),
            "message": f"Subtitles added to copy '{copy_name}'. Original project unchanged.",
        }

    except Exception as e:
        return {"error": f"Failed to add subtitles: {e}"}


async def smart_cut_project(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
    silence_threshold_sec: float = 3.0,
    detect_duplicates: bool = True,
    add_subtitles: bool = False,
    language: Optional[str] = None,
) -> dict:
    """
    Apply smart_cut to existing CapCut project.

    Creates a copy of the project before making changes.
    Processes all video clips in the project.

    Args:
        project_path: Full path to project folder.
        project_name: Project name to search for.
        silence_threshold_sec: Minimum pause to cut.
        detect_duplicates: Whether to detect duplicate takes.
        add_subtitles: Whether to add subtitles.
        language: Language for transcription.

    Returns:
        Path to modified project copy with statistics.
    """
    # Check if CapCut modification is allowed
    if not can_modify_capcut():
        return {
            "error": "CapCut project modification is disabled",
            "suggestion": "Set SMARTCUT_ALLOWED_TARGETS=capcut or SMARTCUT_ALLOWED_TARGETS=all to enable",
        }

    # Find project
    if project_path:
        path = Path(project_path)
    elif project_name:
        path = find_project_by_name(project_name)
        if path is None:
            return {"error": f"Project '{project_name}' not found"}
    else:
        return {"error": "Either project_path or project_name must be provided"}

    # Check for required files
    content_file = path / "draft_info.json"
    if not content_file.exists():
        return {
            "error": f"Project missing draft_info.json file",
            "path": str(path),
            "suggestion": "This project may be incomplete. Try opening it in CapCut first, make any edit, and save.",
        }

    try:
        # Load original project
        original = CapCutProject.load(path)
        original_name = original.project_name

        # Create backup copy
        copy_name = f"{original_name} — SmartCut"
        project = original.create_copy(copy_name)

        # Get all video sources
        video_paths = project.get_source_video_paths()
        if not video_paths:
            return {
                "error": "No video files found in project",
                "suggestion": "The project doesn't contain video materials. Add a video in CapCut first.",
            }

        # Process each video and collect results
        all_stats = {
            "original_duration": 0,
            "kept_duration": 0,
            "duplicates_removed": 0,
            "silences_removed": 0,
            "videos_processed": 0,
        }

        all_subtitles = []

        for video_path in video_paths:
            if not video_path.exists():
                continue

            # Transcribe
            transcription_result = await transcribe(str(video_path), language)

            # Analyze
            analysis_result = await analyze_content(
                transcription_result,
                silence_threshold_sec=silence_threshold_sec,
                duplicate_detection=detect_duplicates,
            )

            cut_plan = analysis_result.get("cut_plan", {})
            stats = cut_plan.get("stats", {})
            all_stats["original_duration"] += stats.get("original_duration", 0)
            all_stats["kept_duration"] += stats.get("kept_duration", 0)
            all_stats["duplicates_removed"] += stats.get("duplicates_removed", 0)
            all_stats["silences_removed"] += stats.get("silences_removed", 0)
            all_stats["videos_processed"] += 1

            # Apply cuts to video segments in the project
            project.apply_cut_plan(cut_plan, video_path)

            # Generate subtitles if requested
            if add_subtitles:
                subtitles_result = await generate_subtitles(
                    transcription_data=transcription_result,
                    cut_plan_data=analysis_result.get("cut_plan", {}),
                    style="dynamic",
                )
                all_subtitles.extend(subtitles_result.get("lines", []))

        # Add subtitles if any
        if all_subtitles:
            text_style = TextStyle(
                font_size=8,
                font_color="#FFFFFF",
                position_y=0.8,
            )
            project.add_text_track(all_subtitles, text_style)

        project.save()

        # Format durations
        def format_duration(sec):
            return f"{int(sec // 60)}:{int(sec % 60):02d}"

        return {
            "original_project": str(path),
            "modified_project": str(project.project_path),
            "project_name": copy_name,
            "stats": {
                "original_duration": format_duration(all_stats["original_duration"]),
                "final_duration": format_duration(all_stats["kept_duration"]),
                "time_saved": format_duration(all_stats["original_duration"] - all_stats["kept_duration"]),
                "duplicates_removed": all_stats["duplicates_removed"],
                "silences_removed": all_stats["silences_removed"],
                "videos_processed": all_stats["videos_processed"],
            },
            "subtitles_added": len(all_subtitles) if add_subtitles else 0,
            "message": f"Smart cut applied to copy '{copy_name}'. Original project unchanged.",
        }

    except Exception as e:
        return {"error": f"Failed to process project: {e}"}


def _parse_srt_file(srt_path: Path) -> list[dict]:
    """Parse SRT file into subtitle list."""
    if not srt_path.exists():
        return []

    subtitles = []
    content = srt_path.read_text(encoding="utf-8")

    blocks = content.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        # Parse timestamp line
        timestamp_line = lines[1]
        if " --> " not in timestamp_line:
            continue

        start_str, end_str = timestamp_line.split(" --> ")
        start = _parse_srt_timestamp(start_str)
        end = _parse_srt_timestamp(end_str)

        # Get text (may be multiple lines)
        text = " ".join(lines[2:])

        subtitles.append({
            "start": start,
            "end": end,
            "text": text,
        })

    return subtitles


def _parse_srt_timestamp(ts: str) -> float:
    """Parse SRT timestamp (HH:MM:SS,mmm) to seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) != 3:
        return 0.0

    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])

    return hours * 3600 + minutes * 60 + seconds
