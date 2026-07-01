# SmartCut MCP Server — Project Context

## What is this?

MCP server for automated "talking head" video editing. Works with Claude Code to:
- Read CapCut's auto-generated subtitles
- Heuristically find silences (gaps > 1 sec between subtitles)
- Detect duplicate takes (keeps the last one)
- Cut directly in the CapCut project (no backups, no copies)
- Optionally use OpenAI GPT for better duplicate detection

## Project Structure

```
src/smartcut/
├── __init__.py              # Version
├── config.py                # Settings, env vars, constants
├── server.py                # MCP server entry point, 8 tools
├── core/
│   ├── models.py            # Pydantic models (CapCutSubtitleSegment, etc.)
│   ├── whisper_client.py    # OpenAI Whisper API wrapper (optional)
│   ├── llm_client.py        # GPT for duplicate detection (optional)
│   ├── ffmpeg_utils.py      # FFmpeg audio extraction (optional, for Whisper)
│   ├── capcut_reader.py     # CapCut project reader/modifier + subtitle parser
│   └── capcut_finder.py     # CapCut project discovery
└── tools/
    └── capcut_projects.py   # All 8 MCP tools + heuristic analysis engine
```

## Key Files

### config.py
- `Settings` class with env vars: `OPENAI_API_KEY` (optional), `CAPCUT_DRAFTS_DIR`
- Constants: `SILENCE_THRESHOLD_SEC = 1.0`, `DUPLICATE_SIMILARITY_THRESHOLD = 0.6`

### server.py
- 8 MCP tools:
  - `list_capcut_projects`, `open_capcut_project`, `smart_cut_project` (original)
  - `edit_subtitle`, `split_subtitle`, `merge_subtitles`, `fix_word_timing`, `batch_edit_subtitles` (subtitle corrections)

### capcut_reader.py
- `CapCutProject` class for loading/modifying existing CapCut projects
- Key methods: `load()`, `save()`, `get_subtitle_segments()`, `remove_time_ranges()`
- Subtitle corrections: `edit_subtitle_text()`, `edit_subtitle_timing()`, `split_subtitle()`, `merge_subtitles()`, `fix_word_timing()`
- Reads `draft_info.json` (content) and `draft_meta_info.json` (metadata)

### tools/capcut_projects.py
- Main tool: `smart_cut_project()` — the core function
- Heuristic engine: `find_gaps()`, `find_duplicate_takes()`, `compute_text_similarity()`
- Subtitle correction wrappers: `edit_subtitle()`, `split_subtitle()`, `merge_subtitles()`, `fix_word_timing()`, `batch_edit_subtitles()`
- Optional: `_detect_duplicates_with_llm()` for OpenAI-enhanced detection

### capcut_finder.py
- `get_capcut_drafts_dir()` - auto-detects CapCut drafts location
- macOS: `~/Movies/CapCut/User Data/Projects/com.lveditor.draft/`
- Windows: `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\`

## CapCut Format Notes

- Times are in **microseconds** (1 sec = 1,000,000 μs)
- Video segments have `source_timerange` (where in source) and `target_timerange` (where on timeline)
- Text segments have `target_timerange` only (`source_timerange` is null)
- Auto-generated subtitles: `materials.texts[]` with `recognize_task_id != ""`
- Subtitle word timing: `words.start_time[]` / `words.end_time[]` in **milliseconds**, relative to segment start
- Display text is in `content` JSON field (not top-level `text`)
- CapCut monitors drafts folder via FSEvents and may rename/move folders

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| OPENAI_API_KEY | No | - | OpenAI API key (for GPT duplicate detection) |
| CAPCUT_DRAFTS_DIR | No | auto | Path to CapCut drafts folder |

## Running

```bash
cd capcut-ai-editor
python -m venv venv
source venv/bin/activate
pip install -e .
python -m smartcut.server
```

## Common Tasks

### Add new tool
1. Create function in `tools/capcut_projects.py`
2. Add Tool schema in `server.py`
3. Add handler in `call_tool()`

### Debug CapCut issues
- Check `.recycle_bin/` folder in drafts dir — CapCut may move "invalid" projects there
- Verify `draft_info.json` exists (not just `draft_meta_info.json`)
- CapCut may need restart to see changes
