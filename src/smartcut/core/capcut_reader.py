"""CapCut project reader and modifier."""

import copy
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from smartcut.config import MICROSECONDS_PER_SECOND
from smartcut.core.models import (
    CapCutProjectData,
    CapCutSubtitleSegment,
    ExistingTextSegment,
    ExistingVideoMaterial,
    ExistingVideoSegment,
)


def generate_uuid() -> str:
    """Generate a UUID string for CapCut objects."""
    return str(uuid.uuid4()).upper()


@dataclass
class TextStyle:
    """Text styling for subtitle segments."""

    font_size: int = 8
    font_color: str = "#FFFFFF"
    background_color: Optional[str] = "#000000"
    background_alpha: float = 0.6
    position_y: float = 0.8
    bold: bool = False
    font_path: str = ""


class CapCutProject:
    """
    Represents an existing CapCut project.

    Can load, modify, and save CapCut draft projects.
    """

    def __init__(self, project_path: Path):
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
        return self._content.get("id", self.project_path.name)

    @property
    def project_name(self) -> str:
        return self._meta.get("draft_name") or self._content.get("name") or "Untitled"

    @project_name.setter
    def project_name(self, value: str) -> None:
        self._content["name"] = value
        self._meta["draft_name"] = value

    @property
    def duration_us(self) -> int:
        return self._content.get("duration", 0)

    @property
    def duration(self) -> float:
        return self.duration_us / MICROSECONDS_PER_SECOND

    @property
    def canvas_width(self) -> int:
        return self._content.get("canvas_config", {}).get("width", 1080)

    @property
    def canvas_height(self) -> int:
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
        """Get all video segments from video tracks."""
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
                source = seg.get("source_timerange") or {}

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

    def get_subtitle_segments(self) -> list[CapCutSubtitleSegment]:
        """
        Get auto-generated subtitle segments from CapCut.

        CapCut stores auto-subtitles as text materials with:
        - recognize_task_id != "" (marks it as auto-generated)
        - words.text, words.start_time, words.end_time (word-level timing in ms)
        - content JSON field has display text

        Text track segments have target_timerange (microseconds) for absolute position.

        Returns:
            List of CapCutSubtitleSegment sorted by timeline position.
        """
        # Step 1: Collect text materials with recognize_task_id
        subtitle_materials: dict[str, dict] = {}
        for mat in self._content.get("materials", {}).get("texts", []):
            recognize_id = mat.get("recognize_task_id", "")
            if not recognize_id:
                continue

            content_str = mat.get("content", "{}")
            try:
                content = json.loads(content_str)
                display_text = content.get("text", "")
            except json.JSONDecodeError:
                display_text = ""

            words_data = mat.get("words", {})

            subtitle_materials[mat.get("id", "")] = {
                "text": display_text,
                "words_text": words_data.get("text", []),
                "words_start_ms": words_data.get("start_time", []),
                "words_end_ms": words_data.get("end_time", []),
                "recognize_task_id": recognize_id,
            }

        if not subtitle_materials:
            return []

        # Step 2: Find segments on text tracks that reference these materials
        segments = []
        for track in self._content.get("tracks", []):
            if track.get("type") != "text":
                continue
            for seg in track.get("segments", []):
                material_id = seg.get("material_id", "")
                if material_id not in subtitle_materials:
                    continue

                mat_data = subtitle_materials[material_id]
                target = seg.get("target_timerange", {})

                segments.append(
                    CapCutSubtitleSegment(
                        segment_id=seg.get("id", ""),
                        material_id=material_id,
                        text=mat_data["text"],
                        words_text=mat_data["words_text"],
                        words_start_ms=mat_data["words_start_ms"],
                        words_end_ms=mat_data["words_end_ms"],
                        timeline_start_us=target.get("start", 0),
                        timeline_duration_us=target.get("duration", 0),
                        recognize_task_id=mat_data["recognize_task_id"],
                    )
                )

        segments.sort(key=lambda s: s.timeline_start_us)
        return segments

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

    def remove_time_ranges(self, ranges_to_cut: list[tuple[int, int]]) -> None:
        """
        Remove specified time ranges from ALL tracks (video, audio, text).

        For each range to cut:
        - Segments fully inside the range are removed
        - Segments partially overlapping are trimmed/split
        - All subsequent segments are shifted left to close gaps

        Args:
            ranges_to_cut: List of (start_us, end_us) ranges to remove.
                           Must be sorted by start time and non-overlapping.
        """
        if not ranges_to_cut:
            return

        for track in self._content.get("tracks", []):
            segments = track.get("segments", [])
            if not segments:
                continue

            track_type = track.get("type", "")
            new_segments = self._apply_cuts_to_segments(
                segments, ranges_to_cut, track_type,
            )
            track["segments"] = new_segments

        # Also remove text materials that no longer have segments referencing them
        self._cleanup_orphaned_text_materials()

        self._update_duration()

    def _apply_cuts_to_segments(
        self,
        segments: list[dict],
        ranges_to_cut: list[tuple[int, int]],
        track_type: str,
    ) -> list[dict]:
        """
        Apply cut ranges to a list of segments, returning surviving segments
        with adjusted positions.

        For each segment:
        1. Subtract all cut ranges from its time span → remaining pieces
        2. For video/audio: adjust source_timerange for each piece
        3. Shift all pieces left based on total cut duration before them
        """
        surviving = []

        for seg in segments:
            target = seg.get("target_timerange", {})
            seg_start = target.get("start", 0)
            seg_dur = target.get("duration", 0)
            seg_end = seg_start + seg_dur

            if seg_dur <= 0:
                continue

            # Find remaining pieces after subtracting cuts
            pieces = [(seg_start, seg_end)]
            for cut_start, cut_end in ranges_to_cut:
                new_pieces = []
                for piece_start, piece_end in pieces:
                    if cut_end <= piece_start or cut_start >= piece_end:
                        new_pieces.append((piece_start, piece_end))
                    else:
                        if piece_start < cut_start:
                            new_pieces.append((piece_start, cut_start))
                        if piece_end > cut_end:
                            new_pieces.append((cut_end, piece_end))
                pieces = new_pieces

            if not pieces:
                continue

            # Build new segments from remaining pieces
            source = seg.get("source_timerange")
            has_source = source is not None and isinstance(source, dict)
            source_start_us = source.get("start", 0) if has_source else 0

            for piece_start, piece_end in pieces:
                piece_dur = piece_end - piece_start
                if piece_dur <= 0:
                    continue

                new_seg = copy.deepcopy(seg)
                new_seg["id"] = generate_uuid()

                # Calculate shifted target position (close gaps from cuts before this piece)
                shift = _compute_shift(piece_start, ranges_to_cut)
                new_seg["target_timerange"] = {
                    "start": piece_start - shift,
                    "duration": piece_dur,
                }

                # Adjust source_timerange for video/audio (text source_timerange is null)
                if has_source and track_type in ("video", "audio"):
                    offset_from_seg_start = piece_start - seg_start
                    new_seg["source_timerange"] = {
                        "start": source_start_us + offset_from_seg_start,
                        "duration": piece_dur,
                    }

                surviving.append(new_seg)

        return surviving

    def _cleanup_orphaned_text_materials(self) -> None:
        """Remove text materials that are no longer referenced by any segment."""
        referenced_material_ids = set()
        for track in self._content.get("tracks", []):
            if track.get("type") != "text":
                continue
            for seg in track.get("segments", []):
                referenced_material_ids.add(seg.get("material_id", ""))

        texts = self._content.get("materials", {}).get("texts", [])
        self._content["materials"]["texts"] = [
            m for m in texts if m.get("id", "") in referenced_material_ids
        ]

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

        if "texts" not in self._content.get("materials", {}):
            self._content.setdefault("materials", {})["texts"] = []

        text_materials = self._content["materials"]["texts"]

        new_segments = []
        position_toggle = False

        for sub in subtitles:
            start_us = int(sub["start"] * MICROSECONDS_PER_SECOND)
            end_us = int(sub["end"] * MICROSECONDS_PER_SECOND)
            duration_us = end_us - start_us
            text = sub["text"]

            if style.position_y == 0.8:
                position_y = 0.2 if position_toggle else 0.8
                position_toggle = not position_toggle
            else:
                position_y = style.position_y

            material_id = generate_uuid()
            text_material = self._build_text_material(material_id, text, style)
            text_materials.append(text_material)

            segment = self._build_text_segment(material_id, start_us, duration_us, position_y)
            new_segments.append(segment)

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

        text_track["segments"].extend(new_segments)
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

    # ------------------------------------------------------------------
    # Subtitle correction operations
    # ------------------------------------------------------------------

    def _find_segment_by_id(self, segment_id: str) -> dict | None:
        for track in self._content.get("tracks", []):
            for seg in track.get("segments", []):
                if seg.get("id") == segment_id:
                    return seg
        return None

    def _find_material_by_id(self, material_id: str) -> dict | None:
        for mat in self._content.get("materials", {}).get("texts", []):
            if mat.get("id") == material_id:
                return mat
        return None

    def _find_text_track(self) -> dict | None:
        for track in self._content.get("tracks", []):
            if track.get("type") == "text":
                return track
        return None

    def edit_subtitle_text(self, segment_id: str, new_text: str) -> bool:
        """Change subtitle display text, updating content JSON and styles range."""
        seg = self._find_segment_by_id(segment_id)
        if not seg:
            return False
        mat = self._find_material_by_id(seg["material_id"])
        if not mat:
            return False

        content = json.loads(mat.get("content", "{}"))
        content["text"] = new_text
        for style in content.get("styles", []):
            style["range"] = [0, len(new_text)]
        mat["content"] = json.dumps(content)

        words = mat.get("words")
        if words:
            mat["words"] = {"text": [], "start_time": [], "end_time": []}

        return True

    def edit_subtitle_timing(
        self,
        segment_id: str,
        new_start_us: int | None = None,
        new_duration_us: int | None = None,
    ) -> bool:
        """Adjust a subtitle's position and/or duration on the timeline."""
        seg = self._find_segment_by_id(segment_id)
        if not seg:
            return False
        if new_start_us is not None:
            seg["target_timerange"]["start"] = new_start_us
        if new_duration_us is not None:
            seg["target_timerange"]["duration"] = new_duration_us
        self._update_duration()
        return True

    def fix_word_timing(
        self,
        segment_id: str,
        words_text: list[str],
        words_start_ms: list[int],
        words_end_ms: list[int],
    ) -> bool:
        """Replace word-level timing arrays on a subtitle material."""
        if not (len(words_text) == len(words_start_ms) == len(words_end_ms)):
            raise ValueError(
                f"Arrays must be equal length: text={len(words_text)}, "
                f"start={len(words_start_ms)}, end={len(words_end_ms)}"
            )
        seg = self._find_segment_by_id(segment_id)
        if not seg:
            return False
        mat = self._find_material_by_id(seg["material_id"])
        if not mat:
            return False
        mat["words"] = {
            "text": words_text,
            "start_time": words_start_ms,
            "end_time": words_end_ms,
        }
        return True

    def split_subtitle(self, segment_id: str, split_time_us: int) -> bool:
        """Split a subtitle into two at a given timeline point."""
        seg = self._find_segment_by_id(segment_id)
        if not seg:
            return False
        mat = self._find_material_by_id(seg["material_id"])
        if not mat:
            return False

        seg_start = seg["target_timerange"]["start"]
        seg_end = seg_start + seg["target_timerange"]["duration"]

        if split_time_us <= seg_start or split_time_us >= seg_end:
            return False

        ratio = (split_time_us - seg_start) / (seg_end - seg_start)
        content = json.loads(mat.get("content", "{}"))
        words = mat.get("words", {})
        word_texts = words.get("text", [])

        split_idx = self._find_word_split_index(words, ratio)
        if split_idx <= 0 or split_idx >= len(word_texts):
            split_idx = max(1, len(word_texts) // 2)

        text_a = " ".join(word_texts[:split_idx]) if word_texts else content.get("text", "")
        text_b = " ".join(word_texts[split_idx:]) if word_texts else ""

        if not text_a or not text_b:
            return False

        # --- Modify existing material (part A) ---
        content["text"] = text_a
        for style in content.get("styles", []):
            style["range"] = [0, len(text_a)]
        mat["content"] = json.dumps(content)
        if word_texts:
            mat["words"] = {
                "text": word_texts[:split_idx],
                "start_time": words.get("start_time", [])[:split_idx],
                "end_time": words.get("end_time", [])[:split_idx],
            }
        dur_a = split_time_us - seg_start
        seg["target_timerange"]["duration"] = dur_a

        # --- Create new material (part B) via deepcopy ---
        new_mat = copy.deepcopy(mat)
        new_mat_id = generate_uuid()
        new_mat["id"] = new_mat_id
        content_b = json.loads(new_mat.get("content", "{}"))
        content_b["text"] = text_b
        for style in content_b.get("styles", []):
            style["range"] = [0, len(text_b)]
        new_mat["content"] = json.dumps(content_b)
        if word_texts:
            new_mat["words"] = {
                "text": word_texts[split_idx:],
                "start_time": words.get("start_time", [])[split_idx:],
                "end_time": words.get("end_time", [])[split_idx:],
            }
        self._content["materials"]["texts"].append(new_mat)

        # --- Create new segment (part B) ---
        new_seg = copy.deepcopy(seg)
        new_seg["id"] = generate_uuid()
        new_seg["material_id"] = new_mat_id
        new_seg["target_timerange"] = {
            "start": split_time_us,
            "duration": seg_end - split_time_us,
        }

        track = self._find_text_track()
        if track:
            idx = next(
                (i for i, s in enumerate(track["segments"]) if s.get("id") == seg.get("id")),
                len(track["segments"]) - 1,
            )
            track["segments"].insert(idx + 1, new_seg)

        self._update_duration()
        return True

    def merge_subtitles(self, segment_id_a: str, segment_id_b: str) -> bool:
        """Merge two subtitles into one, extending A to cover B's range."""
        seg_a = self._find_segment_by_id(segment_id_a)
        seg_b = self._find_segment_by_id(segment_id_b)
        if not seg_a or not seg_b:
            return False

        mat_a = self._find_material_by_id(seg_a["material_id"])
        mat_b = self._find_material_by_id(seg_b["material_id"])
        if not mat_a or not mat_b:
            return False

        content_a = json.loads(mat_a.get("content", "{}"))
        content_b = json.loads(mat_b.get("content", "{}"))
        merged_text = f"{content_a.get('text', '')} {content_b.get('text', '')}"
        content_a["text"] = merged_text
        for style in content_a.get("styles", []):
            style["range"] = [0, len(merged_text)]
        mat_a["content"] = json.dumps(content_a)

        words_a = mat_a.get("words", {})
        words_b = mat_b.get("words", {})
        if words_a.get("text") and words_b.get("text"):
            offset_us = seg_b["target_timerange"]["start"] - seg_a["target_timerange"]["start"]
            offset_ms = offset_us // 1000
            mat_a["words"] = {
                "text": words_a.get("text", []) + words_b.get("text", []),
                "start_time": (
                    words_a.get("start_time", [])
                    + [t + offset_ms for t in words_b.get("start_time", [])]
                ),
                "end_time": (
                    words_a.get("end_time", [])
                    + [t + offset_ms for t in words_b.get("end_time", [])]
                ),
            }

        seg_b_end = seg_b["target_timerange"]["start"] + seg_b["target_timerange"]["duration"]
        seg_a["target_timerange"]["duration"] = seg_b_end - seg_a["target_timerange"]["start"]

        track = self._find_text_track()
        if track:
            track["segments"] = [s for s in track["segments"] if s.get("id") != seg_b.get("id")]

        self._cleanup_orphaned_text_materials()
        self._update_duration()
        return True

    @staticmethod
    def _find_word_split_index(words: dict, ratio: float) -> int:
        word_texts = words.get("text", [])
        end_times = words.get("end_time", [])
        if not word_texts:
            return 1
        if not end_times:
            return max(1, int(len(word_texts) * ratio))
        total_dur = end_times[-1] if end_times[-1] > 0 else 1
        target_ms = int(total_dur * ratio)
        for i, t in enumerate(words.get("start_time", [])):
            if t >= target_ms:
                return max(1, i)
        return max(1, len(word_texts) // 2)

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
        current_time = int(time.time())
        self._content["update_time"] = current_time
        self._meta["tm_draft_modified"] = current_time

        with open(self.content_file, "w", encoding="utf-8") as f:
            json.dump(self._content, f, ensure_ascii=False, indent=2)

        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)


def _compute_shift(position_us: int, ranges_to_cut: list[tuple[int, int]]) -> int:
    """
    Compute how much a position should shift left due to cuts before it.

    For a given timeline position, sum up the durations of all cut ranges
    that end before (or overlap with) that position.
    """
    shift = 0
    for cut_start, cut_end in ranges_to_cut:
        if cut_start >= position_us:
            break
        shift += min(cut_end, position_us) - cut_start
    return shift
