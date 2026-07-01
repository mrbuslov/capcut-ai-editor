"""MCP tools for working with CapCut projects — smart cut via auto-generated subtitles."""

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from smartcut.config import (
    DUPLICATE_SIMILARITY_THRESHOLD,
    MICROSECONDS_PER_SECOND,
    SILENCE_THRESHOLD_SEC,
    get_settings,
)
from smartcut.core.capcut_finder import (
    find_project_by_name,
    get_capcut_drafts_dir,
    list_projects,
)
from smartcut.core.capcut_reader import CapCutProject
from smartcut.core.models import CapCutSubtitleSegment


# ---------------------------------------------------------------------------
# Tool: list_capcut_projects
# ---------------------------------------------------------------------------

async def list_capcut_projects(
    drafts_dir: Optional[str] = None,
) -> dict:
    """List all CapCut projects in drafts directory."""
    drafts_path = Path(drafts_dir) if drafts_dir else None
    detected_dir = drafts_path or get_capcut_drafts_dir()

    if detected_dir is None:
        return {
            "projects": [],
            "drafts_dir": None,
            "message": "CapCut drafts directory not found. Is CapCut installed?",
        }

    projects = list_projects(detected_dir, require_content=True)
    all_projects = list_projects(detected_dir, require_content=False)
    incomplete_count = len(all_projects) - len(projects)

    message = f"Found {len(projects)} projects"
    if incomplete_count > 0:
        message += f" ({incomplete_count} incomplete — missing draft_info.json)"

    return {
        "projects": [p.model_dump() for p in projects],
        "drafts_dir": str(detected_dir),
        "count": len(projects),
        "message": message if projects else "No complete projects found",
    }


# ---------------------------------------------------------------------------
# Tool: open_capcut_project
# ---------------------------------------------------------------------------

async def open_capcut_project(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
) -> dict:
    """Open existing CapCut project and return its structure."""
    path = _resolve_project_path(project_path, project_name)
    if isinstance(path, dict):
        return path  # error dict

    project = CapCutProject.load(path)
    data = project.to_project_data()
    subtitles = project.get_subtitle_segments()

    return {
        "project": data.model_dump(),
        "auto_subtitles_count": len(subtitles),
        "auto_subtitles": [
            {"text": s.text, "start_sec": round(s.timeline_start_sec, 2), "end_sec": round(s.timeline_end_sec, 2)}
            for s in subtitles
        ],
        "message": (
            f"Loaded '{data.project_name}' — "
            f"{len(data.video_segments)} video segments, "
            f"{len(subtitles)} auto-subtitles"
        ),
    }


# ---------------------------------------------------------------------------
# Tool: smart_cut_project
# ---------------------------------------------------------------------------

async def smart_cut_project(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
    silence_threshold_sec: float = SILENCE_THRESHOLD_SEC,
    similarity_threshold: float = DUPLICATE_SIMILARITY_THRESHOLD,
    use_openai: bool = False,
) -> dict:
    """
    Smart cut a CapCut project using its auto-generated subtitles.

    Reads CapCut's subtitles to heuristically find gaps and duplicate takes,
    then removes them directly in the project (no backup copy).

    Set use_openai=True for GPT-enhanced duplicate detection (requires OPENAI_API_KEY).
    """
    path = _resolve_project_path(project_path, project_name)
    if isinstance(path, dict):
        return path  # error dict

    project = CapCutProject.load(path)

    # Read auto-generated subtitles
    subtitles = project.get_subtitle_segments()
    if not subtitles:
        return {
            "error": "No auto-generated subtitles found in project",
            "suggestion": (
                "Open this project in CapCut, select the video track, "
                "and use Text → Auto Captions to generate subtitles first. "
                "Then run this tool again."
            ),
            "project_path": str(path),
            "project_name": project.project_name,
        }

    threshold_us = int(silence_threshold_sec * MICROSECONDS_PER_SECOND)

    # Step 1: Find gaps (silences between subtitles, including start/end)
    gap_ranges = find_gaps(subtitles, threshold_us, project.duration_us)

    # Step 2: Find duplicate takes
    duplicate_ranges = find_duplicate_takes(subtitles, similarity_threshold)

    # Step 3: Optional OpenAI enhancement
    if use_openai:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError(
                "use_openai=True but OPENAI_API_KEY is not set. "
                "Set it in environment or .env file, or use use_openai=False for heuristic mode."
            )
        llm_ranges = _detect_duplicates_with_llm(subtitles, settings.openai_api_key)
        if llm_ranges:
            duplicate_ranges = llm_ranges

    # Step 4: Merge all ranges
    all_ranges = gap_ranges + duplicate_ranges
    merged_ranges = merge_time_ranges(all_ranges)

    if not merged_ranges:
        return {
            "project_path": str(path),
            "project_name": project.project_name,
            "message": "No cuts needed — no significant gaps or duplicates found",
            "stats": {
                "gaps_found": 0,
                "duplicates_found": 0,
                "time_saved": "0:00",
            },
        }

    # Step 5: Calculate stats before cutting
    total_cut_us = sum(end - start for start, end in merged_ranges)
    original_duration_us = project.duration_us

    # Step 6: Apply cuts
    project.remove_time_ranges(merged_ranges)

    # Step 7: Save directly (no backup)
    project.save()

    return {
        "project_path": str(path),
        "project_name": project.project_name,
        "stats": {
            "original_duration": _format_duration_us(original_duration_us),
            "final_duration": _format_duration_us(original_duration_us - total_cut_us),
            "time_saved": _format_duration_us(total_cut_us),
            "gaps_removed": len(gap_ranges),
            "duplicates_removed": len(duplicate_ranges),
            "total_cuts": len(merged_ranges),
            "subtitles_analyzed": len(subtitles),
            "used_openai": use_openai,
        },
        "cuts_detail": [
            {
                "start_sec": round(s / MICROSECONDS_PER_SECOND, 2),
                "end_sec": round(e / MICROSECONDS_PER_SECOND, 2),
                "duration_sec": round((e - s) / MICROSECONDS_PER_SECOND, 2),
            }
            for s, e in merged_ranges
        ],
        "message": (
            f"Smart cut applied to '{project.project_name}'. "
            f"Removed {len(gap_ranges)} gaps and {len(duplicate_ranges)} duplicate takes, "
            f"saving {_format_duration_us(total_cut_us)}."
        ),
    }


