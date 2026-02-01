"""Pydantic data models for SmartCut."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# Transcription models

class TranscriptionWord(BaseModel):
    """A single word with timestamps."""

    word: str
    start: float
    end: float


class TranscriptionSegment(BaseModel):
    """A segment of transcription (usually a sentence or phrase)."""

    id: int
    start: float
    end: float
    text: str
    words: list[TranscriptionWord] = Field(default_factory=list)


class Transcription(BaseModel):
    """Complete transcription result."""

    language: str
    duration: float
    segments: list[TranscriptionSegment] = Field(default_factory=list)

    def get_all_words(self) -> list[TranscriptionWord]:
        """Get flat list of all words across all segments."""
        words = []
        for segment in self.segments:
            words.extend(segment.words)
        return words


# Analysis models

class Paragraph(BaseModel):
    """A paragraph identified in the transcription."""

    id: int
    start: float
    end: float
    text: str
    action: Literal["keep", "remove"]
    reason: str
    group_id: Optional[int] = None


class CutSegment(BaseModel):
    """A segment to keep or remove in the final cut."""

    start: float
    end: float
    start_word: str = ""
    end_word: str = ""
    reason: Optional[str] = None


class CutStats(BaseModel):
    """Statistics about the cut plan."""

    original_duration: float
    kept_duration: float
    removed_duration: float
    duplicates_removed: int = 0
    silences_removed: int = 0

    @property
    def time_saved_formatted(self) -> str:
        """Format removed duration as MM:SS."""
        minutes = int(self.removed_duration // 60)
        seconds = int(self.removed_duration % 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def original_duration_formatted(self) -> str:
        """Format original duration as MM:SS."""
        minutes = int(self.original_duration // 60)
        seconds = int(self.original_duration % 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def kept_duration_formatted(self) -> str:
        """Format kept duration as MM:SS."""
        minutes = int(self.kept_duration // 60)
        seconds = int(self.kept_duration % 60)
        return f"{minutes}:{seconds:02d}"


class CutPlan(BaseModel):
    """Plan for cutting the video."""

    keep_segments: list[CutSegment] = Field(default_factory=list)
    remove_segments: list[CutSegment] = Field(default_factory=list)
    stats: CutStats


class AnalysisResult(BaseModel):
    """Complete analysis result."""

    paragraphs: list[Paragraph] = Field(default_factory=list)
    cut_plan: CutPlan


# Subtitle models

class SubtitleLine(BaseModel):
    """A single subtitle line."""

    start: float
    end: float
    text: str
    accent_words: list[str] = Field(default_factory=list)
    position: Literal["top", "bottom"] = "bottom"


# Duplicate detection models

class DuplicateGroup(BaseModel):
    """A group of duplicate paragraphs."""

    block_ids: list[int]
    keep: int
    remove: list[int]
    reason: str


class DuplicateGroups(BaseModel):
    """Result of duplicate detection."""

    groups: list[DuplicateGroup] = Field(default_factory=list)


# Media info models

class MediaInfo(BaseModel):
    """Information about a media file."""

    duration: float
    width: int
    height: int
    fps: float = 30.0
    audio_sample_rate: int = 44100
    format: str = "mov"


class LoudnessInfo(BaseModel):
    """Audio loudness measurement."""

    input_i: float  # Integrated loudness (LUFS)
    input_tp: float  # True peak (dB)
    input_lra: float  # Loudness range
    input_thresh: float  # Threshold
    target_offset: float = 0.0


# CapCut project models

class ProjectInfo(BaseModel):
    """CapCut project metadata."""

    name: str
    path: str
    project_id: str
    duration_us: int
    duration_formatted: str
    modified_time: int
    video_count: int = 0
    has_content: bool = True  # Whether draft_content.json exists (project can be modified)


class ExistingVideoSegment(BaseModel):
    """Video segment from existing CapCut project."""

    id: str
    material_id: str
    source_path: str
    timeline_start: float  # seconds
    timeline_end: float  # seconds
    source_start: float  # seconds
    source_end: float  # seconds
    duration: float  # seconds


class ExistingVideoMaterial(BaseModel):
    """Video material from existing CapCut project."""

    id: str
    path: str
    duration: float  # seconds
    width: int
    height: int


class ExistingTextSegment(BaseModel):
    """Text segment from existing CapCut project."""

    id: str
    material_id: str
    text: str
    timeline_start: float  # seconds
    timeline_end: float  # seconds


class CapCutProjectData(BaseModel):
    """Parsed CapCut project structure."""

    project_id: str
    project_name: str
    project_path: str
    duration: float  # seconds
    canvas_width: int
    canvas_height: int
    video_materials: list[ExistingVideoMaterial] = Field(default_factory=list)
    video_segments: list[ExistingVideoSegment] = Field(default_factory=list)
    text_segments: list[ExistingTextSegment] = Field(default_factory=list)
