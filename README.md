# SmartCut MCP Server

MCP server for automated "talking head" video processing. Removes pauses, detects duplicate takes, adds subtitles — and exports to CapCut project.

## Features

- **Removes long pauses** (3+ seconds between phrases)
- **Detects duplicate takes** (when you re-record a phrase multiple times — keeps the last, best one)
- **Generates subtitles** with dynamic styling (accent words, position changes)
- **Enhances audio** via Auphonic or FFmpeg normalization
- **Exports to CapCut** — open the project and fine-tune manually
- **Works with existing CapCut projects** — list, open, modify, and save projects with automatic backup

## Requirements

- Python 3.10+
- FFmpeg (must be in PATH)
- OpenAI API key (for Whisper + GPT)
- CapCut (for final editing)

### Installing FFmpeg

**Mac:**
```bash
brew install ffmpeg
```

**Windows:**
```bash
winget install ffmpeg
```

## Installation

```bash
cd capcut-ai-editor
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

## Claude Desktop Setup

Open Claude Desktop config:
- **Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add:

```json
{
  "mcpServers": {
    "smartcut": {
      "command": "/path/to/capcut-ai-editor/venv/bin/python",
      "args": ["-m", "smartcut.server"],
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

Replace `/path/to/capcut-ai-editor` with the actual path to the project.

**Optional** (for audio enhancement via Auphonic):
```json
"env": {
  "OPENAI_API_KEY": "sk-...",
  "AUPHONIC_API_KEY": "...",
  "AUPHONIC_PRESET_UUID": "..."
}
```

Restart Claude Desktop.

## Usage

In chat with Claude, just describe what you need:

**Basic processing:**
```
Process video /Users/me/Desktop/video.mov — remove pauses and duplicates
```

**With subtitles:**
```
Process video.mov, add subtitles with accent words
```

**With audio enhancement:**
```
Process video.mov, enhance audio via Auphonic
```

**Export to video file (without CapCut):**
```
Cut pauses from video.mov and save as video_cut.mov
```

**Transcription only:**
```
Transcribe video.mov
```

## Working with Existing CapCut Projects

SmartCut can work with projects you've already created in CapCut.

**List all CapCut projects:**
```
Show me my CapCut projects
```

**Open a specific project:**
```
Open CapCut project "My Vlog"
```

**Add subtitles to existing project:**
```
Add subtitles to my "Interview" CapCut project
```

**Apply smart_cut to existing project:**
```
Remove pauses and duplicates from my "Podcast Episode 5" project
```

All modifications create a backup copy of the project (original stays untouched).

## After Processing

1. Open CapCut
2. Find the project in drafts (may need to restart CapCut)
3. Review and fine-tune the edit manually
4. Export the final video

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| OPENAI_API_KEY | Yes | OpenAI API key |
| AUPHONIC_API_KEY | No | Auphonic API key (for audio enhancement) |
| AUPHONIC_PRESET_UUID | No | Auphonic preset UUID |
| CAPCUT_DRAFTS_DIR | No | Path to CapCut drafts folder (auto-detected) |
| SMARTCUT_ALLOWED_TARGETS | No | What can be modified: `capcut` (default), `source`, or `all` |

## Troubleshooting

**"FFmpeg not found"**
Install FFmpeg and make sure it's in PATH: `ffmpeg -version`

**CapCut doesn't see the project**
Restart CapCut. Check that the video path is correct (video must exist).

**Whisper API error**
Check OPENAI_API_KEY. Make sure the account has credits.
