"""
Gemini Audio Transcription Service
Uses Gemini 2.5 Flash Lite for audio-to-text transcription with retry mechanism.
"""

import os
import asyncio
import logging
from typing import Optional
from dataclasses import dataclass
import google.generativeai as genai
from prompts import GEMINI_TRANSCRIPTION_PROMPT

logger = logging.getLogger(__name__)

@dataclass
class TranscriptionResult:
    """Result of audio transcription"""
    success: bool
    text: str = ""
    error: str = ""


class GeminiTranscriber:
    """Audio transcription service using Gemini 2.5 Flash Lite"""
    
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds
    DEFAULT_MODEL = "gemini-2.5-flash"
    
    def __init__(self, model: Optional[str] = None):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError("GOOGLE_API_KEY is not set")
        genai.configure(api_key=api_key)
        self.model_name = model or self.DEFAULT_MODEL
        self.enabled = True
        logger.info(f"GeminiTranscriber initialized with model: {self.model_name}")
    
    async def transcribe(self, audio_path: str) -> TranscriptionResult:
        """
        Transcribe audio file using Gemini.
        
        Args:
            audio_path: Path to the audio file (WAV format)
            
        Returns:
            TranscriptionResult with success status and transcribed text or error
        """
        if not os.path.exists(audio_path):
            return TranscriptionResult(
                success=False,
                error=f"Audio file not found: {audio_path}"
            )
        
        for attempt in range(self.MAX_RETRIES):
            try:
                result = await self._do_transcribe(audio_path)
                return TranscriptionResult(success=True, text=result)
            except Exception as e:
                logger.warning(f"Transcription attempt {attempt + 1} failed: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"All transcription attempts failed for {audio_path}")
                    return TranscriptionResult(
                        success=False,
                        error=f"Transcription failed: {str(e)}"
                    )
        
        return TranscriptionResult(success=False, error="Unknown error")
    
    async def _do_transcribe(self, audio_path: str) -> str:
        """
        Perform the actual transcription using Gemini.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            Transcribed text
        """
        logger.info(f"Transcribing audio file: {audio_path}")
        
        audio_file = genai.upload_file(audio_path)
        logger.info(f"Uploaded audio file: {audio_file.name}")
        
        while audio_file.state.name == "PROCESSING":
            await asyncio.sleep(0.5)
            audio_file = genai.get_file(audio_file.name)
        
        if audio_file.state.name == "FAILED":
            raise Exception(f"Audio file processing failed: {audio_file.state.name}")
        
        model = genai.GenerativeModel(self.model_name)
        
        response = await model.generate_content_async(
            [GEMINI_TRANSCRIPTION_PROMPT, audio_file],
            generation_config=genai.GenerationConfig(
                temperature=0.0,
            )
        )
        
        try:
            genai.delete_file(audio_file.name)
            logger.info(f"Deleted uploaded audio file: {audio_file.name}")
        except Exception as e:
            logger.warning(f"Failed to delete uploaded file: {e}")
        
        transcribed_text = response.text.strip()
        logger.info(f"Transcription completed: {transcribed_text[:100]}...")
        
        return transcribed_text
    
    def transcribe_sync(self, audio_path: str) -> TranscriptionResult:
        """
        Synchronous version of transcribe for non-async contexts.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            TranscriptionResult with success status and transcribed text or error
        """
        return asyncio.run(self.transcribe(audio_path))

_transcriber: Optional[GeminiTranscriber] = None

def get_gemini_transcriber() -> GeminiTranscriber:
    """Get or create the global GeminiTranscriber instance"""
    global _transcriber
    if _transcriber is None:
        try:
            _transcriber = GeminiTranscriber()
        except EnvironmentError as e:
            logger.error(f"Failed to initialize GeminiTranscriber: {e}")
            raise
    return _transcriber
