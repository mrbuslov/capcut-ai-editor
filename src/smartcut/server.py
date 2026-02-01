"""SmartCut MCP Server - entry point."""

import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from smartcut.config import can_modify_capcut, can_modify_source
from smartcut.core.ffmpeg_utils import check_ffmpeg_installed
from smartcut.tools.analyze import analyze_content
from smartcut.tools.audio_enhance import enhance_audio
from smartcut.tools.audio_normalize import normalize_audio_loudness
from smartcut.tools.capcut_export import generate_capcut_project
from smartcut.tools.capcut_projects import (
    add_subtitles_to_project,
    list_capcut_projects,
    open_capcut_project,
    smart_cut_project,
)
from smartcut.tools.smart_cut import smart_cut
from smartcut.tools.subtitles import generate_subtitles
from smartcut.tools.transcribe import transcribe
from smartcut.tools.video_export import export_video

# Create server instance
server = Server("smartcut")


def _get_readonly_tools() -> list[Tool]:
    """Get read-only tools (always available)."""
    return [
        Tool(
            name="transcribe",
            description=(
                "Transcribe a video or audio file using OpenAI Whisper API. "
                "Returns word-level timestamps for precise editing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the video or audio file",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code (e.g., 'ru', 'en'). Auto-detect if not specified.",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="analyze_content",
            description=(
                "Analyze transcription to identify paragraph boundaries, "
                "long pauses, and duplicate takes. Returns a cut plan."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "transcription_data": {
                        "type": "object",
                        "description": "Transcription data from the transcribe tool",
                    },
                    "silence_threshold_sec": {
                        "type": "number",
                        "description": "Minimum pause to consider as paragraph break (default 3.0)",
                        "default": 3.0,
                    },
                    "duplicate_detection": {
                        "type": "boolean",
                        "description": "Whether to detect duplicate takes using LLM",
                        "default": True,
                    },
                },
                "required": ["transcription_data"],
            },
        ),
        Tool(
            name="generate_subtitles",
            description=(
                "Generate subtitles from transcription as SRT file. "
                "Supports dynamic styling with accent words."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "transcription_data": {
                        "type": "object",
                        "description": "Transcription data from transcribe tool",
                    },
                    "cut_plan_data": {
                        "type": "object",
                        "description": "Cut plan to align subtitles to",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["dynamic", "simple"],
                        "description": "Subtitle style",
                        "default": "dynamic",
                    },
                    "output_srt_path": {
                        "type": "string",
                        "description": "Path for SRT file output",
                    },
                },
                "required": ["transcription_data", "cut_plan_data"],
            },
        ),
    ]


def _get_capcut_tools() -> list[Tool]:
    """Get CapCut modification tools (require SMARTCUT_ALLOWED_TARGETS=capcut or all)."""
    return [
        Tool(
            name="generate_capcut_project",
            description=(
                "Generate a CapCut draft project from a cut plan. "
                "The project will appear in CapCut's drafts list."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the source video file",
                    },
                    "cut_plan_data": {
                        "type": "object",
                        "description": "Cut plan from analyze_content tool",
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Name for the CapCut project",
                    },
                    "add_subtitles": {
                        "type": "boolean",
                        "description": "Whether to add subtitle track",
                        "default": True,
                    },
                    "subtitle_style": {
                        "type": "string",
                        "enum": ["dynamic", "simple"],
                        "description": "Subtitle style",
                        "default": "dynamic",
                    },
                    "transcription_data": {
                        "type": "object",
                        "description": "Transcription data (needed for subtitles)",
                    },
                },
                "required": ["file_path", "cut_plan_data"],
            },
        ),
        Tool(
            name="list_capcut_projects",
            description=(
                "List all existing CapCut projects in the drafts directory. "
                "Auto-detects drafts location on macOS, Windows, and Linux. "
                "Only shows complete projects (with draft_info.json) that can be modified."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "drafts_dir": {
                        "type": "string",
                        "description": "Custom path to CapCut drafts directory (auto-detected if not set)",
                    },
                    "include_incomplete": {
                        "type": "boolean",
                        "description": "Also show incomplete projects that can't be modified",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="open_capcut_project",
            description=(
                "Open an existing CapCut project and return its structure. "
                "Shows video materials, segments, text tracks, and timeline info."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Full path to the project folder",
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Project name to search for (partial match supported)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="add_subtitles_to_project",
            description=(
                "Add subtitles to an existing CapCut project. "
                "Creates a backup copy of the project before modification. "
                "Can transcribe video automatically or use provided transcription/SRT."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Full path to the project folder",
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Project name to search for (partial match)",
                    },
                    "transcription_data": {
                        "type": "object",
                        "description": "Transcription data from transcribe tool (optional)",
                    },
                    "srt_path": {
                        "type": "string",
                        "description": "Path to existing SRT file (optional)",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["dynamic", "simple"],
                        "description": "Subtitle style",
                        "default": "dynamic",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code for transcription (auto-detect if not set)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="smart_cut_project",
            description=(
                "Apply smart_cut to an existing CapCut project. "
                "Creates a backup copy, then removes pauses and duplicates from all video clips. "
                "The last take of duplicates is always kept (assumed to be the best)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Full path to the project folder",
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Project name to search for (partial match)",
                    },
                    "silence_threshold_sec": {
                        "type": "number",
                        "description": "Minimum pause duration to cut (default 3.0 seconds)",
                        "default": 3.0,
                    },
                    "detect_duplicates": {
                        "type": "boolean",
                        "description": "Whether to detect and remove duplicate takes",
                        "default": True,
                    },
                    "add_subtitles": {
                        "type": "boolean",
                        "description": "Whether to add subtitles",
                        "default": True,
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code (auto-detect if not set)",
                    },
                },
                "required": [],
            },
        ),
    ]


def _get_source_tools() -> list[Tool]:
    """Get source file modification tools (require SMARTCUT_ALLOWED_TARGETS=source or all)."""
    return [
        Tool(
            name="export_video",
            description=(
                "Export cut video as a new file using FFmpeg. "
                "Uses stream copy for fast, lossless export."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the source video file",
                    },
                    "cut_plan_data": {
                        "type": "object",
                        "description": "Cut plan from analyze_content tool",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Output file path (auto-generated if not set)",
                    },
                    "preserve_format": {
                        "type": "boolean",
                        "description": "Keep original format (MOV stays MOV)",
                        "default": True,
                    },
                },
                "required": ["file_path", "cut_plan_data"],
            },
        ),
        Tool(
            name="enhance_audio",
            description=(
                "Enhance audio quality using Auphonic API. "
                "Includes loudness normalization, noise reduction, and leveling. "
                "Requires AUPHONIC_API_KEY environment variable."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the video file",
                    },
                    "preset_uuid": {
                        "type": "string",
                        "description": "Auphonic preset UUID (uses AUPHONIC_PRESET_UUID env var if not set)",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Output file path (auto-generated if not set)",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="normalize_audio",
            description=(
                "Normalize audio loudness using FFmpeg. "
                "Free alternative to Auphonic for basic loudness normalization. "
                "Standard target is -16 LUFS for social media."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the video/audio file",
                    },
                    "target_lufs": {
                        "type": "number",
                        "description": "Target loudness in LUFS (default -16)",
                        "default": -16.0,
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Output file path (auto-generated if not set)",
                    },
                },
                "required": ["file_path"],
            },
        ),
    ]


