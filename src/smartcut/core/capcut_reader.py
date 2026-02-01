"""CapCut project reader and modifier."""

import json
import shutil
import time
from pathlib import Path
from typing import Optional

from smartcut.config import MICROSECONDS_PER_SECOND
from smartcut.core.capcut_draft import CapCutDraft, TextStyle, generate_uuid
from smartcut.core.models import (
    CapCutProjectData,
    ExistingTextSegment,
    ExistingVideoMaterial,
    ExistingVideoSegment,
)


class CapCutProject:
    """
    Represents an existing CapCut project.

    Can load, modify, and save CapCut draft projects.
    """

    def __init__(self, project_path: Path):
        """
        Initialize with project path.

        Args:
            project_path: Path to project folder (containing draft_info.json).
        """
        self.project_path = project_path
        self.content_file = project_path / "draft_info.json"
        self.meta_file = project_path / "draft_meta_info.json"

        if not self.content_file.exists():
            raise FileNotFoundError(f"draft_info.json not found in {project_path}")

        self._content: dict = {}
        self._meta: dict = {}
        self._load()

    def _load(self) -> None:
        """Load project files."""
        with open(self.content_file, "r", encoding="utf-8") as f:
            self._content = json.load(f)

        if self.meta_file.exists():
            with open(self.meta_file, "r", encoding="utf-8") as f:
                self._meta = json.load(f)

    @classmethod
    def load(cls, project_path: Path) -> "CapCutProject":
        """Load project from path."""
        return cls(project_path)

    @property
    def project_id(self) -> str:
        """Get project UUID."""
        return self._content.get("id", self.project_path.name)

    @property
    def project_name(self) -> str:
        """Get project name from meta file (primary) or content file (fallback)."""
        return self._meta.get("draft_name") or self._content.get("name") or "Untitled"

    @project_name.setter
    def project_name(self, value: str) -> None:
        """Set project name."""
        self._content["name"] = value
        self._meta["draft_name"] = value

    @property
    def duration_us(self) -> int:
        """Get project duration in microseconds."""
        return self._content.get("duration", 0)

    @property
    def duration(self) -> float:
        """Get project duration in seconds."""
        return self.duration_us / MICROSECONDS_PER_SECOND

    @property
    def canvas_width(self) -> int:
        """Get canvas width."""
        return self._content.get("canvas_config", {}).get("width", 1080)

    @property
    def canvas_height(self) -> int:
        """Get canvas height."""
        return self._content.get("canvas_config", {}).get("height", 1920)

    def get_video_materials(self) -> list[ExistingVideoMaterial]:
        """Get all video materials in project."""
        materials = []
        for mat in self._content.get("materials", {}).get("videos", []):
            materials.append(
                ExistingVideoMaterial(
                    id=mat.get("id", ""),
                    path=mat.get("path", ""),
                    duration=mat.get("duration", 0) / MICROSECONDS_PER_SECOND,
                    width=mat.get("width", 0),
                    height=mat.get("height", 0),
                )
            )
        return materials

    def get_video_segments(self) -> list[ExistingVideoSegment]:
        """Get all video segments from video track."""
        segments = []
        materials_map = {m.id: m for m in self.get_video_materials()}

        for track in self._content.get("tracks", []):
            if track.get("type") != "video":
                continue

            for seg in track.get("segments", []):
                material_id = seg.get("material_id", "")
                material = materials_map.get(material_id)
                source_path = material.path if material else ""

                target = seg.get("target_timerange", {})
                source = seg.get("source_timerange", {})

                timeline_start = target.get("start", 0) / MICROSECONDS_PER_SECOND
                duration = target.get("duration", 0) / MICROSECONDS_PER_SECOND

                segments.append(
                    ExistingVideoSegment(
                        id=seg.get("id", ""),
                        material_id=material_id,
                        source_path=source_path,
                        timeline_start=timeline_start,
                        timeline_end=timeline_start + duration,
                        source_start=source.get("start", 0) / MICROSECONDS_PER_SECOND,
                        source_end=(source.get("start", 0) + source.get("duration", 0)) / MICROSECONDS_PER_SECOND,
                        duration=duration,
                    )
                )

        return segments

    def get_text_segments(self) -> list[ExistingTextSegment]:
        """Get all text segments from text tracks."""
        segments = []
        text_materials = {
            m.get("id"): m
            for m in self._content.get("materials", {}).get("texts", [])
        }

        for track in self._content.get("tracks", []):
            if track.get("type") != "text":
                continue

            for seg in track.get("segments", []):
                material_id = seg.get("material_id", "")
                material = text_materials.get(material_id, {})

                # Parse text from content JSON
                content_str = material.get("content", "{}")
                try:
                    content = json.loads(content_str)
                    text = content.get("text", "")
                except json.JSONDecodeError:
                    text = ""

                target = seg.get("target_timerange", {})
                timeline_start = target.get("start", 0) / MICROSECONDS_PER_SECOND
                duration = target.get("duration", 0) / MICROSECONDS_PER_SECOND

                segments.append(
                    ExistingTextSegment(
                        id=seg.get("id", ""),
                        material_id=material_id,
                        text=text,
                        timeline_start=timeline_start,
                        timeline_end=timeline_start + duration,
                    )
                )

        return segments

    def get_source_video_paths(self) -> list[Path]:
        """Get unique source video file paths."""
        paths = set()
        for material in self.get_video_materials():
            if material.path:
                paths.add(Path(material.path))
        return list(paths)

    def to_project_data(self) -> CapCutProjectData:
        """Convert to CapCutProjectData model."""
        return CapCutProjectData(
            project_id=self.project_id,
            project_name=self.project_name,
            project_path=str(self.project_path),
            duration=self.duration,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height,
            video_materials=self.get_video_materials(),
            video_segments=self.get_video_segments(),
            text_segments=self.get_text_segments(),
        )

    def add_text_track(
        self,
        subtitles: list[dict],
        style: Optional[TextStyle] = None,
    ) -> None:
        """
        Add a text track with subtitles.

        Args:
            subtitles: List of dicts with 'start', 'end', 'text' keys (times in seconds).
            style: Text style configuration.
        """
        if not subtitles:
            return

        style = style or TextStyle()

        # Get or create text materials list
        if "texts" not in self._content.get("materials", {}):
            self._content.setdefault("materials", {})["texts"] = []

        text_materials = self._content["materials"]["texts"]

        # Create text segments
        new_segments = []
        position_toggle = False

        for sub in subtitles:
            start_us = int(sub["start"] * MICROSECONDS_PER_SECOND)
            end_us = int(sub["end"] * MICROSECONDS_PER_SECOND)
            duration_us = end_us - start_us
            text = sub["text"]

            # Alternate position for dynamic style
            if style.position_y == 0.8:  # Default bottom
                position_y = 0.2 if position_toggle else 0.8
                position_toggle = not position_toggle
            else:
                position_y = style.position_y

            # Create material
            material_id = generate_uuid()
            text_material = self._build_text_material(material_id, text, style)
            text_materials.append(text_material)

            # Create segment
            segment = self._build_text_segment(material_id, start_us, duration_us, position_y)
            new_segments.append(segment)

        # Find or create text track
        text_track = None
        for track in self._content.get("tracks", []):
            if track.get("type") == "text":
                text_track = track
                break

        if text_track is None:
            text_track = {
                "attribute": 0,
                "flag": 0,
                "id": generate_uuid(),
                "is_default_name": True,
                "name": "",
                "segments": [],
                "type": "text",
            }
            self._content.setdefault("tracks", []).append(text_track)

        # Add segments to track
        text_track["segments"].extend(new_segments)

        # Update duration if needed
        self._update_duration()

    def _build_text_material(self, material_id: str, text: str, style: TextStyle) -> dict:
        """Build text material JSON."""
        content = {
            "styles": [
                {
                    "fill": {
                        "alpha": 1.0,
                        "content": {"render_type": "solid", "solid": {"color": [1.0, 1.0, 1.0]}},
                    },
                    "font": {"id": "", "path": style.font_path},
                    "range": [0, len(text)],
                    "size": style.font_size,
                }
            ],
            "text": text,
        }

        return {
            "id": material_id,
            "type": "text",
            "add_type": 0,
            "alignment": 1,
            "background_alpha": style.background_alpha,
            "background_color": style.background_color or "",
            "background_style": 0 if not style.background_color else 1,
            "bold_width": 0.0 if not style.bold else 1.0,
            "content": json.dumps(content),
            "font_size": style.font_size,
            "global_alpha": 1.0,
            "line_max_width": 0.82,
            "line_spacing": 0.02,
            "text_color": style.font_color,
            "text_size": style.font_size,
            "type": "text",
        }

    def _build_text_segment(
        self,
        material_id: str,
        start_us: int,
        duration_us: int,
        position_y: float,
    ) -> dict:
        """Build text segment JSON."""
        return {
            "id": generate_uuid(),
            "material_id": material_id,
            "target_timerange": {"start": start_us, "duration": duration_us},
            "source_timerange": {"start": 0, "duration": duration_us},
            "clip": {
                "alpha": 1.0,
                "flip": {"horizontal": False, "vertical": False},
                "rotation": 0.0,
                "scale": {"x": 1.0, "y": 1.0},
                "transform": {"x": 0.0, "y": position_y - 0.5},
            },
            "render_index": 11000,
            "visible": True,
            "speed": 1.0,
        }

    def update_video_segments(self, new_segments: list[dict]) -> None:
        """
        Replace video segments with new ones.

        Args:
            new_segments: List of dicts with segment data.
        """
        for track in self._content.get("tracks", []):
            if track.get("type") == "video":
                track["segments"] = new_segments
                break

        self._update_duration()

    def apply_cut_plan(self, cut_plan: dict, video_path: Path) -> None:
        """
        Apply cut plan to video segments.

        Replaces video track segments with new ones based on keep_segments from cut_plan.

        Args:
            cut_plan: Dict with 'keep_segments' list containing {start, end} in seconds.
            video_path: Source video path (to find matching material).
        """
        keep_segments = cut_plan.get("keep_segments", [])
        if not keep_segments:
            return

        # Find video track
        video_track = self._find_video_track()
        if video_track is None:
            return

        # Find material_id for this video
        material_id = self._find_material_id_for_path(video_path)
        if material_id is None:
            return

        # Get existing segment as template (for copying default fields)
        existing_segments = video_track.get("segments", [])
        template_segment = existing_segments[0] if existing_segments else {}

        # Build new segments from keep_segments
        new_segments = []
        timeline_offset_us = 0

        for seg in keep_segments:
            source_start_us = int(seg["start"] * MICROSECONDS_PER_SECOND)
            source_end_us = int(seg["end"] * MICROSECONDS_PER_SECOND)
            duration_us = source_end_us - source_start_us

            new_segment = self._build_video_segment(
                material_id=material_id,
                timeline_start_us=timeline_offset_us,
                source_start_us=source_start_us,
                duration_us=duration_us,
                template=template_segment,
            )
            new_segments.append(new_segment)
            timeline_offset_us += duration_us

        # Replace video track segments
        video_track["segments"] = new_segments
        self._update_duration()

    def _find_video_track(self) -> Optional[dict]:
        """Find the video track in tracks list."""
        for track in self._content.get("tracks", []):
            if track.get("type") == "video":
                return track
        return None

    def _find_material_id_for_path(self, video_path: Path) -> Optional[str]:
        """Find material_id for a video path."""
        video_path_str = str(video_path)
        for mat in self._content.get("materials", {}).get("videos", []):
            if mat.get("path") == video_path_str:
                return mat.get("id")
        return None

    def _build_video_segment(
        self,
        material_id: str,
        timeline_start_us: int,
        source_start_us: int,
        duration_us: int,
        template: dict = None,
    ) -> dict:
        """
        Build a video segment JSON.

        Args:
            material_id: Video material ID.
            timeline_start_us: Start position on timeline (microseconds).
            source_start_us: Start position in source video (microseconds).
            duration_us: Segment duration (microseconds).
            template: Existing segment to copy default fields from.
        """
        # Start with template or minimal defaults
        if template:
            segment = template.copy()
        else:
            segment = {
                "clip": {
                    "alpha": 1.0,
                    "flip": {"horizontal": False, "vertical": False},
                    "rotation": 0.0,
                    "scale": {"x": 1.0, "y": 1.0},
                    "transform": {"x": 0.0, "y": 0.0},
                },
                "speed": 1.0,
                "render_index": 0,
            }

        # Override with our values
        segment["id"] = generate_uuid()
        segment["material_id"] = material_id
        segment["target_timerange"] = {"start": timeline_start_us, "duration": duration_us}
        segment["source_timerange"] = {"start": source_start_us, "duration": duration_us}

        return segment

    def _update_duration(self) -> None:
        """Recalculate and update project duration."""
        max_end = 0

        for track in self._content.get("tracks", []):
            for seg in track.get("segments", []):
                target = seg.get("target_timerange", {})
                end = target.get("start", 0) + target.get("duration", 0)
                max_end = max(max_end, end)

        self._content["duration"] = max_end
        self._meta["tm_duration"] = max_end

    def save(self) -> None:
        """Save project to disk."""
        # Update modification time
        current_time = int(time.time())
        self._content["update_time"] = current_time
        self._meta["tm_draft_modified"] = current_time

        # Write content file
        with open(self.content_file, "w", encoding="utf-8") as f:
            json.dump(self._content, f, ensure_ascii=False, indent=2)

        # Write meta file
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)

    def create_copy(self, new_name: str) -> "CapCutProject":
        """
        Create a copy of this project with a new name.

        Args:
            new_name: Name for the copied project.

        Returns:
            New CapCutProject instance for the copy.
        """
        # Generate new project ID
        new_id = generate_uuid()

        # Create new folder
        new_path = self.project_path.parent / new_id
        shutil.copytree(self.project_path, new_path)

        # Load the copy
        copy_project = CapCutProject(new_path)

        # Update IDs and name
        copy_project._content["id"] = new_id
        copy_project._meta["draft_id"] = new_id
        copy_project._meta["draft_root_path"] = str(new_path)
        copy_project.project_name = new_name

        # Save changes
        copy_project.save()

        return copy_project