# ---------------------------------------------------------------------------
# Heuristic analysis engine
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, remove punctuation, normalize whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def compute_text_similarity(text_a: str, text_b: str) -> float:
    """
    Compute similarity between two texts.

    Uses max of:
    - Jaccard word overlap (catches reordered duplicates)
    - SequenceMatcher ratio (catches sequential similarity)
    """
    norm_a = normalize_text(text_a)
    norm_b = normalize_text(text_b)

    words_a = set(norm_a.split())
    words_b = set(norm_b.split())

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b
    jaccard = len(intersection) / len(union)

    seq_ratio = SequenceMatcher(None, norm_a, norm_b).ratio()

    return max(jaccard, seq_ratio)


def find_gaps(
    subtitles: list[CapCutSubtitleSegment],
    threshold_us: int,
    project_duration_us: int = 0,
) -> list[tuple[int, int]]:
    """
    Find silence gaps that exceed the threshold.

    Checks:
    - Gap from project start (0) to first subtitle
    - Gaps between consecutive subtitles
    - Gap from last subtitle to project end
    """
    gaps = []

    if not subtitles:
        return gaps

    # Gap at the beginning (before first subtitle) — always cut, it's dead air
    first_start = subtitles[0].timeline_start_us
    if first_start > 0:
        gaps.append((0, first_start))

    # Gaps between consecutive subtitles
    for i in range(len(subtitles) - 1):
        current_end = subtitles[i].timeline_end_us
        next_start = subtitles[i + 1].timeline_start_us
        gap = next_start - current_end
        if gap > threshold_us:
            gaps.append((current_end, next_start))

    # Gap at the end (after last subtitle) — always cut, it's dead air
    if project_duration_us > 0:
        last_end = subtitles[-1].timeline_end_us
        if project_duration_us > last_end:
            gaps.append((last_end, project_duration_us))

    return gaps


def find_duplicate_takes(
    subtitles: list[CapCutSubtitleSegment],
    similarity_threshold: float = DUPLICATE_SIMILARITY_THRESHOLD,
) -> list[tuple[int, int]]:
    """
    Find duplicate takes by detecting "restart points".

    A person records in takes: they say a sequence of phrases, then start over.
    Example:
        "Hello friends today I'll..."   <- Take 1 (abandoned)
        "Hello friends, today I'll show you..."  <- Take 2 (abandoned)
        "Hello friends, today I'll show you how..."  <- Take 3 (KEEP)

    The takes are NOT consecutive — each take is a GROUP of subtitles.
    We detect restarts by finding subtitle[i] that matches a later subtitle[j],
    meaning the speaker went back to re-record from that point.

    Cuts the ENTIRE span from first removed subtitle to the start of the kept
    version — including all gaps between subtitles within the removed takes.

    Returns time ranges of earlier takes to cut.
    """
    if len(subtitles) < 2:
        return []

    ranges_to_cut = []
    i = 0

    while i < len(subtitles):
        # Look for the LATEST restart of this subtitle's phrase
        last_restart = None
        for j in range(i + 1, len(subtitles)):
            if compute_text_similarity(subtitles[i].text, subtitles[j].text) >= similarity_threshold:
                last_restart = j

        if last_restart is not None:
            # Cut ONE continuous range: from start of first removed
            # to start of the kept version (includes all gaps between removed subs)
            cut_start = subtitles[i].timeline_start_us
            cut_end = subtitles[last_restart].timeline_start_us
            ranges_to_cut.append((cut_start, cut_end))
            i = last_restart
        else:
            i += 1

    return ranges_to_cut


