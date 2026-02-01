"""Audio Normalize tool - normalizes audio loudness using FFmpeg."""

from pathlib import Path
from typing import Optional

from smartcut.config import TARGET_LUFS
from smartcut.core.ffmpeg_utils import check_ffmpeg_installed, normalize_audio


async def normalize_audio_loudness(
    file_path: str,
    target_lufs: float = TARGET_LUFS,
    output_path: Optional[str] = None,
) -> dict:
    """
    Normalize audio loudness using FFmpeg's loudnorm filter.

    This is a free alternative to Auphonic for basic loudness normalization.
    Uses two-pass loudnorm filter for accurate normalization.

    Standard targets:
    - -16 LUFS: Social media (YouTube, Instagram, TikTok)
    - -14 LUFS: Spotify, Apple Music
    - -23 LUFS: Broadcast (EBU R128)

    Args:
        file_path: Path to the video/audio file.
        target_lufs: Target loudness in LUFS (default -16).
        output_path: Output file path. Auto-generated if not set.

    Returns:
        Normalized file path and loudness information.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not check_ffmpeg_installed():
        raise RuntimeError(
            "FFmpeg is not installed or not in PATH. "
            "Install it with: brew install ffmpeg (Mac) or winget install ffmpeg (Windows)"
        )

    # Determine output path
    if output_path:
        out_path = Path(output_path)
    else:
        out_path = path.with_stem(f"{path.stem}_normalized")

    # Normalize audio
    _, loudness_info = normalize_audio(path, out_path, target_lufs)

    return {
        "output_path": str(out_path.absolute()),
        "original_lufs": round(loudness_info.input_i, 1),
        "target_lufs": target_lufs,
        "applied": True,
        "message": f"Audio normalized from {loudness_info.input_i:.1f} LUFS to {target_lufs} LUFS",
    }
