# SmartCut MCP Server — TODO

## Legend
- [ ] — pending
- [x] — done

---

## Phase 1: Project Setup

### 1.1 Project Initialization
- [x] Create directory structure:
  ```
  src/smartcut/
  src/smartcut/core/
  src/smartcut/tools/
  ```
- [x] Create pyproject.toml with metadata and dependencies
- [x] Create requirements.txt (for pip install)
- [x] Add LICENSE (MIT)

### 1.2 Configuration (src/smartcut/config.py)
- [x] Define Settings class (pydantic-settings)
- [x] Environment variables:
  - [x] OPENAI_API_KEY (required)
  - [x] AUPHONIC_API_KEY (optional)
  - [x] AUPHONIC_PRESET_UUID (optional)
  - [x] CAPCUT_DRAFTS_DIR (optional, auto-detect)
- [x] Default constants:
  - [x] SILENCE_THRESHOLD_SEC = 3.0
  - [x] MIN_SEGMENT_DURATION_SEC = 0.5
  - [x] SUBTITLE_MAX_WORDS = 8
  - [x] SUBTITLE_MAX_CHARS = 45
  - [x] TARGET_LUFS = -16.0
  - [x] WHISPER_MODEL = "whisper-1"
  - [x] LLM_MODEL = "gpt-4o-mini"
- [x] Auto-detect CapCut drafts directory (macOS/Windows)

---

## Phase 2: Core Infrastructure

### 2.1 Data Models (src/smartcut/core/models.py)
- [x] TranscriptionWord
- [x] TranscriptionSegment
- [x] Transcription
- [x] Paragraph
- [x] CutSegment
- [x] CutPlan
- [x] CutStats
- [x] SubtitleLine
- [x] DuplicateGroup, DuplicateGroups
- [x] MediaInfo, LoudnessInfo

### 2.2 Whisper Client (src/smartcut/core/whisper_client.py)
- [x] WhisperClient class
- [x] Handle audio > 25MB (error message with guidance)
- [x] Retry logic (3 attempts, exponential backoff)
- [x] Request word-level timestamps (timestamp_granularities)

### 2.3 LLM Client (src/smartcut/core/llm_client.py)
- [x] LLMClient class
- [x] detect_duplicates() method
- [x] identify_accent_words() method
- [x] Prompt for duplicate detection
- [x] Prompt for accent words identification
- [x] JSON mode for structured output

### 2.4 Auphonic Client (src/smartcut/core/auphonic_client.py)
- [x] AuphonicClient class
- [x] create_production() method
- [x] poll_status() method
- [x] download_result() method
- [x] Handle missing API key gracefully
- [x] Polling with timeout

### 2.5 FFmpeg Utils (src/smartcut/core/ffmpeg_utils.py)
- [x] check_ffmpeg_installed()
- [x] get_media_info()
- [x] extract_audio()
- [x] cut_segment()
- [x] concat_segments()
- [x] measure_loudness()
- [x] normalize_audio()
- [x] mux_audio_video()

### 2.6 CapCut Draft Generator (src/smartcut/core/capcut_draft.py)
- [x] CapCutDraft class
- [x] add_video_material()
- [x] add_video_segment()
- [x] add_text_material()
- [x] add_text_segment()
- [x] save()
- [x] TextStyle dataclass
- [x] Generate draft_meta_info.json
- [x] Generate draft_content.json
- [x] UUID generation for segments/materials

---

## Phase 3: MCP Tools

### 3.1 Transcribe Tool (src/smartcut/tools/transcribe.py)
- [x] transcribe() async function
- [x] Input: file_path, language (optional)
- [x] Extract audio via FFmpeg
- [x] Call WhisperClient.transcribe()
- [x] Error handling

### 3.2 Analyze Tool (src/smartcut/tools/analyze.py)
- [x] analyze_content() async function
- [x] find_paragraphs() - split by pauses
- [x] detect_duplicates_in_paragraphs() - LLM detection
- [x] build_cut_plan() - create CutPlan

### 3.3 Smart Cut Tool (src/smartcut/tools/smart_cut.py)
- [x] smart_cut() async function - main orchestrator
- [x] Call transcribe → analyze → export
- [x] Support output_format: capcut, video, both
- [x] Return comprehensive result

### 3.4 CapCut Export Tool (src/smartcut/tools/capcut_export.py)
- [x] generate_capcut_project() async function
- [x] Get video info
- [x] Create CapCutDraft with segments
- [x] Add subtitles if requested
- [x] Save to drafts directory

### 3.5 Video Export Tool (src/smartcut/tools/video_export.py)
- [x] export_video() async function
- [x] Cut segments with FFmpeg
- [x] Concatenate segments
- [x] Preserve original format

### 3.6 Subtitles Tool (src/smartcut/tools/subtitles.py)
- [x] generate_subtitles() async function
- [x] map_words_to_timeline()
- [x] group_words_into_lines()
- [x] Generate SRT file
- [x] Identify accent words for dynamic style

