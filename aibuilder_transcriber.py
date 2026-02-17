"""
AI Builder Space Audio Transcription Service
Supports both short and long audio transcription endpoints.
"""

import os
import asyncio
import logging
from typing import Optional
from gemini_transcriber import TranscriptionResult
import httpx

logger = logging.getLogger(__name__)


class AIBuilderTranscriber:
    """Audio transcription service using AI Builder Space"""

    MAX_RETRIES = 3
    TIMEOUT = 300  # seconds

    def __init__(self):
        self.api_token = os.getenv("AIBUILDER_API_TOKEN")
        self.base_url = os.getenv("AIBUILDER_BASE_URL") or "https://space.ai-builders.com/backend"
        if not self.api_token:
            raise EnvironmentError("AIBUILDER_API_TOKEN is not set")
        self.enabled = True
        logger.info(f"AIBuilderTranscriber initialized, base_url: {self.base_url}")

    async def transcribe(self, audio_path: str, language: str = "zh-TW") -> TranscriptionResult:
        """POST /v1/audio/transcriptions (short audio)"""
        if not os.path.exists(audio_path):
            return TranscriptionResult(success=False, error=f"Audio file not found: {audio_path}")

        for attempt in range(self.MAX_RETRIES):
            try:
                text = await self._do_transcribe(audio_path, language)
                return TranscriptionResult(success=True, text=text)
            except Exception as e:
                logger.warning(f"Builder transcription attempt {attempt + 1} failed: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    return TranscriptionResult(success=False, error=f"Transcription failed: {str(e)}")

        return TranscriptionResult(success=False, error="Unknown error")

    async def transcribe_long(self, audio_path: str, language: str = "zh-TW",
                               speaker_labels: bool = False,
                               disfluencies: bool = False) -> TranscriptionResult:
        """POST /v1/audio/transcriptions_long (long audio, sentence-level timestamps)"""
        if not os.path.exists(audio_path):
            return TranscriptionResult(success=False, error=f"Audio file not found: {audio_path}")

        for attempt in range(self.MAX_RETRIES):
            try:
                text = await self._do_transcribe_long(audio_path, language, speaker_labels, disfluencies)
                return TranscriptionResult(success=True, text=text)
            except Exception as e:
                logger.warning(f"Builder long transcription attempt {attempt + 1} failed: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    return TranscriptionResult(success=False, error=f"Long transcription failed: {str(e)}")

        return TranscriptionResult(success=False, error="Unknown error")

    async def _do_transcribe(self, audio_path: str, language: str) -> str:
        url = f"{self.base_url}/v1/audio/transcriptions"
        logger.info(f"Builder transcribe: {audio_path}")

        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            with open(audio_path, "rb") as f:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_token}"},
                    files={"audio_file": (os.path.basename(audio_path), f, "audio/wav")},
                    data={"language": language},
                )
            response.raise_for_status()
            result = response.json()
            text = result.get("text", "")
            logger.info(f"Builder transcription completed: {text[:100]}...")
            return text

    async def _do_transcribe_long(self, audio_path: str, language: str,
                                   speaker_labels: bool, disfluencies: bool) -> str:
        url = f"{self.base_url}/v1/audio/transcriptions_long"
        logger.info(f"Builder long transcribe: {audio_path}")

        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            with open(audio_path, "rb") as f:
                data = {"language": language}
                if speaker_labels:
                    data["speaker_labels"] = "true"
                if disfluencies:
                    data["disfluencies"] = "true"

                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_token}"},
                    files={"audio_file": (os.path.basename(audio_path), f, "audio/wav")},
                    data=data,
                )
            response.raise_for_status()
            result = response.json()
            text = result.get("text", "")
            logger.info(f"Builder long transcription completed: {text[:100]}...")
            return text


_transcriber: Optional[AIBuilderTranscriber] = None


def get_aibuilder_transcriber() -> AIBuilderTranscriber:
    """Get or create the global AIBuilderTranscriber instance"""
    global _transcriber
    if _transcriber is None:
        try:
            _transcriber = AIBuilderTranscriber()
        except EnvironmentError as e:
            logger.error(f"Failed to initialize AIBuilderTranscriber: {e}")
            raise
    return _transcriber
