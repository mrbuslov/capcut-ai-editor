"""CapCut draft project generator."""

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from smartcut.config import MICROSECONDS_PER_SECOND


def generate_uuid() -> str:
    """Generate a UUID string for CapCut objects."""
    return str(uuid.uuid4()).upper()


def generate_id() -> str:
    """Generate a numeric-like ID string."""
    return str(uuid.uuid4().int)[:19]


@dataclass
class TextStyle:
    """Style configuration for text/subtitle segments."""

    font_size: int = 8
    font_color: str = "#FFFFFF"
    background_color: Optional[str] = "#000000"
    background_alpha: float = 0.6
    position_y: float = 0.8  # 0.0 = top, 1.0 = bottom
    bold: bool = False
    font_path: str = ""


@dataclass
class VideoSegment:
    """Video segment on timeline."""

    id: str
    material_id: str
    timeline_start_us: int
    source_start_us: int
    duration_us: int


@dataclass
class TextSegment:
    """Text segment on timeline."""

    id: str
    material_id: str
    timeline_start_us: int
    duration_us: int


@dataclass
class VideoMaterial:
    """Video material definition."""

    id: str
    file_path: str
    duration_us: int
    width: int
    height: int


@dataclass
class TextMaterial:
    """Text material definition."""

    id: str
    text: str
    style: TextStyle


