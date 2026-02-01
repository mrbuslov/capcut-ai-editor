"""FFmpeg utility functions for video/audio processing."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from smartcut.config import TARGET_LUFS
from smartcut.core.models import LoudnessInfo, MediaInfo


class FFmpegError(Exception):
    """FFmpeg operation error."""

    pass


def check_ffmpeg_installed() -> bool:
    """Check if FFmpeg is installed and available in PATH."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def get_media_info(file_path: Path) -> MediaInfo:
    """
    Get media file information using ffprobe.

    Args:
        file_path: Path to media file.

    Returns:
        MediaInfo object with duration, resolution, etc.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"ffprobe failed: {e.stderr}")
    except json.JSONDecodeError as e:
        raise FFmpegError(f"Failed to parse ffprobe output: {e}")

    # Extract format info
    format_info = data.get("format", {})
    duration = float(format_info.get("duration", 0))
    file_format = format_info.get("format_name", "").split(",")[0]

    # Extract video stream info
    width, height, fps = 1920, 1080, 30.0
    audio_sample_rate = 44100

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width", width)
            height = stream.get("height", height)
            # Parse fps from r_frame_rate (e.g., "30/1")
            fps_str = stream.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) != 0 else 30.0
        elif stream.get("codec_type") == "audio":
            audio_sample_rate = int(stream.get("sample_rate", audio_sample_rate))

    return MediaInfo(
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        audio_sample_rate=audio_sample_rate,
        format=file_format,
    )


def extract_audio(
    video_path: Path,
    output_path: Path,
    sample_rate: int = 16000,
) -> Path:
    """
    Extract audio from video file.

    Args:
        video_path: Path to video file.
        output_path: Path for output audio file (WAV).
        sample_rate: Audio sample rate (default 16kHz for Whisper).

    Returns:
        Path to extracted audio file.
    """
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # PCM 16-bit
        "-ar", str(sample_rate),  # Sample rate
        "-ac", "1",  # Mono
        "-y",  # Overwrite
        str(output_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"Audio extraction failed: {e.stderr.decode()}")

    return output_path


def cut_segment(
    input_path: Path,
    output_path: Path,
    start: float,
    end: float,
    stream_copy: bool = True,
) -> Path:
    """
    Cut a segment from video/audio file.

    Args:
        input_path: Input file path.
        output_path: Output file path.
        start: Start time in seconds.
        end: End time in seconds.
        stream_copy: Use stream copy (fast, no re-encode) if True.

    Returns:
        Path to output file.
    """
    duration = end - start

    cmd = [
        "ffmpeg",
        "-ss", str(start),  # Seek before input (faster)
        "-i", str(input_path),
        "-t", str(duration),
    ]

    if stream_copy:
        cmd.extend(["-c", "copy"])

    cmd.extend(["-y", str(output_path)])

    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"Segment cutting failed: {e.stderr.decode()}")

    return output_path


def concat_segments(
    segment_paths: list[Path],
    output_path: Path,
    use_concat_filter: bool = False,
) -> Path:
    """
    Concatenate multiple video/audio segments.

    Args:
        segment_paths: List of segment file paths.
        output_path: Output file path.
        use_concat_filter: Use concat filter (re-encodes) vs concat demuxer (stream copy).

    Returns:
        Path to concatenated file.
    """
    if not segment_paths:
        raise FFmpegError("No segments to concatenate")

    if len(segment_paths) == 1:
        # Just copy the single file
        shutil.copy(segment_paths[0], output_path)
        return output_path

    # Create concat list file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for path in segment_paths:
            # Escape single quotes in paths
            escaped_path = str(path).replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
        concat_list_path = f.name

    try:
        if use_concat_filter:
            # Use concat filter (re-encodes, handles different formats)
            inputs = []
            for path in segment_paths:
                inputs.extend(["-i", str(path)])

            filter_parts = [f"[{i}:v][{i}:a]" for i in range(len(segment_paths))]
            filter_complex = "".join(filter_parts) + f"concat=n={len(segment_paths)}:v=1:a=1[outv][outa]"

            cmd = ["ffmpeg"] + inputs + [
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-y", str(output_path),
            ]
        else:
            # Use concat demuxer (stream copy, fast)
            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_path,
                "-c", "copy",
                "-y", str(output_path),
            ]

        subprocess.run(cmd, capture_output=True, check=True)

    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"Concatenation failed: {e.stderr.decode()}")
    finally:
        Path(concat_list_path).unlink(missing_ok=True)

    return output_path


def measure_loudness(file_path: Path) -> LoudnessInfo:
    """
    Measure audio loudness using FFmpeg loudnorm filter.

    Args:
        file_path: Path to audio/video file.

    Returns:
        LoudnessInfo with measured values.
    """
    cmd = [
        "ffmpeg",
        "-i", str(file_path),
        "-af", "loudnorm=print_format=json",
        "-f", "null",
        "-",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        # loudnorm output is in stderr
        output = result.stderr

        # Find JSON in output
        json_start = output.rfind("{")
        json_end = output.rfind("}") + 1
        if json_start == -1 or json_end == 0:
            raise FFmpegError("Could not find loudness data in FFmpeg output")

        loudness_data = json.loads(output[json_start:json_end])

        return LoudnessInfo(
            input_i=float(loudness_data.get("input_i", -24)),
            input_tp=float(loudness_data.get("input_tp", 0)),
            input_lra=float(loudness_data.get("input_lra", 0)),
            input_thresh=float(loudness_data.get("input_thresh", -34)),
            target_offset=float(loudness_data.get("target_offset", 0)),
        )

    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"Loudness measurement failed: {e.stderr}")
    except (json.JSONDecodeError, KeyError) as e:
        raise FFmpegError(f"Failed to parse loudness data: {e}")


def normalize_audio(
    input_path: Path,
    output_path: Path,
    target_lufs: float = TARGET_LUFS,
) -> tuple[Path, LoudnessInfo]:
    """
    Normalize audio loudness using two-pass loudnorm filter.

    Args:
        input_path: Input file path.
        output_path: Output file path.
        target_lufs: Target loudness in LUFS (default -16).

    Returns:
        Tuple of (output path, loudness info).
    """
    # First pass: measure loudness
    loudness = measure_loudness(input_path)

    # Second pass: apply normalization
    loudnorm_filter = (
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:"
        f"measured_I={loudness.input_i}:"
        f"measured_TP={loudness.input_tp}:"
        f"measured_LRA={loudness.input_lra}:"
        f"measured_thresh={loudness.input_thresh}:"
        f"offset={loudness.target_offset}:"
        f"linear=true"
    )

    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-af", loudnorm_filter,
        "-c:v", "copy",  # Copy video stream
        "-y", str(output_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"Audio normalization failed: {e.stderr.decode()}")

    return output_path, loudness


def mux_audio_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
) -> Path:
    """
    Mux audio into video file (replace audio track).

    Args:
        video_path: Video file path.
        audio_path: Audio file path.
        output_path: Output file path.

    Returns:
        Path to output file.
    """
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-y", str(output_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"Audio/video muxing failed: {e.stderr.decode()}")

    return output_path


def get_file_format(file_path: Path) -> str:
    """Get file format extension, normalized."""
    suffix = file_path.suffix.lower().lstrip(".")
    # Normalize common formats
    format_map = {
        "mov": "mov",
        "mp4": "mp4",
        "m4v": "mp4",
        "mkv": "mkv",
        "avi": "avi",
        "webm": "webm",
    }
    return format_map.get(suffix, suffix)
