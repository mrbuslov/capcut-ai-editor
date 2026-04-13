# SmartCut MCP Server

MCP server for automated "talking head" video editing. Reads CapCut's auto-generated subtitles to find and remove silences and duplicate takes — directly in the CapCut project.

## How it works

1. Record your video, import into CapCut
2. Generate subtitles in CapCut (Text → Auto Captions)
3. Close CapCut
4. Ask Claude: "Smart cut my 'Podcast Episode 5' project"
5. Reopen in CapCut, review the cuts

SmartCut reads CapCut's subtitles to understand where speech is. Gaps between subtitles > 1 second are cut. If the speaker repeats a phrase (duplicate take), earlier attempts are removed and the last version is kept.

**No API keys required** — heuristic analysis works locally. Optionally set `OPENAI_API_KEY` for GPT-enhanced duplicate detection.

## Requirements

- Python 3.10+
- CapCut (for editing and subtitle generation)

## Installation

```bash
cd capcut-ai-editor
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

For optional OpenAI-enhanced duplicate detection:
```bash
pip install -e ".[openai]"
```

## Claude Code / Claude Desktop Setup

Add to MCP config:

```json
{
  "mcpServers": {
    "smartcut": {
      "command": "/path/to/capcut-ai-editor/venv/bin/python",
      "args": ["-m", "smartcut.server"]
    }
  }
}
```

Optional env for GPT-enhanced duplicates:
```json
"env": {
  "OPENAI_API_KEY": "sk-..."
}
```

## Usage

**List projects:**
```
Show me my CapCut projects
```

**Inspect a project:**
```
Open CapCut project "My Vlog"
```

**Smart cut (main function):**
```
Smart cut my "Podcast Episode 5" project
```

**With OpenAI enhancement:**
```
Smart cut "My Video" with use_openai=true
```

**Warning:** Smart cut modifies the project in place (no backup). Make a copy in CapCut first if you want to keep the original.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| OPENAI_API_KEY | No | OpenAI API key (for GPT-enhanced duplicate detection) |
| CAPCUT_DRAFTS_DIR | No | Path to CapCut drafts folder (auto-detected) |

## Troubleshooting

**"No auto-generated subtitles found"**
Open the project in CapCut, select the video track, use Text → Auto Captions, save, then try again.

**CapCut doesn't see changes**
Restart CapCut. It monitors the drafts folder but sometimes needs a restart.

## Related Tools

- [capcut-cli](https://github.com/renezander030/capcut-cli) — CLI for editing CapCut draft_content.json: change text, timing, speed, volume. JSON output, batch edits via JSONL.