def _get_smart_cut_tool() -> Tool:
    """Get the main smart_cut tool."""
    return Tool(
        name="smart_cut",
        description=(
            "Main tool for processing talking head videos. "
            "Transcribes, removes long pauses, detects duplicate takes, "
            "and exports to CapCut project or video file. "
            "The last take of duplicates is always kept (assumed to be the best)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the video file (MOV, MP4, etc.)",
                },
                "language": {
                    "type": "string",
                    "description": "Language code (e.g., 'ru', 'en'). Auto-detect if not specified.",
                },
                "silence_threshold_sec": {
                    "type": "number",
                    "description": "Minimum pause duration to cut (default 3.0 seconds)",
                    "default": 3.0,
                },
                "detect_duplicates": {
                    "type": "boolean",
                    "description": "Whether to detect and remove duplicate takes",
                    "default": True,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["capcut", "video", "both"],
                    "description": "Output format - 'capcut' (CapCut project), 'video' (MP4/MOV file), or 'both'",
                    "default": "capcut",
                },
                "project_name": {
                    "type": "string",
                    "description": "Name for the CapCut project",
                },
                "add_subtitles": {
                    "type": "boolean",
                    "description": "Whether to add subtitles",
                    "default": True,
                },
                "subtitle_style": {
                    "type": "string",
                    "enum": ["dynamic", "simple"],
                    "description": "Subtitle style - 'dynamic' (with accents) or 'simple'",
                    "default": "dynamic",
                },
            },
            "required": ["file_path"],
        },
    )


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools based on SMARTCUT_ALLOWED_TARGETS setting."""
    tools = []

    # smart_cut is special - it can output to either, so include if any is allowed
    if can_modify_capcut() or can_modify_source():
        tools.append(_get_smart_cut_tool())

    # Always include read-only tools
    tools.extend(_get_readonly_tools())

    # Add CapCut tools if allowed
    if can_modify_capcut():
        tools.extend(_get_capcut_tools())

    # Add source file tools if allowed
    if can_modify_source():
        tools.extend(_get_source_tools())

    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "smart_cut":
            result = await smart_cut(**arguments)
        elif name == "transcribe":
            result = await transcribe(**arguments)
        elif name == "analyze_content":
            result = await analyze_content(**arguments)
        elif name == "generate_capcut_project":
            result = await generate_capcut_project(**arguments)
        elif name == "export_video":
            result = await export_video(**arguments)
        elif name == "generate_subtitles":
            result = await generate_subtitles(**arguments)
        elif name == "enhance_audio":
            result = await enhance_audio(**arguments)
        elif name == "normalize_audio":
            result = await normalize_audio_loudness(**arguments)
        elif name == "list_capcut_projects":
            result = await list_capcut_projects(**arguments)
        elif name == "open_capcut_project":
            result = await open_capcut_project(**arguments)
        elif name == "add_subtitles_to_project":
            result = await add_subtitles_to_project(**arguments)
        elif name == "smart_cut_project":
            result = await smart_cut_project(**arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except RuntimeError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Unexpected error: {type(e).__name__}: {e}")]


async def main():
    """Run the MCP server."""
    # Check FFmpeg on startup
    if not check_ffmpeg_installed():
        import sys
        print(
            "Warning: FFmpeg is not installed or not in PATH. "
            "Some features will not work. "
            "Install it with: brew install ffmpeg (Mac) or winget install ffmpeg (Windows)",
            file=sys.stderr,
        )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
