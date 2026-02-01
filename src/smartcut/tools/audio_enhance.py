"""Audio Enhance tool - enhances audio using Auphonic API."""

import tempfile
from pathlib import Path
from typing import Optional

from smartcut.config import can_modify_source, get_settings
from smartcut.core.auphonic_client import AuphonicClient
from smartcut.core.ffmpeg_utils import extract_audio, mux_audio_video


async def enhance_audio(
    file_path: str,
    preset_uuid: Optional[str] = None,
    output_path: Optional[str] = None,
) -> dict:
    """
    Enhance audio quality using Auphonic API.

    Auphonic provides professional audio processing including:
    - Loudness normalization
    - Noise reduction
    - Leveling
    - Filtering

    Requires AUPHONIC_API_KEY environment variable.

    Args:
        file_path: Path to the video file.
        preset_uuid: Auphonic preset UUID. Uses AUPHONIC_PRESET_UUID env var if not set.
        output_path: Output file path. Auto-generated if not set.

    Returns:
        Enhanced file path and processing information.
    """
    # Check if source file modification is allowed
    if not can_modify_source():
        return {
            "error": "Source file modification is disabled",
            "suggestion": "Set SMARTCUT_ALLOWED_TARGETS=source or SMARTCUT_ALLOWED_TARGETS=all to enable",
        }

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    settings = get_settings()

    # Check for API key
    if not settings.auphonic_api_key:
        raise RuntimeError(
            "AUPHONIC_API_KEY environment variable is not set. "
            "Get an API key at https://auphonic.com and set AUPHONIC_API_KEY. "
            "Alternatively, use the normalize_audio tool for basic loudness normalization via FFmpeg."
        )

    # Use preset from parameter or environment
    preset = preset_uuid or settings.auphonic_preset_uuid

    # Determine output path
    if output_path:
        out_path = Path(output_path)
    else:
        out_path = path.with_stem(f"{path.stem}_enhanced")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Extract audio
        audio_path = temp_path / "audio.wav"
        extract_audio(path, audio_path, sample_rate=44100)

        # Process with Auphonic
        client = AuphonicClient(settings.auphonic_api_key)
        enhanced_audio_path = temp_path / "enhanced.wav"

        try:
            production_uuid = client.create_production(
                audio_path=audio_path,
                preset_uuid=preset,
                title=f"SmartCut: {path.name}",
            )

            client.poll_until_done(production_uuid)
            client.download_result(production_uuid, enhanced_audio_path)

        except Exception as e:
            raise RuntimeError(f"Auphonic processing failed: {e}")

        # Mux enhanced audio back into video
        mux_audio_video(path, enhanced_audio_path, out_path)

    return {
        "enhanced_file_path": str(out_path.absolute()),
        "auphonic_production_uuid": production_uuid,
        "status": "done",
        "message": f"Audio enhanced and saved to {out_path.name}",
    }