class CapCutDraft:
    """Generator for CapCut draft project files."""

    def __init__(
        self,
        project_name: str,
        canvas_width: int = 1080,
        canvas_height: int = 1920,
    ):
        self.project_name = project_name
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.project_id = generate_uuid()

        self.video_materials: list[VideoMaterial] = []
        self.text_materials: list[TextMaterial] = []
        self.video_segments: list[VideoSegment] = []
        self.text_segments: list[TextSegment] = []

    def add_video_material(
        self,
        file_path: Path,
        duration_us: int,
        width: int,
        height: int,
    ) -> str:
        """Add a video material and return its ID."""
        material_id = generate_uuid()
        self.video_materials.append(
            VideoMaterial(
                id=material_id,
                file_path=str(file_path.absolute()),
                duration_us=duration_us,
                width=width,
                height=height,
            )
        )
        return material_id

    def add_video_segment(
        self,
        material_id: str,
        timeline_start_us: int,
        source_start_us: int,
        duration_us: int,
    ) -> str:
        """Add a video segment to the timeline."""
        segment_id = generate_uuid()
        self.video_segments.append(
            VideoSegment(
                id=segment_id,
                material_id=material_id,
                timeline_start_us=timeline_start_us,
                source_start_us=source_start_us,
                duration_us=duration_us,
            )
        )
        return segment_id

    def add_text_material(self, text: str, style: Optional[TextStyle] = None) -> str:
        """Add a text material and return its ID."""
        material_id = generate_uuid()
        self.text_materials.append(
            TextMaterial(
                id=material_id,
                text=text,
                style=style or TextStyle(),
            )
        )
        return material_id

    def add_text_segment(
        self,
        material_id: str,
        timeline_start_us: int,
        duration_us: int,
    ) -> str:
        """Add a text segment to the timeline."""
        segment_id = generate_uuid()
        self.text_segments.append(
            TextSegment(
                id=segment_id,
                material_id=material_id,
                timeline_start_us=timeline_start_us,
                duration_us=duration_us,
            )
        )
        return segment_id

    def _calculate_total_duration(self) -> int:
        """Calculate total timeline duration in microseconds."""
        max_end = 0
        for seg in self.video_segments:
            end = seg.timeline_start_us + seg.duration_us
            max_end = max(max_end, end)
        for seg in self.text_segments:
            end = seg.timeline_start_us + seg.duration_us
            max_end = max(max_end, end)
        return max_end

    def _build_video_material_json(self, material: VideoMaterial) -> dict:
        """Build JSON for a video material."""
        return {
            "id": material.id,
            "type": "video",
            "path": material.file_path,
            "duration": material.duration_us,
            "width": material.width,
            "height": material.height,
            "category_id": "",
            "category_name": "local",
            "create_time": int(time.time()),
            "extra_info": "",
            "import_time": int(time.time()),
            "import_time_ms": int(time.time() * 1000),
            "local_material_id": generate_id(),
            "material_id": material.id,
            "material_name": Path(material.file_path).name,
            "media_path": "",
            "metetype": "video",
            "roughcut_time_range": {
                "duration": material.duration_us,
                "start": 0,
            },
            "sub_time_range": {
                "duration": -1,
                "start": -1,
            },
        }

    def _build_video_segment_json(self, segment: VideoSegment) -> dict:
        """Build JSON for a video segment."""
        return {
            "id": segment.id,
            "material_id": segment.material_id,
            "target_timerange": {
                "start": segment.timeline_start_us,
                "duration": segment.duration_us,
            },
            "source_timerange": {
                "start": segment.source_start_us,
                "duration": segment.duration_us,
            },
            "cartoon": False,
            "clip": {
                "alpha": 1.0,
                "flip": {"horizontal": False, "vertical": False},
                "rotation": 0.0,
                "scale": {"x": 1.0, "y": 1.0},
                "transform": {"x": 0.0, "y": 0.0},
            },
            "common_keyframes": [],
            "enable_adjust": True,
            "enable_color_correct_adjust": False,
            "enable_color_curves": True,
            "enable_color_match_adjust": False,
            "enable_color_wheels": True,
            "enable_hsl": False,
            "enable_lut": False,
            "extra_material_refs": [],
            "group_id": "",
            "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
            "intensifies_audio": False,
            "is_placeholder": False,
            "is_tone_modify": False,
            "keyframe_refs": [],
            "last_nonzero_volume": 1.0,
            "render_index": 0,
            "responsive_layout": {
                "enable": False,
                "horizontal_pos_layout": 0,
                "size_layout": 0,
                "target_follow": "",
                "vertical_pos_layout": 0,
            },
            "reverse": False,
            "speed": 1.0,
            "template_id": "",
            "template_scene": "default",
            "track_attribute": 0,
            "track_render_index": 0,
            "uniform_scale": {"on": True, "value": 1.0},
            "visible": True,
            "volume": 1.0,
        }

    def _build_text_material_json(self, material: TextMaterial) -> dict:
        """Build JSON for a text material."""
        style = material.style

        # Build content with potential styling
        content = {
            "styles": [
                {
                    "fill": {
                        "alpha": 1.0,
                        "content": {"render_type": "solid", "solid": {"color": [1.0, 1.0, 1.0]}},
                    },
                    "font": {
                        "id": "",
                        "path": style.font_path,
                    },
                    "range": [0, len(material.text)],
                    "size": style.font_size,
                }
            ],
            "text": material.text,
        }

        return {
            "id": material.id,
            "type": "text",
            "add_type": 0,
            "alignment": 1,
            "background_alpha": style.background_alpha,
            "background_color": style.background_color or "",
            "background_height": 0.14,
            "background_horizontal_offset": 0.0,
            "background_round_radius": 0.0,
            "background_style": 0 if not style.background_color else 1,
            "background_vertical_offset": 0.0,
            "background_width": 0.14,
            "bold_width": 0.0 if not style.bold else 1.0,
            "border_alpha": 1.0,
            "border_color": "",
            "border_width": 0.08,
            "caption_template_info": {
                "category_id": "",
                "category_name": "",
                "effect_id": "",
                "is_new": False,
                "path": "",
                "request_id": "",
                "resource_id": "",
                "resource_name": "",
                "source_platform": 0,
            },
            "check_flag": 7,
            "combo_info": {"text_templates": []},
            "content": json.dumps(content),
            "fixed_height": -1.0,
            "fixed_width": -1.0,
            "font_category_id": "",
            "font_category_name": "",
            "font_id": "",
            "font_name": "",
            "font_path": style.font_path,
            "font_resource_id": "",
            "font_size": style.font_size,
            "font_source_platform": 0,
            "font_team_id": "",
            "font_title": "",
            "font_url": "",
            "fonts": [],
            "force_apply_line_max_width": False,
            "global_alpha": 1.0,
            "group_id": "",
            "has_shadow": False,
            "initial_scale": 1.0,
            "inner_padding": -1.0,
            "is_rich_text": False,
            "italic_degree": 0,
            "ktv_color": "",
            "language": "",
            "layer_weight": 1,
            "letter_spacing": 0.0,
            "line_feed": 1,
            "line_max_width": 0.82,
            "line_spacing": 0.02,
            "multi_language_current": "none",
            "name": "",
            "original_size": [],
            "preset_category": "",
            "preset_category_id": "",
            "preset_has_set_alignment": False,
            "preset_id": "",
            "preset_index": 0,
            "preset_name": "",
            "recognize_task_id": "",
            "recognize_type": 0,
            "relevance_segment": [],
            "shadow_alpha": 0.9,
            "shadow_angle": -45.0,
            "shadow_color": "",
            "shadow_distance": 5.0,
            "shadow_point": {"x": 0.6363961030678928, "y": -0.6363961030678928},
            "shadow_smoothing": 0.45,
            "shape_clip_x": False,
            "shape_clip_y": False,
            "source_from": "",
            "style_name": "",
            "sub_type": 0,
            "subtitle_keywords": None,
            "text_alpha": 1.0,
            "text_color": style.font_color,
            "text_curve": None,
            "text_preset_resource_id": "",
            "text_size": style.font_size,
            "text_to_audio_ids": [],
            "tts_auto_update": False,
            "type": "text",
            "typesetting": 0,
            "underline": False,
            "underline_offset": 0.22,
            "underline_width": 0.05,
            "use_effect_default_color": True,
            "words": {"end_time": [], "start_time": [], "text": []},
        }

    def _build_text_segment_json(self, segment: TextSegment) -> dict:
        """Build JSON for a text segment."""
        # Find the corresponding material to get position
        material = next(
            (m for m in self.text_materials if m.id == segment.material_id),
            None
        )
        position_y = material.style.position_y if material else 0.8

        return {
            "id": segment.id,
            "material_id": segment.material_id,
            "target_timerange": {
                "start": segment.timeline_start_us,
                "duration": segment.duration_us,
            },
            "source_timerange": {
                "start": 0,
                "duration": segment.duration_us,
            },
            "cartoon": False,
            "clip": {
                "alpha": 1.0,
                "flip": {"horizontal": False, "vertical": False},
                "rotation": 0.0,
                "scale": {"x": 1.0, "y": 1.0},
                "transform": {"x": 0.0, "y": position_y - 0.5},  # Center-relative
            },
            "common_keyframes": [],
            "enable_adjust": False,
            "enable_color_correct_adjust": False,
            "enable_color_curves": True,
            "enable_color_match_adjust": False,
            "enable_color_wheels": True,
            "enable_hsl": False,
            "enable_lut": False,
            "extra_material_refs": [],
            "group_id": "",
            "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
            "intensifies_audio": False,
            "is_placeholder": False,
            "is_tone_modify": False,
            "keyframe_refs": [],
            "last_nonzero_volume": 1.0,
            "render_index": 11000,
            "responsive_layout": {
                "enable": False,
                "horizontal_pos_layout": 0,
                "size_layout": 0,
                "target_follow": "",
                "vertical_pos_layout": 0,
            },
            "reverse": False,
            "speed": 1.0,
            "template_id": "",
            "template_scene": "default",
            "track_attribute": 0,
            "track_render_index": 0,
            "uniform_scale": {"on": True, "value": 1.0},
            "visible": True,
            "volume": 1.0,
        }

    def build_draft_content(self) -> dict:
        """Build the complete draft_content.json structure."""
        total_duration = self._calculate_total_duration()

        # Build materials
        video_materials_json = [
            self._build_video_material_json(m) for m in self.video_materials
        ]
        text_materials_json = [
            self._build_text_material_json(m) for m in self.text_materials
        ]

        # Build tracks
        video_track = {
            "attribute": 0,
            "flag": 0,
            "id": generate_uuid(),
            "is_default_name": True,
            "name": "",
            "segments": [self._build_video_segment_json(s) for s in self.video_segments],
            "type": "video",
        }

        tracks = [video_track]

        if self.text_segments:
            text_track = {
                "attribute": 0,
                "flag": 0,
                "id": generate_uuid(),
                "is_default_name": True,
                "name": "",
                "segments": [self._build_text_segment_json(s) for s in self.text_segments],
                "type": "text",
            }
            tracks.append(text_track)

        return {
            "canvas_config": {
                "height": self.canvas_height,
                "ratio": "original",
                "width": self.canvas_width,
            },
            "color_space": 0,
            "config": {"adjust_max_index": 1, "attachment_info": [], "combination_max_index": 1, "export_range": None, "extract_audio_last_index": 1, "lyrics_recognition_id": "", "lyrics_sync": True, "lyrics_taskinfo": [], "maintrack_adsorb": True, "material_save_mode": 0, "multi_language_current": "none", "multi_language_list": [], "multi_language_main": "none", "multi_language_mode": "none", "original_sound_last_index": 1, "record_audio_last_index": 1, "sticker_max_index": 1, "subtitle_keywords_config": None, "subtitle_recognition_id": "", "subtitle_sync": True, "subtitle_taskinfo": [], "system_font_list": [], "text_animation_last_index": 1, "text_to_audio_ids": [], "video_mute": False, "zoom_info_params": None},
            "cover": "",
            "create_time": int(time.time()),
            "duration": total_duration,
            "extra_info": "",
            "fps": 30.0,
            "free_render_index_mode_on": False,
            "group_container": None,
            "id": self.project_id,
            "keyframe_graph_list": [],
            "keyframes": {"adjusts": [], "audios": [], "effects": [], "filters": [], "handwrites": [], "stickers": [], "texts": [], "videos": []},
            "last_modified_platform": {"app_id": 0, "app_source": "", "app_version": "", "device_id": "", "hard_disk_id": "", "mac_address": "", "os": "mac", "os_version": ""},
            "materials": {
                "adjusts": [],
                "audio_balances": [],
                "audio_effects": [],
                "audio_fades": [],
                "audio_track_indexes": [],
                "audios": [],
                "beats": [],
                "canvases": [],
                "chromas": [],
                "color_curves": [],
                "digital_humans": [],
                "drafts": [],
                "effects": [],
                "flowers": [],
                "green_screens": [],
                "handwrites": [],
                "hsl": [],
                "images": [],
                "log_color_wheels": [],
                "loudnesses": [],
                "manual_deformations": [],
                "masks": [],
                "material_animations": [],
                "material_colors": [],
                "multi_language_refs": [],
                "placeholders": [],
                "plugin_effects": [],
                "primary_color_wheels": [],
                "realtime_denoises": [],
                "shapes": [],
                "smart_crops": [],
                "smart_relights": [],
                "sound_channel_mappings": [],
                "speeds": [],
                "stickers": [],
                "tail_leaders": [],
                "text_templates": [],
                "texts": text_materials_json,
                "time_marks": [],
                "transitions": [],
                "video_effects": [],
                "video_trackings": [],
                "videos": video_materials_json,
                "vocal_beautifys": [],
                "vocal_separations": [],
            },
            "mutable_config": None,
            "name": self.project_name,
            "new_version": "113.0.0",
            "platform": {"app_id": 0, "app_source": "", "app_version": "", "device_id": "", "hard_disk_id": "", "mac_address": "", "os": "mac", "os_version": ""},
            "relationships": [],
            "render_index_track_mode_on": False,
            "retouch_cover": None,
            "source": "default",
            "static_cover_image_path": "",
            "tracks": tracks,
            "update_time": int(time.time()),
            "version": 360000,
        }

    def build_draft_meta_info(self, root_path: str) -> dict:
        """Build the draft_meta_info.json structure."""
        total_duration = self._calculate_total_duration()
        current_time = int(time.time())

        return {
            "draft_cloud_capcut_purchase_info": "",
            "draft_cloud_last_action_download": False,
            "draft_cloud_materials": [],
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cover": "",
            "draft_deeplink_url": "",
            "draft_enterprise_info": {},
            "draft_fold_path": "",
            "draft_id": self.project_id,
            "draft_is_ai_shorts": False,
            "draft_is_article_video_draft": False,
            "draft_is_from_deeplink": "",
            "draft_is_invisible": False,
            "draft_materials_copied": False,
            "draft_name": self.project_name,
            "draft_new_version": "",
            "draft_removable_storage_device": "",
            "draft_root_path": root_path,
            "draft_segment_extra_info": "",
            "draft_timeline_materials_size_": 0,
            "tm_draft_cloud_completed": 0,
            "tm_draft_cloud_modified": 0,
            "tm_draft_create": current_time,
            "tm_draft_modified": current_time,
            "tm_duration": total_duration,
        }

    def save(self, output_dir: Path) -> Path:
        """
        Save the draft project to a directory.

        Args:
            output_dir: Base directory for CapCut drafts.

        Returns:
            Path to the created project folder.
        """
        # Create project folder with UUID
        project_folder = output_dir / self.project_id
        project_folder.mkdir(parents=True, exist_ok=True)

        # Save draft_content.json
        draft_content = self.build_draft_content()
        draft_content_path = project_folder / "draft_content.json"
        with open(draft_content_path, "w", encoding="utf-8") as f:
            json.dump(draft_content, f, ensure_ascii=False, indent=2)

        # Save draft_meta_info.json
        draft_meta = self.build_draft_meta_info(str(project_folder.absolute()))
        draft_meta_path = project_folder / "draft_meta_info.json"
        with open(draft_meta_path, "w", encoding="utf-8") as f:
            json.dump(draft_meta, f, ensure_ascii=False, indent=2)

        return project_folder