### 3.7 Audio Enhance Tool (src/smartcut/tools/audio_enhance.py)
- [x] enhance_audio() async function
- [x] Auphonic integration
- [x] Error handling for missing API key

### 3.8 Audio Normalize Tool (src/smartcut/tools/audio_normalize.py)
- [x] normalize_audio_loudness() async function
- [x] Two-pass loudnorm filter
- [x] Return loudness info

---

## Phase 4: MCP Server

### 4.1 Server Entry Point (src/smartcut/server.py)
- [x] Import all tools
- [x] Create MCP server instance
- [x] Register all 12 tools with schemas (8 original + 4 existing project tools)
- [x] Setup stdio transport
- [x] Handle startup errors (FFmpeg check)
- [x] call_tool() handler

### 4.2 Package Init (src/smartcut/__init__.py)
- [x] Version string

---

## Phase 4.5: Existing CapCut Project Support

### 4.5.1 Project Discovery (src/smartcut/core/capcut_finder.py)
- [x] get_capcut_drafts_dir() - auto-detect on macOS/Windows/Linux
- [x] list_projects() - list all projects with metadata
- [x] find_project_by_name() - search by name (partial match)

### 4.5.2 Project Reader (src/smartcut/core/capcut_reader.py)
- [x] CapCutProject class
- [x] Load draft_content.json and draft_meta_info.json
- [x] get_video_materials() - parse video materials
- [x] get_video_segments() - parse video track segments
- [x] get_text_segments() - parse text tracks
- [x] add_text_track() - add subtitles
- [x] update_video_segments() - modify video segments
- [x] create_copy() - backup project with new name
- [x] save() - write changes to disk

### 4.5.3 Data Models (src/smartcut/core/models.py)
- [x] ProjectInfo
- [x] ExistingVideoSegment
- [x] ExistingVideoMaterial
- [x] ExistingTextSegment
- [x] CapCutProjectData

### 4.5.4 MCP Tools (src/smartcut/tools/capcut_projects.py)
- [x] list_capcut_projects() - list all projects
- [x] open_capcut_project() - open and return structure
- [x] add_subtitles_to_project() - add subtitles with backup
- [x] smart_cut_project() - apply smart_cut with backup

---

## Phase 5: Testing

### 5.1 Unit Tests
- [ ] test_config.py — settings loading
- [ ] test_models.py — Pydantic models validation
- [ ] test_ffmpeg_utils.py — FFmpeg helpers (mock subprocess)
- [ ] test_capcut_draft.py — draft JSON generation

### 5.2 Integration Tests
- [ ] test_whisper_client.py — real API call (skip without key)
- [ ] test_llm_client.py — real API call (skip without key)
- [ ] test_full_pipeline.py — end-to-end with test video

### 5.3 Manual Testing Checklist
- [ ] Short video (30 sec, no duplicates) — basic silence removal
- [ ] Medium video (5 min, 3-4 duplicate takes) — duplicate detection
- [ ] Long video (15+ min) — chunked transcription
- [ ] MOV from iPhone — format preservation
- [ ] MP4 file — standard handling
- [ ] Russian language — correct transcription
- [ ] English language — multilingual support
- [ ] CapCut project opens on Mac
- [ ] Subtitles display correctly
- [ ] Dynamic subtitle styling (accent colors, positions)
- [ ] Auphonic integration (with valid API key)
- [ ] Graceful failure without Auphonic key
- [ ] Audio normalization via FFmpeg

### 5.4 Existing CapCut Project Testing
- [ ] list_capcut_projects — finds projects on macOS
- [ ] list_capcut_projects — finds projects on Windows
- [ ] open_capcut_project — returns correct structure
- [ ] add_subtitles_to_project — creates backup copy
- [ ] add_subtitles_to_project — subtitles appear in CapCut
- [ ] smart_cut_project — creates backup copy
- [ ] smart_cut_project — cuts applied to all video clips
- [ ] Original project remains untouched after modification

---

## Phase 6: Documentation

### 6.1 README.md
- [x] Project description
- [x] Requirements (Python, FFmpeg)
- [x] Installation
- [x] Claude Desktop setup
- [x] Usage examples
- [x] Environment variables

### 6.2 Inline Documentation
- [x] Docstrings for public API
- [x] Type hints everywhere

---

## Blockers & Risks

1. **CapCut draft format** — may change in newer CapCut versions
   - Mitigation: study pyCapCut/VectCutAPI, test on real CapCut

2. **Whisper API limits** — 25MB max file size
   - Mitigation: chunking with overlap

3. **LLM duplicate detection** — may make mistakes
   - Mitigation: conservative approach, user can edit in CapCut

4. **FFmpeg dependency** — must be installed
   - Mitigation: clear error message with installation instructions
