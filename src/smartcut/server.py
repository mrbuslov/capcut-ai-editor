"""SmartCut MCP Server — simplified entry point."""

import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from smartcut.tools.capcut_projects import (
    batch_edit_subtitles,
    edit_subtitle,
    fix_word_timing,
    list_capcut_projects,
    merge_subtitles,
    open_capcut_project,
    smart_cut_project,
    split_subtitle,
)

server = Server("smartcut")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="list_capcut_projects",
            description="List all CapCut projects in the drafts directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "drafts_dir": {
                        "type": "string",
                        "description": "Custom path to CapCut drafts directory (auto-detected if not set)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="open_capcut_project",
            description=(
                "Open an existing CapCut project and return its structure. "
                "Shows video segments, text tracks, and auto-generated subtitles."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Full path to project folder"},
                    "project_name": {"type": "string", "description": "Project name (partial match)"},
                },
                "required": [],
            },
        ),
        Tool(
            name="smart_cut_project",
            description=(
                "Smart cut a CapCut project: remove silences and duplicate takes. "
                "Reads CapCut's auto-generated subtitles to find gaps and duplicates. "
                "User must generate subtitles in CapCut first (Text → Auto Captions). "
                "Modifies the project IN PLACE (no backup). "
                "By default uses heuristic analysis (free, no API keys). "
                "Set use_openai=true for GPT-enhanced duplicate detection."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Full path to project folder"},
                    "project_name": {"type": "string", "description": "Project name (partial match)"},
                    "silence_threshold_sec": {
                        "type": "number",
                        "description": "Minimum gap between subtitles to cut (default 1.0 sec)",
                        "default": 1.0,
                    },
                    "similarity_threshold": {
                        "type": "number",
                        "description": "Text similarity threshold for duplicate detection (0.0-1.0, default 0.6)",
                        "default": 0.6,
                    },
                    "use_openai": {
                        "type": "boolean",
                        "description": "Use OpenAI GPT for enhanced duplicate detection (requires OPENAI_API_KEY)",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="edit_subtitle",
            description=(
                "Edit subtitle text and/or timing in a CapCut project. "
                "Changing text clears word-level timing (words array). "
                "Use fix_word_timing afterwards if needed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Full path to project folder"},
                    "project_name": {"type": "string", "description": "Project name (partial match)"},
                    "segment_id": {"type": "string", "description": "ID of the text segment to edit"},
                    "new_text": {"type": "string", "description": "New display text"},
                    "new_start_sec": {"type": "number", "description": "New start time in seconds"},
                    "new_duration_sec": {"type": "number", "description": "New duration in seconds"},
                },
                "required": ["segment_id"],
            },
        ),
        Tool(
            name="split_subtitle",
            description="Split a subtitle into two at a given time point on the timeline.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Full path to project folder"},
                    "project_name": {"type": "string", "description": "Project name (partial match)"},
                    "segment_id": {"type": "string", "description": "ID of the text segment to split"},
                    "split_time_sec": {"type": "number", "description": "Timeline time in seconds where to split"},
                },
                "required": ["segment_id", "split_time_sec"],
            },
        ),
        Tool(
            name="merge_subtitles",
            description="Merge two subtitles into one. Segment A absorbs segment B's text and timing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Full path to project folder"},
                    "project_name": {"type": "string", "description": "Project name (partial match)"},
                    "segment_id_a": {"type": "string", "description": "ID of first segment (will be kept)"},
                    "segment_id_b": {"type": "string", "description": "ID of second segment (will be removed)"},
                },
                "required": ["segment_id_a", "segment_id_b"],
            },
        ),
        Tool(
            name="fix_word_timing",
            description="Fix word-level timing on a subtitle. All three arrays must be the same length.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Full path to project folder"},
                    "project_name": {"type": "string", "description": "Project name (partial match)"},
                    "segment_id": {"type": "string", "description": "ID of the text segment"},
                    "words_text": {"type": "array", "items": {"type": "string"}, "description": "Word strings"},
                    "words_start_ms": {"type": "array", "items": {"type": "integer"}, "description": "Start times in ms (relative to segment start)"},
                    "words_end_ms": {"type": "array", "items": {"type": "integer"}, "description": "End times in ms (relative to segment start)"},
                },
                "required": ["segment_id", "words_text", "words_start_ms", "words_end_ms"],
            },
        ),
        Tool(
            name="batch_edit_subtitles",
            description=(
                "Apply multiple subtitle edits in one pass. Each edit can change text and/or timing. "
                "Each item needs segment_id, and optionally new_text, new_start_sec, new_duration_sec."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Full path to project folder"},
                    "project_name": {"type": "string", "description": "Project name (partial match)"},
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "segment_id": {"type": "string"},
                                "new_text": {"type": "string"},
                                "new_start_sec": {"type": "number"},
                                "new_duration_sec": {"type": "number"},
                            },
                            "required": ["segment_id"],
                        },
                        "description": "List of edits to apply",
                    },
                },
                "required": ["edits"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "list_capcut_projects":
            result = await list_capcut_projects(**arguments)
        elif name == "open_capcut_project":
            result = await open_capcut_project(**arguments)
        elif name == "smart_cut_project":
            result = await smart_cut_project(**arguments)
        elif name == "edit_subtitle":
            result = await edit_subtitle(**arguments)
        elif name == "split_subtitle":
            result = await split_subtitle(**arguments)
        elif name == "merge_subtitles":
            result = await merge_subtitles(**arguments)
        elif name == "fix_word_timing":
            result = await fix_word_timing(**arguments)
        elif name == "batch_edit_subtitles":
            result = await batch_edit_subtitles(**arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
