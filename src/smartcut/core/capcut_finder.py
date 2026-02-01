"""CapCut project discovery and listing."""

import json
import platform
from pathlib import Path
from typing import Optional

from smartcut.core.models import ProjectInfo


def get_capcut_drafts_dir() -> Optional[Path]:
    """
    Auto-detect CapCut drafts directory for current OS.

    Returns:
        Path to drafts directory or None if not found.
    """
    system = platform.system()

    if system == "Darwin":  # macOS
        path = Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    elif system == "Windows":
        local_app_data = Path.home() / "AppData" / "Local"
        path = local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    elif system == "Linux":
        # Try common Linux locations
        possible_paths = [
            Path.home() / ".capcut" / "drafts",
            Path.home() / ".local" / "share" / "CapCut" / "drafts",
            Path.home() / "CapCut" / "drafts",
        ]
        for p in possible_paths:
            if p.exists():
                return p
        return None
    else:
        return None

    return path if path.exists() else None


def list_projects(drafts_dir: Optional[Path] = None) -> list[ProjectInfo]:
    """
    List all CapCut projects in drafts directory.

    Args:
        drafts_dir: Path to drafts directory. Auto-detected if None.

    Returns:
        List of ProjectInfo objects sorted by modification time (newest first).
    """
    if drafts_dir is None:
        drafts_dir = get_capcut_drafts_dir()

    if drafts_dir is None or not drafts_dir.exists():
        return []

    projects = []

    for project_folder in drafts_dir.iterdir():
        if not project_folder.is_dir():
            continue

        meta_file = project_folder / "draft_meta_info.json"
        content_file = project_folder / "draft_content.json"

        if not meta_file.exists():
            continue

        try:
            project_info = _parse_project_info(project_folder, meta_file, content_file)
            if project_info:
                projects.append(project_info)
        except Exception:
            # Skip corrupted projects
            continue

    # Sort by modification time (newest first)
    projects.sort(key=lambda p: p.modified_time, reverse=True)

    return projects


def find_project_by_name(
    name: str,
    drafts_dir: Optional[Path] = None,
    exact_match: bool = False,
) -> Optional[Path]:
    """
    Find project by name.

    Args:
        name: Project name to search for.
        drafts_dir: Path to drafts directory. Auto-detected if None.
        exact_match: If True, require exact name match. Otherwise partial match.

    Returns:
        Path to project folder or None if not found.
    """
    projects = list_projects(drafts_dir)

    name_lower = name.lower()

    for project in projects:
        if exact_match:
            if project.name == name:
                return Path(project.path)
        else:
            if name_lower in project.name.lower():
                return Path(project.path)

    return None


def find_project_by_id(
    project_id: str,
    drafts_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Find project by UUID.

    Args:
        project_id: Project UUID.
        drafts_dir: Path to drafts directory. Auto-detected if None.

    Returns:
        Path to project folder or None if not found.
    """
    if drafts_dir is None:
        drafts_dir = get_capcut_drafts_dir()

    if drafts_dir is None or not drafts_dir.exists():
        return None

    # Project folder is named by UUID
    project_folder = drafts_dir / project_id
    if project_folder.exists() and (project_folder / "draft_meta_info.json").exists():
        return project_folder

    return None


def _parse_project_info(
    project_folder: Path,
    meta_file: Path,
    content_file: Path,
) -> Optional[ProjectInfo]:
    """Parse project metadata from JSON files."""
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Get basic info from meta
    project_id = meta.get("draft_id", project_folder.name)
    project_name = meta.get("draft_name", "Untitled")
    duration_us = meta.get("tm_duration", 0)
    modified_time = meta.get("tm_draft_modified", 0)

    # Count video materials from content file if exists
    video_count = 0
    if content_file.exists():
        try:
            with open(content_file, "r", encoding="utf-8") as f:
                content = json.load(f)
            videos = content.get("materials", {}).get("videos", [])
            video_count = len(videos)
        except Exception:
            pass

    # Format duration
    duration_sec = duration_us / 1_000_000
    minutes = int(duration_sec // 60)
    seconds = int(duration_sec % 60)
    duration_formatted = f"{minutes}:{seconds:02d}"

    return ProjectInfo(
        name=project_name,
        path=str(project_folder),
        project_id=project_id,
        duration_us=duration_us,
        duration_formatted=duration_formatted,
        modified_time=modified_time,
        video_count=video_count,
    )
