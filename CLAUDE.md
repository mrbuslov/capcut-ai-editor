# SmartCut MCP Server — Project Context

## What is this?

MCP server for automated "talking head" video editing. Works with Claude Desktop to:
- Remove long pauses (3+ sec)
- Detect duplicate takes (keeps the last one)
- Add subtitles with dynamic styling
- Export to CapCut project or video file
- Work with existing CapCut projects (list, open, modify with automatic backup)

## Project Structure

```
src/smartcut/
├── __init__.py              # Version
├── config.py                # Settings, env vars, constants
├── server.py                # MCP server entry point, tool registration
├── core/
│   ├── models.py            # Pydantic models for all data structures
│   ├── whisper_client.py    # OpenAI Whisper API wrapper
│   ├── llm_client.py        # GPT for duplicate detection
│   ├── ffmpeg_utils.py      # FFmpeg helpers
│   ├── auphonic_client.py   # Auphonic API for audio enhancement
│   ├── capcut_draft.py      # CapCut project generator (new projects)
│   ├── capcut_reader.py     # CapCut project reader/modifier (existing projects)
│   └── capcut_finder.py     # CapCut project discovery
└── tools/
    ├── transcribe.py        # Whisper transcription
    ├── analyze.py           # Content analysis (pauses, duplicates)
    ├── smart_cut.py         # Main orchestrator tool
    ├── capcut_export.py     # Generate new CapCut project
    ├── capcut_projects.py   # Work with existing CapCut projects
    ├── video_export.py      # FFmpeg video export
    ├── subtitles.py         # SRT generation
    ├── audio_enhance.py     # Auphonic integration
    └── audio_normalize.py   # FFmpeg loudness normalization
```

## Key Files

### config.py
- `Settings` class with env vars: `OPENAI_API_KEY`, `AUPHONIC_API_KEY`, `CAPCUT_DRAFTS_DIR`, `SMARTCUT_ALLOWED_TARGETS`
- Constants: `MICROSECONDS_PER_SECOND = 1_000_000`, `SILENCE_THRESHOLD_SEC = 3.0`
- Helper functions: `can_modify_capcut()`, `can_modify_source()`

### server.py
- 12 MCP tools registered
- Tools filtered based on `SMARTCUT_ALLOWED_TARGETS` env var
- Categories: readonly (transcribe, analyze, subtitles), capcut (5 tools), source (3 tools)

### capcut_reader.py
- `CapCutProject` class for loading/modifying existing CapCut projects
- Key methods: `load()`, `save()`, `create_copy()`, `add_text_track()`, `apply_cut_plan()`
- Reads `draft_info.json` (content) and `draft_meta_info.json` (metadata)

### capcut_finder.py
- `get_capcut_drafts_dir()` - auto-detects CapCut drafts location
- macOS: `~/Movies/CapCut/User Data/Projects/com.lveditor.draft/`
- Windows: `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\`

## CapCut Format Notes

- Times are in **microseconds** (1 sec = 1,000,000 μs)
- Video segments have `source_timerange` (where in source) and `target_timerange` (where on timeline)
- Project name is in `draft_meta_info.json` as `draft_name`
- CapCut monitors drafts folder via FSEvents and may rename/move folders

## Recent Fixes (Feb 2026)

### 1. create_copy() race condition
**Problem**: CapCut renamed UUID folders before we could access them
**Fix**: Use readable name directly (`"Project — SmartCut"`) instead of UUID for folder name

### 2. smart_cut_project not applying cuts
**Problem**: Function analyzed video but never modified CapCut segments
**Fix**: Added `apply_cut_plan()` method and call it after analysis

### 3. Safety env variable
**Added**: `SMARTCUT_ALLOWED_TARGETS` (capcut/source/all) to control what can be modified
- Tools are filtered on startup based on this setting
- Each modifying tool also checks permission before executing

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| OPENAI_API_KEY | Yes | - | OpenAI API key for Whisper + GPT |
| AUPHONIC_API_KEY | No | - | Auphonic API for audio enhancement |
| AUPHONIC_PRESET_UUID | No | - | Auphonic preset UUID |
| CAPCUT_DRAFTS_DIR | No | auto | Path to CapCut drafts folder |
| SMARTCUT_ALLOWED_TARGETS | No | capcut | What can be modified: capcut/source/all |

## Running

```bash
# Install
cd capcut-ai-editor
python -m venv venv
source venv/bin/activate
pip install -e .

# Run server directly
python -m smartcut.server

# Or via Claude Desktop config
```

## Testing with Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "smartcut": {
      "command": "/path/to/capcut-ai-editor/venv/bin/python",
      "args": ["-m", "smartcut.server"],
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "SMARTCUT_ALLOWED_TARGETS": "capcut"
      }
    }
  }
}
```

## Common Tasks

### Add new tool
1. Create function in `tools/`
2. Add Tool schema in `server.py` (in appropriate `_get_*_tools()` function)
3. Add handler in `call_tool()`

### Modify CapCut project format handling
- Edit `capcut_reader.py` for existing projects
- Edit `capcut_draft.py` for new projects
- Check `models.py` for data structures

### Debug CapCut issues
- Check `.recycle_bin/` folder in drafts dir - CapCut may move "invalid" projects there
- Verify `draft_info.json` exists (not just `draft_meta_info.json`)
- CapCut may need restart to see new projects