def merge_time_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or adjacent time ranges. Returns sorted, non-overlapping list."""
    if not ranges:
        return []

    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged = [sorted_ranges[0]]

    for start, end in sorted_ranges[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    return merged


# ---------------------------------------------------------------------------
# Optional OpenAI-enhanced duplicate detection
# ---------------------------------------------------------------------------

def _detect_duplicates_with_llm(
    subtitles: list[CapCutSubtitleSegment],
    api_key: str,
) -> list[tuple[int, int]]:
    """Use OpenAI GPT to detect duplicate takes more accurately."""
    from smartcut.core.llm_client import LLMClient

    paragraphs = [
        {"id": i, "text": s.text}
        for i, s in enumerate(subtitles)
    ]

    client = LLMClient(api_key=api_key)
    result = client.detect_duplicates(paragraphs)

    ranges_to_cut = []
    for group in result.groups:
        for idx in group.remove:
            if 0 <= idx < len(subtitles):
                seg = subtitles[idx]
                ranges_to_cut.append((seg.timeline_start_us, seg.timeline_end_us))

    return ranges_to_cut


# ---------------------------------------------------------------------------
# Tool: edit_subtitle
# ---------------------------------------------------------------------------

async def edit_subtitle(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
    segment_id: str = "",
    new_text: Optional[str] = None,
    new_start_sec: Optional[float] = None,
    new_duration_sec: Optional[float] = None,
) -> dict:
    """Edit subtitle text and/or timing."""
    path = _resolve_project_path(project_path, project_name)
    if isinstance(path, dict):
        return path

    if not segment_id:
        return {"error": "segment_id is required"}

    project = CapCutProject.load(path)
    changed = []

    if new_text is not None:
        if project.edit_subtitle_text(segment_id, new_text):
            changed.append("text")
        else:
            return {"error": f"Segment '{segment_id}' not found"}

    if new_start_sec is not None or new_duration_sec is not None:
        start_us = int(new_start_sec * MICROSECONDS_PER_SECOND) if new_start_sec is not None else None
        dur_us = int(new_duration_sec * MICROSECONDS_PER_SECOND) if new_duration_sec is not None else None
        if project.edit_subtitle_timing(segment_id, start_us, dur_us):
            changed.append("timing")
        else:
            return {"error": f"Segment '{segment_id}' not found"}

    if not changed:
        return {"error": "Nothing to change — provide new_text, new_start_sec, or new_duration_sec"}

    project.save()
    return {
        "project_name": project.project_name,
        "segment_id": segment_id,
        "changed": changed,
        "message": f"Subtitle updated ({', '.join(changed)}). Restart CapCut to see changes.",
    }


# ---------------------------------------------------------------------------
# Tool: split_subtitle
# ---------------------------------------------------------------------------

async def split_subtitle(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
    segment_id: str = "",
    split_time_sec: float = 0.0,
) -> dict:
    """Split a subtitle into two at a given time point."""
    path = _resolve_project_path(project_path, project_name)
    if isinstance(path, dict):
        return path

    if not segment_id:
        return {"error": "segment_id is required"}
    if split_time_sec <= 0:
        return {"error": "split_time_sec must be > 0"}

    project = CapCutProject.load(path)
    split_us = int(split_time_sec * MICROSECONDS_PER_SECOND)

    if project.split_subtitle(segment_id, split_us):
        project.save()
        return {
            "project_name": project.project_name,
            "segment_id": segment_id,
            "split_at_sec": split_time_sec,
            "message": f"Subtitle split at {split_time_sec:.2f}s. Restart CapCut to see changes.",
        }

    return {"error": f"Could not split segment '{segment_id}' at {split_time_sec}s — check that the time is within the segment's range"}


# ---------------------------------------------------------------------------
# Tool: merge_subtitles
# ---------------------------------------------------------------------------

async def merge_subtitles(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
    segment_id_a: str = "",
    segment_id_b: str = "",
) -> dict:
    """Merge two subtitles into one."""
    path = _resolve_project_path(project_path, project_name)
    if isinstance(path, dict):
        return path

    if not segment_id_a or not segment_id_b:
        return {"error": "Both segment_id_a and segment_id_b are required"}

    project = CapCutProject.load(path)

    if project.merge_subtitles(segment_id_a, segment_id_b):
        project.save()
        return {
            "project_name": project.project_name,
            "merged_into": segment_id_a,
            "removed": segment_id_b,
            "message": "Subtitles merged. Restart CapCut to see changes.",
        }

    return {"error": "Could not merge — one or both segment IDs not found"}


# ---------------------------------------------------------------------------
# Tool: fix_word_timing
# ---------------------------------------------------------------------------

async def fix_word_timing(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
    segment_id: str = "",
    words_text: list[str] | None = None,
    words_start_ms: list[int] | None = None,
    words_end_ms: list[int] | None = None,
) -> dict:
    """Fix word-level timing on a subtitle."""
    path = _resolve_project_path(project_path, project_name)
    if isinstance(path, dict):
        return path

    if not segment_id:
        return {"error": "segment_id is required"}
    if not words_text or not words_start_ms or not words_end_ms:
        return {"error": "words_text, words_start_ms, and words_end_ms are all required"}

    project = CapCutProject.load(path)

    try:
        if project.fix_word_timing(segment_id, words_text, words_start_ms, words_end_ms):
            project.save()
            return {
                "project_name": project.project_name,
                "segment_id": segment_id,
                "word_count": len(words_text),
                "message": "Word timing updated. Restart CapCut to see changes.",
            }
    except ValueError as e:
        return {"error": str(e)}

    return {"error": f"Segment '{segment_id}' not found"}


# ---------------------------------------------------------------------------
# Tool: batch_edit_subtitles
# ---------------------------------------------------------------------------

async def batch_edit_subtitles(
    project_path: Optional[str] = None,
    project_name: Optional[str] = None,
    edits: list[dict] | None = None,
) -> dict:
    """Apply multiple subtitle edits in one pass."""
    path = _resolve_project_path(project_path, project_name)
    if isinstance(path, dict):
        return path

    if not edits:
        return {"error": "edits list is required"}

    project = CapCutProject.load(path)
    results = []

    for i, edit in enumerate(edits):
        sid = edit.get("segment_id", "")
        if not sid:
            results.append({"index": i, "ok": False, "error": "missing segment_id"})
            continue

        ok = True
        new_text = edit.get("new_text")
        if new_text is not None:
            if not project.edit_subtitle_text(sid, new_text):
                results.append({"index": i, "ok": False, "error": "segment not found"})
                continue

        new_start = edit.get("new_start_sec")
        new_dur = edit.get("new_duration_sec")
        if new_start is not None or new_dur is not None:
            start_us = int(new_start * MICROSECONDS_PER_SECOND) if new_start is not None else None
            dur_us = int(new_dur * MICROSECONDS_PER_SECOND) if new_dur is not None else None
            if not project.edit_subtitle_timing(sid, start_us, dur_us):
                results.append({"index": i, "ok": False, "error": "segment not found"})
                continue

        results.append({"index": i, "ok": True, "segment_id": sid})

    project.save()
    succeeded = sum(1 for r in results if r["ok"])
    return {
        "project_name": project.project_name,
        "total": len(edits),
        "succeeded": succeeded,
        "failed": len(edits) - succeeded,
        "results": results,
        "message": f"{succeeded}/{len(edits)} edits applied. Restart CapCut to see changes.",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_project_path(
    project_path: Optional[str],
    project_name: Optional[str],
) -> Path | dict:
    """Resolve project path from either path or name. Returns Path or error dict."""
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
        return {"error": "Either project_path or project_name must be provided"}

    if not path.exists():
        return {"error": f"Project path not found: {path}"}

    content_file = path / "draft_info.json"
    if not content_file.exists():
        return {
            "error": "Project missing draft_info.json",
            "path": str(path),
            "suggestion": "Open it in CapCut first to regenerate the content file.",
        }

    return path


def _format_duration_us(duration_us: int) -> str:
    """Format microseconds as M:SS."""
    total_sec = duration_us / MICROSECONDS_PER_SECOND
    minutes = int(total_sec // 60)
    seconds = int(total_sec % 60)
    return f"{minutes}:{seconds:02d}"
