"""Auphonic API client for audio enhancement."""

import time
from pathlib import Path
from typing import Optional

import httpx

AUPHONIC_API_BASE = "https://auphonic.com/api"
POLL_INTERVAL_SEC = 5
MAX_POLL_ATTEMPTS = 120  # 10 minutes max


class ProductionStatus:
    """Auphonic production status."""

    INCOMPLETE = 0
    QUEUED = 1
    IN_PROGRESS = 2
    DONE = 3
    ERROR = 4

    STATUS_NAMES = {
        0: "incomplete",
        1: "queued",
        2: "in_progress",
        3: "done",
        4: "error",
    }

    def __init__(self, status_code: int, status_string: str = "", error_message: str = ""):
        self.code = status_code
        self.status_string = status_string or self.STATUS_NAMES.get(status_code, "unknown")
        self.error_message = error_message

    @property
    def is_done(self) -> bool:
        return self.code == self.DONE

    @property
    def is_error(self) -> bool:
        return self.code == self.ERROR

    @property
    def is_pending(self) -> bool:
        return self.code in (self.INCOMPLETE, self.QUEUED, self.IN_PROGRESS)


class AuphonicClient:
    """Client for Auphonic audio enhancement API."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Auphonic API key is required")
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def create_production(
        self,
        audio_path: Path,
        preset_uuid: Optional[str] = None,
        title: str = "SmartCut Enhancement",
    ) -> str:
        """
        Create and start an Auphonic production.

        Args:
            audio_path: Path to audio file.
            preset_uuid: Auphonic preset UUID (optional).
            title: Production title.

        Returns:
            Production UUID.
        """
        with httpx.Client(timeout=300) as client:
            # Create production with file upload
            files = {"input_file": open(audio_path, "rb")}
            data = {
                "title": title,
                "action": "start",
            }
            if preset_uuid:
                data["preset"] = preset_uuid

            response = client.post(
                f"{AUPHONIC_API_BASE}/simple/productions.json",
                headers=self.headers,
                files=files,
                data=data,
            )
            response.raise_for_status()

            result = response.json()
            if result.get("status_code") != 200:
                raise RuntimeError(f"Auphonic API error: {result.get('error_message', 'Unknown error')}")

            return result["data"]["uuid"]

    def get_status(self, production_uuid: str) -> ProductionStatus:
        """
        Get production status.

        Args:
            production_uuid: Production UUID.

        Returns:
            ProductionStatus object.
        """
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{AUPHONIC_API_BASE}/production/{production_uuid}.json",
                headers=self.headers,
            )
            response.raise_for_status()

            result = response.json()
            data = result.get("data", {})

            return ProductionStatus(
                status_code=data.get("status", 0),
                status_string=data.get("status_string", ""),
                error_message=data.get("error_message", ""),
            )

    def poll_until_done(
        self,
        production_uuid: str,
        poll_interval: int = POLL_INTERVAL_SEC,
        max_attempts: int = MAX_POLL_ATTEMPTS,
    ) -> ProductionStatus:
        """
        Poll production status until completion.

        Args:
            production_uuid: Production UUID.
            poll_interval: Seconds between polls.
            max_attempts: Maximum poll attempts.

        Returns:
            Final ProductionStatus.

        Raises:
            TimeoutError: If max attempts exceeded.
            RuntimeError: If production failed.
        """
        for _ in range(max_attempts):
            status = self.get_status(production_uuid)

            if status.is_done:
                return status

            if status.is_error:
                raise RuntimeError(f"Auphonic production failed: {status.error_message}")

            time.sleep(poll_interval)

        raise TimeoutError(f"Auphonic production timed out after {max_attempts * poll_interval} seconds")

    def download_result(
        self,
        production_uuid: str,
        output_path: Path,
    ) -> Path:
        """
        Download enhanced audio file.

        Args:
            production_uuid: Production UUID.
            output_path: Path to save the file.

        Returns:
            Path to downloaded file.
        """
        with httpx.Client(timeout=300) as client:
            # Get production details to find output file URL
            response = client.get(
                f"{AUPHONIC_API_BASE}/production/{production_uuid}.json",
                headers=self.headers,
            )
            response.raise_for_status()

            result = response.json()
            output_files = result.get("data", {}).get("output_files", [])

            if not output_files:
                raise RuntimeError("No output files available")

            # Download the first output file
            download_url = output_files[0].get("download_url")
            if not download_url:
                raise RuntimeError("No download URL available")

            # Download file
            response = client.get(download_url, headers=self.headers)
            response.raise_for_status()

            output_path.write_bytes(response.content)
            return output_path

    def enhance_audio(
        self,
        audio_path: Path,
        output_path: Path,
        preset_uuid: Optional[str] = None,
    ) -> Path:
        """
        Full workflow: create production, wait, download result.

        Args:
            audio_path: Input audio file.
            output_path: Output file path.
            preset_uuid: Auphonic preset UUID.

        Returns:
            Path to enhanced audio file.
        """
        production_uuid = self.create_production(audio_path, preset_uuid)
        self.poll_until_done(production_uuid)
        return self.download_result(production_uuid, output_path)
