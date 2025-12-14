import asyncio
import json
import os
import uuid
import numpy as np
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
import uvicorn
import logging
from prompts import PROMPTS
from openai_realtime_client import OpenAIRealtimeAudioTextClient
from starlette.websockets import WebSocketState
import wave
import datetime
import scipy.signal
from openai import OpenAI, AsyncOpenAI
from pydantic import BaseModel, Field
from typing import Generator, Optional
from llm_processor import get_llm_processor
from datetime import datetime, timedelta
from notion_service import notion_service
from content_analyzer import content_analyzer
from monitor import word_count_monitor
from gemini_transcriber import get_gemini_transcriber
from google_sheet_service import google_sheet_service
from chinese_converter import convert_if_needed

# Audio storage configuration
# Use /tmp for temporary audio storage (works on all systems, survives within container lifecycle)
AUDIO_STORAGE_PATH = os.getenv("AUDIO_STORAGE_PATH", "/tmp/brainwave_audio")

def ensure_audio_storage_exists():
    """Ensure the audio storage directory exists"""
    try:
        if not os.path.exists(AUDIO_STORAGE_PATH):
            os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
            logger.info(f"Created audio storage directory: {AUDIO_STORAGE_PATH}")
    except OSError as e:
        logger.warning(f"Could not create audio storage directory: {e}. Audio storage will be disabled.")

def generate_session_id() -> str:
    """Generate a unique session ID for audio storage"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    return f"{timestamp}_{unique_id}"

def get_audio_file_path(session_id: str) -> str:
    """Get the full path for an audio file given a session ID"""
    return os.path.join(AUDIO_STORAGE_PATH, f"{session_id}.wav")

# Audio cleanup configuration
AUDIO_CLEANUP_INTERVAL = 3600  # 1 hour in seconds
AUDIO_MAX_AGE = 86400  # 24 hours in seconds

async def cleanup_old_audio_files():
    """Background task to clean up old audio files every hour"""
    while True:
        try:
            await asyncio.sleep(AUDIO_CLEANUP_INTERVAL)
            
            if not os.path.exists(AUDIO_STORAGE_PATH):
                continue
                
            now = datetime.now()
            cleaned_count = 0
            
            for filename in os.listdir(AUDIO_STORAGE_PATH):
                filepath = os.path.join(AUDIO_STORAGE_PATH, filename)
                try:
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    file_age = (now - file_mtime).total_seconds()
                    
                    if file_age > AUDIO_MAX_AGE:
                        os.remove(filepath)
                        cleaned_count += 1
                        logger.info(f"Cleaned up old audio file: {filepath}")
                except Exception as e:
                    logger.warning(f"Failed to check/clean file {filepath}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"Audio cleanup completed: removed {cleaned_count} old files")
                
        except Exception as e:
            logger.error(f"Error in audio cleanup task: {e}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Pydantic models for request and response schemas
class ReadabilityRequest(BaseModel):
    text: str = Field(..., description="The text to improve readability for.")

class ReadabilityResponse(BaseModel):
    enhanced_text: str = Field(..., description="The text with improved readability.")

class CorrectnessRequest(BaseModel):
    text: str = Field(..., description="The text to check for factual correctness.")

class CorrectnessResponse(BaseModel):
    analysis: str = Field(..., description="The factual correctness analysis.")

class AskAIRequest(BaseModel):
    text: str = Field(..., description="The question to ask AI.")

class AskAIResponse(BaseModel):
    answer: str = Field(..., description="AI's answer to the question.")

# Word count monitoring models
class WordCountStatusResponse(BaseModel):
    status: str = Field(..., description="Current status of the word count monitor")
    running: bool = Field(..., description="Whether the monitor is running")
    stats: dict = Field(..., description="Monitor statistics")

class ManualUpdateRequest(BaseModel):
    page_id: Optional[str] = Field(None, description="Specific page ID to update (optional)")

class ManualUpdateResponse(BaseModel):
    success: bool = Field(..., description="Whether the update was successful")
    message: str = Field(..., description="Status message")
    details: Optional[dict] = Field(None, description="Additional details")

# Re-transcription models
class RetranscribeRequest(BaseModel):
    session_id: str = Field(..., description="The session ID of the recording to re-transcribe")

class RetranscribeResponse(BaseModel):
    success: bool = Field(..., description="Whether the re-transcription was successful")
    text: str = Field("", description="The re-transcribed text")
    error: str = Field("", description="Error message if failed")

# Confirm Notion models
class ConfirmNotionRequest(BaseModel):
    transcript: str = Field(..., description="The transcript text to save to Notion")
    session_id: Optional[str] = Field(None, description="The session ID for audio cleanup")

# Append Notion models
class AppendNotionRequest(BaseModel):
    page_id: str = Field(..., description="The Notion page ID to append to")
    section_title: str = Field(..., description="The section title (e.g., 'Readability', 'Correctness', 'Ask AI')")
    content: str = Field(..., description="The content to append")

# Checkbox update models
class UpdateCheckboxRequest(BaseModel):
    page_id: str = Field(..., description="The Notion page ID to update")
    property_name: str = Field(..., description="The checkbox property name (e.g., 'Readability', 'Correctness', 'Ask AI')")
    checked: bool = Field(True, description="Whether to check or uncheck the checkbox")

# Google Sheet models
class SaveToSheetRequest(BaseModel):
    content: str = Field(..., description="The transcript content to save to Google Sheet")
    category: Optional[str] = Field(None, description="Optional category (e.g., 'todo')")

app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY is not set in environment variables. Some features will be disabled.")

# Notion configuration
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_AUTO_CREATE = os.getenv("NOTION_AUTO_CREATE", "true").lower() == "true"

if not NOTION_TOKEN or not NOTION_DATABASE_ID:
    logger.warning("NOTION_TOKEN or NOTION_DATABASE_ID not set. Notion integration will be disabled.")
else:
    logger.info("Notion integration enabled for automatic note creation")

# Initialize with a default model
try:
    llm_processor = get_llm_processor("gpt-4o")  # Default processor
except Exception as e:
    logger.warning(f"Failed to initialize LLM processor: {e}. Text processing will be disabled.")
    llm_processor = None

# Background task reference for cleanup
_cleanup_task = None

# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Start the word count monitoring service and ensure audio storage exists"""
    global _cleanup_task
    logger.info("Starting application...")
    
    # Ensure audio storage directory exists
    ensure_audio_storage_exists()
    
    # Start background audio cleanup task
    _cleanup_task = asyncio.create_task(cleanup_old_audio_files())
    logger.info("Audio cleanup background task started")
    
    # Start the word count monitor if Notion is configured
    if notion_service.enabled:
        success = await word_count_monitor.start()
        if success:
            logger.info("Word count monitoring started successfully")
        else:
            logger.warning("Failed to start word count monitoring")
    else:
        logger.info("Notion service not enabled, skipping word count monitoring")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of services"""
    global _cleanup_task
    logger.info("Shutting down application...")
    
    # Stop the audio cleanup task
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("Audio cleanup task stopped")
    
    # Stop the word count monitor
    await word_count_monitor.stop()
    logger.info("Word count monitoring stopped")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_realtime_page(request: Request):
    return FileResponse("static/realtime.html")

@app.get("/health")
async def health_check():
    """Health check endpoint for deployment platforms"""
    # Check Notion connectivity if configured
    notion_status = "disabled"
    if NOTION_TOKEN and NOTION_DATABASE_ID:
        try:
            notion_connected = await notion_service.check_connection()
            notion_status = "connected" if notion_connected else "error"
        except Exception:
            notion_status = "error"
    
    # Check word count monitor status
    word_count_status = "disabled"
    if notion_service.enabled:
        word_count_status = "running" if word_count_monitor.is_running else "stopped"
    
    # Check Google Sheet status
    google_sheet_status = "enabled" if google_sheet_service.enabled else "disabled"
    
    return {
        "status": "healthy",
        "openai_configured": OPENAI_API_KEY is not None,
        "llm_processor_ready": llm_processor is not None,
        "notion_status": notion_status,
        "content_analyzer_ready": content_analyzer.enabled,
        "auto_create_notes": NOTION_AUTO_CREATE,
        "word_count_monitor": word_count_status,
        "google_sheet_status": google_sheet_status
    }


class AudioProcessor:
    def __init__(self, target_sample_rate=24000):
        self.target_sample_rate = target_sample_rate
        self.source_sample_rate = 48000  # Most common sample rate for microphones
        
    def process_audio_chunk(self, audio_data):
        # Convert binary audio data to Int16 array
        pcm_data = np.frombuffer(audio_data, dtype=np.int16)
        
        # Convert to float32 for better precision during resampling
        float_data = pcm_data.astype(np.float32) / 32768.0
        
        # Resample from 48kHz to 24kHz
        resampled_data = scipy.signal.resample_poly(
            float_data, 
            self.target_sample_rate, 
            self.source_sample_rate
        )
        
        # Convert back to int16 while preserving amplitude
        resampled_int16 = (resampled_data * 32768.0).clip(-32768, 32767).astype(np.int16)
        return resampled_int16.tobytes()

    def save_audio_buffer(self, audio_buffer, filename):
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)  # Mono audio
            wf.setsampwidth(2)  # 2 bytes per sample (16-bit)
            wf.setframerate(self.target_sample_rate)
            wf.writeframes(b''.join(audio_buffer))
        logger.info(f"Saved audio buffer to {filename}")

@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("New WebSocket connection attempt")
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    
    # Session ID will be generated per recording, not per connection
    session_id = None
    
    # Add initial status update here
    await websocket.send_text(json.dumps({
        "type": "status",
        "status": "idle"  # Set initial status to idle (blue)
    }))
    
    client = None
    audio_processor = AudioProcessor()
    audio_buffer = []
    # Buffer for storing audio to file (accumulated during recording)
    audio_storage_buffer = []
    recording_stopped = asyncio.Event()
    openai_ready = asyncio.Event()
    pending_audio_chunks = []
    # Add synchronization for audio sending operations
    pending_audio_operations = 0
    audio_send_lock = asyncio.Lock()
    all_audio_sent = asyncio.Event()
    all_audio_sent.set()  # Initially set since no audio is pending
    
    # Track complete transcript for Notion integration
    complete_transcript = ""
    session_start_time = datetime.now()
    
    # Dual channel mode flag
    dual_channel_mode = False
    
    async def initialize_openai():
        nonlocal client
        try:
            # Clear the ready flag while initializing
            openai_ready.clear()
            
            client = OpenAIRealtimeAudioTextClient(os.getenv("OPENAI_API_KEY"))
            await client.connect()
            logger.info("Successfully connected to OpenAI client")
            
            # Register handlers after client is initialized
            client.register_handler("session.updated", lambda data: handle_generic_event("session.updated", data))
            client.register_handler("input_audio_buffer.cleared", lambda data: handle_generic_event("input_audio_buffer.cleared", data))
            client.register_handler("input_audio_buffer.speech_started", lambda data: handle_generic_event("input_audio_buffer.speech_started", data))
            client.register_handler("rate_limits.updated", lambda data: handle_generic_event("rate_limits.updated", data))
            client.register_handler("response.output_item.added", lambda data: handle_generic_event("response.output_item.added", data))
            client.register_handler("conversation.item.created", lambda data: handle_generic_event("conversation.item.created", data))
            client.register_handler("response.content_part.added", lambda data: handle_generic_event("response.content_part.added", data))
            client.register_handler("response.text.done", lambda data: handle_generic_event("response.text.done", data))
            client.register_handler("response.content_part.done", lambda data: handle_generic_event("response.content_part.done", data))
            client.register_handler("response.output_item.done", lambda data: handle_generic_event("response.output_item.done", data))
            client.register_handler("response.done", lambda data: handle_response_done(data))
            client.register_handler("error", lambda data: handle_error(data))
            client.register_handler("response.text.delta", lambda data: handle_text_delta(data))
            client.register_handler("response.created", lambda data: handle_response_created(data))
            
            openai_ready.set()  # Set ready flag after successful initialization
            await websocket.send_text(json.dumps({
                "type": "status",
                "status": "connected"
            }))
            return True
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI: {e}")
            openai_ready.clear()  # Ensure flag is cleared on failure
            await websocket.send_text(json.dumps({
                "type": "error",
                "content": "Failed to initialize OpenAI connection"
            }))
            return False

    # Move the handler definitions here (before initialize_openai)
    async def handle_text_delta(data):
        nonlocal complete_transcript
        try:
            delta_text = data.get("delta", "")
            
            # Accumulate text for Notion integration
            if delta_text:
                complete_transcript += delta_text
            
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(json.dumps({
                    "type": "text",
                    "content": delta_text,
                    "isNewResponse": False
                }))
                logger.info("Handled response.text.delta")
        except Exception as e:
            logger.error(f"Error in handle_text_delta: {str(e)}", exc_info=True)

    async def handle_response_created(data):
        await websocket.send_text(json.dumps({
            "type": "text",
            "content": "",
            "isNewResponse": True
        }))
        logger.info("Handled response.created")

    async def handle_error(data):
        error_msg = data.get("error", {}).get("message", "Unknown error")
        logger.error(f"OpenAI error: {error_msg}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "content": error_msg
        }))
        logger.info("Handled error message from OpenAI")

    async def handle_response_done(data):
        nonlocal client, complete_transcript
        logger.info("Handled response.done")
        recording_stopped.set()
        
        # Note: Automatic Notion creation is disabled
        # User must manually confirm transcript via /api/v1/confirm-notion
        # The transcript is sent to frontend for user review
        current_transcript = complete_transcript.strip()
        logger.info(f"Transcription complete, awaiting user confirmation: {current_transcript[:100]}...")
        
        # Convert to Traditional Chinese if needed
        converted_transcript, was_converted = convert_if_needed(current_transcript)
        if was_converted:
            logger.info(f"Converted transcript to Traditional Chinese: {converted_transcript[:100]}...")
        
        # reset transcript to avoid cumulative note content
        complete_transcript = ""
        
        if client:
            try:
                await client.close()
                client = None
                openai_ready.clear()
                
                # Send converted transcript to frontend for replacement
                if was_converted:
                    await websocket.send_text(json.dumps({
                        "type": "transcript_converted",
                        "content": converted_transcript,
                        "original": current_transcript
                    }))
                    logger.info("Sent converted Traditional Chinese transcript to frontend")
                
                # Send transcription_complete event with session_id for frontend to track
                await websocket.send_text(json.dumps({
                    "type": "transcription_complete",
                    "session_id": session_id
                }))
                await websocket.send_text(json.dumps({
                    "type": "status",
                    "status": "idle"
                }))
                logger.info("Connection closed after response completion")
            except Exception as e:
                logger.error(f"Error closing client after response done: {str(e)}")

    async def handle_generic_event(event_type, data):
        logger.info(f"Handled {event_type} with data: {json.dumps(data, ensure_ascii=False)}")

    # Create a queue to handle incoming audio chunks
    audio_queue = asyncio.Queue()

    async def receive_messages():
        nonlocal client
        
        try:
            while True:
                if websocket.client_state == WebSocketState.DISCONNECTED:
                    logger.info("WebSocket client disconnected")
                    openai_ready.clear()
                    break
                    
                try:
                    # Add timeout to prevent infinite waiting
                    data = await asyncio.wait_for(websocket.receive(), timeout=30.0)
                    
                    if "bytes" in data:
                        processed_audio = audio_processor.process_audio_chunk(data["bytes"])
                        
                        # Always store audio for potential re-transcription
                        audio_storage_buffer.append(processed_audio)
                        
                        if not openai_ready.is_set():
                            logger.debug("OpenAI not ready, buffering audio chunk")
                            pending_audio_chunks.append(processed_audio)
                        elif client:
                            # Track pending audio operations
                            async with audio_send_lock:
                                nonlocal pending_audio_operations
                                pending_audio_operations += 1
                                all_audio_sent.clear()  # Clear the event since we have pending operations
                            
                            try:
                                await client.send_audio(processed_audio)
                                await websocket.send_text(json.dumps({
                                    "type": "status",
                                    "status": "connected"
                                }))
                                logger.debug(f"Sent audio chunk, size: {len(processed_audio)} bytes")
                            finally:
                                # Mark operation as complete
                                async with audio_send_lock:
                                    pending_audio_operations -= 1
                                    if pending_audio_operations == 0:
                                        all_audio_sent.set()  # Set event when all operations complete
                        else:
                            logger.warning("Received audio but client is not initialized")
                            
                    elif "text" in data:
                        msg = json.loads(data["text"])
                        
                        if msg.get("type") == "start_recording":
                            # Generate new session ID for each recording
                            session_id = generate_session_id()
                            logger.info(f"Generated new session ID: {session_id}")
                            
                            # Check if dual channel mode is enabled
                            nonlocal dual_channel_mode
                            dual_channel_mode = msg.get("dual_channel", False)
                            logger.info(f"Dual channel mode: {dual_channel_mode}")
                            
                            # Send new session_id to frontend
                            await websocket.send_text(json.dumps({
                                "type": "session_created",
                                "session_id": session_id
                            }))
                            
                            # Reset transcript for new session
                            complete_transcript = ""
                            session_start_time = datetime.now()
                            
                            # Clear audio storage buffer for new recording
                            audio_storage_buffer.clear()
                            logger.info(f"Started new recording session: {session_id}")
                            
                            # Update status to connecting while initializing OpenAI
                            await websocket.send_text(json.dumps({
                                "type": "status",
                                "status": "connecting"
                            }))
                            if not await initialize_openai():
                                continue
                            recording_stopped.clear()
                            pending_audio_chunks.clear()
                            
                            # Send any buffered chunks
                            if pending_audio_chunks and client:
                                logger.info(f"Sending {len(pending_audio_chunks)} buffered chunks")
                                for chunk in pending_audio_chunks:
                                    # Track each buffered chunk operation
                                    async with audio_send_lock:
                                        pending_audio_operations += 1
                                        all_audio_sent.clear()
                                    
                                    try:
                                        await client.send_audio(chunk)
                                    finally:
                                        async with audio_send_lock:
                                            pending_audio_operations -= 1
                                            if pending_audio_operations == 0:
                                                all_audio_sent.set()
                                pending_audio_chunks.clear()
                            
                        elif msg.get("type") == "stop_recording":
                            if client:
                                # CRITICAL FIX: Wait for all pending audio operations to complete
                                # before committing to prevent data loss
                                logger.info("Stop recording received, waiting for all audio to be sent...")
                                
                                # Wait for any pending audio chunks to be sent (with timeout for safety)
                                try:
                                    await asyncio.wait_for(all_audio_sent.wait(), timeout=5.0)
                                    logger.info("All pending audio operations completed")
                                except asyncio.TimeoutError:
                                    logger.warning("Timeout waiting for audio operations to complete, proceeding anyway")
                                    # Reset the pending counter to prevent deadlock
                                    async with audio_send_lock:
                                        pending_audio_operations = 0
                                        all_audio_sent.set()
                                
                                # Save audio to file for potential re-transcription
                                audio_file_path = None
                                if audio_storage_buffer:
                                    audio_file_path = get_audio_file_path(session_id)
                                    try:
                                        audio_processor.save_audio_buffer(audio_storage_buffer, audio_file_path)
                                        logger.info(f"Saved audio file: {audio_file_path} ({len(audio_storage_buffer)} chunks)")
                                    except Exception as e:
                                        logger.error(f"Failed to save audio file: {e}")
                                        audio_file_path = None
                                
                                # Add a small buffer to ensure network operations complete
                                await asyncio.sleep(0.1)
                                
                                logger.info("All audio sent, committing audio buffer...")
                                await client.commit_audio()
                                await client.start_response(PROMPTS['paraphrase-gpt-realtime'])
                                await recording_stopped.wait()
                                # Don't close the client here, let the disconnect timer handle it
                                # Update client status to connected (waiting for response)
                                await websocket.send_text(json.dumps({
                                    "type": "status",
                                    "status": "connected"
                                }))
                                
                                # If dual channel mode is enabled, also transcribe with Gemini
                                if dual_channel_mode and audio_file_path:
                                    logger.info("Dual channel mode: Starting Gemini transcription...")
                                    await websocket.send_text(json.dumps({
                                        "type": "gemini_transcribing"
                                    }))
                                    
                                    try:
                                        transcriber = get_gemini_transcriber()
                                        gemini_result = await transcriber.transcribe(audio_file_path)
                                        
                                        if gemini_result.success:
                                            logger.info(f"Gemini transcription successful: {gemini_result.text[:100]}...")
                                            
                                            # Convert to Traditional Chinese if needed
                                            gemini_text, gemini_was_converted = convert_if_needed(gemini_result.text)
                                            if gemini_was_converted:
                                                logger.info(f"Gemini transcript converted to Traditional Chinese")
                                            
                                            await websocket.send_text(json.dumps({
                                                "type": "gemini_transcription",
                                                "text": gemini_text,
                                                "was_converted": gemini_was_converted
                                            }))
                                        else:
                                            logger.error(f"Gemini transcription failed: {gemini_result.error}")
                                            await websocket.send_text(json.dumps({
                                                "type": "error",
                                                "content": f"Gemini transcription failed: {gemini_result.error}"
                                            }))
                                    except Exception as e:
                                        logger.error(f"Error in Gemini transcription: {e}")
                                        await websocket.send_text(json.dumps({
                                            "type": "error",
                                            "content": f"Gemini transcription error: {str(e)}"
                                        }))

                except asyncio.TimeoutError:
                    logger.debug("No message received for 30 seconds")
                    continue
                except Exception as e:
                    logger.error(f"Error in receive_messages loop: {str(e)}", exc_info=True)
                    break
                
        finally:
            # Cleanup when the loop exits
            if client:
                try:
                    await client.close()
                except Exception as e:
                    logger.error(f"Error closing client in receive_messages: {str(e)}")
            logger.info("Receive messages loop ended")

    async def send_audio_messages():
        while True:
            try:
                processed_audio = await audio_queue.get()
                if processed_audio is None:
                    break
                
                # Add validation
                if len(processed_audio) == 0:
                    logger.warning("Empty audio chunk received, skipping")
                    continue
                
                # Append the processed audio to the buffer
                audio_buffer.append(processed_audio)

                await client.send_audio(processed_audio)
                logger.info(f"Audio chunk sent to OpenAI client, size: {len(processed_audio)} bytes")
                
            except Exception as e:
                logger.error(f"Error in send_audio_messages: {str(e)}", exc_info=True)
                break

        # After processing all audio, set the event
        recording_stopped.set()

    # Start concurrent tasks for receiving and sending
    receive_task = asyncio.create_task(receive_messages())
    send_task = asyncio.create_task(send_audio_messages())

    try:
        # Wait for both tasks to complete
        await asyncio.gather(receive_task, send_task)
    finally:
        if client:
            await client.close()
            logger.info("OpenAI client connection closed")

async def create_notion_note_from_transcript(transcript: str):
    """Create a Notion note from completed STT transcript"""
    try:
        logger.info(f"Creating Notion note for transcript: {transcript[:100]}...")
        
        # Analyze content using Gemini
        analysis = await content_analyzer.analyze_content(transcript)
        
        # Create Notion note with analyzed content
        result = await notion_service.create_stt_note(
            content=transcript,
            title=analysis.get("title"),
            summary=analysis.get("summary"),
            category=analysis.get("category"),
            confidence=analysis.get("confidence")
        )
        
        if result:
            logger.info(f"Successfully created Notion note: {result['url']}")
            return result  # Return the result containing page_id
        else:
            logger.warning("Failed to create Notion note - service may be disabled")
            return None
            
    except Exception as e:
        logger.error(f"Error creating Notion note from transcript: {e}", exc_info=True)

@app.post(
    "/api/v1/readability",
    response_model=ReadabilityResponse,
    summary="Enhance Text Readability",
    description="Improve the readability of the provided text using GPT-4."
)
async def enhance_readability(request: ReadabilityRequest):
    prompt = PROMPTS.get('readability-enhance')
    if not prompt:
        raise HTTPException(status_code=500, detail="Readability prompt not found.")

    try:
        async def text_generator():
            # Use gpt-4o specifically for readability
            async for part in llm_processor.process_text(request.text, prompt, model="gpt-4o"):
                yield part

        return StreamingResponse(text_generator(), media_type="text/plain")

    except Exception as e:
        logger.error(f"Error enhancing readability: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing readability enhancement.")

@app.post(
    "/api/v1/ask_ai",
    response_model=AskAIResponse,
    summary="Ask AI a Question",
    description="Ask AI to provide insights using Gemini 2.5 Pro model."
)
def ask_ai(request: AskAIRequest):
    prompt = PROMPTS.get('ask-ai')
    if not prompt:
        raise HTTPException(status_code=500, detail="Ask AI prompt not found.")

    try:
        # Use Gemini 2.5 Pro specifically for ask_ai
        gemini_processor = get_llm_processor("gemini-2.5-pro")
        answer = gemini_processor.process_text_sync(request.text, prompt, model="gemini-2.5-pro")
        return AskAIResponse(answer=answer)
    except Exception as e:
        logger.error(f"Error processing AI question: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing AI question.")

@app.post(
    "/api/v1/correctness",
    response_model=CorrectnessResponse,
    summary="Check Factual Correctness",
    description="Analyze the text for factual accuracy using GPT-4o."
)
async def check_correctness(request: CorrectnessRequest):
    prompt = PROMPTS.get('correctness-check')
    if not prompt:
        raise HTTPException(status_code=500, detail="Correctness prompt not found.")

    try:
        async def text_generator():
            # Specifically use gpt-4o for correctness checking
            async for part in llm_processor.process_text(request.text, prompt, model="gpt-4o"):
                yield part

        return StreamingResponse(text_generator(), media_type="text/plain")

    except Exception as e:
        logger.error(f"Error checking correctness: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing correctness check.")

# Word count monitoring endpoints
@app.get(
    "/api/v1/word-count/status",
    response_model=WordCountStatusResponse,
    summary="Get Word Count Monitor Status",
    description="Get the current status and statistics of the word count monitoring service."
)
async def get_word_count_status():
    try:
        status = word_count_monitor.get_status()
        return WordCountStatusResponse(
            status="running" if status["running"] else "stopped",
            running=status["running"],
            stats=status
        )
    except Exception as e:
        logger.error(f"Error getting word count status: {e}")
        raise HTTPException(status_code=500, detail="Error getting monitor status")

@app.get(
    "/api/v1/word-count/health",
    summary="Word Count Monitor Health Check",
    description="Perform a health check on the word count monitoring service."
)
async def word_count_health_check():
    try:
        health = await word_count_monitor.health_check()
        status_code = 200 if health["healthy"] else 503
        return health
    except Exception as e:
        logger.error(f"Error in word count health check: {e}")
        return {"healthy": False, "error": str(e)}

@app.post(
    "/api/v1/word-count/manual-update",
    response_model=ManualUpdateResponse,
    summary="Manual Word Count Update",
    description="Manually trigger word count update for a specific page or all pages."
)
async def manual_word_count_update(request: ManualUpdateRequest):
    try:
        if request.page_id:
            # Update specific page
            word_count = await word_count_monitor.manual_update_page(request.page_id)
            if word_count is not None:
                return ManualUpdateResponse(
                    success=True,
                    message=f"Successfully updated word count: {word_count} words",
                    details={"page_id": request.page_id, "word_count": word_count}
                )
            else:
                return ManualUpdateResponse(
                    success=False,
                    message="Failed to update word count for the specified page"
                )
        else:
            # Update all pages
            result = await word_count_monitor.manual_update_all()
            if result["success"]:
                return ManualUpdateResponse(
                    success=True,
                    message=f"Updated {result['updated']} pages out of {result['total']}",
                    details=result
                )
            else:
                return ManualUpdateResponse(
                    success=False,
                    message=result["message"]
                )
    except Exception as e:
        logger.error(f"Error in manual word count update: {e}")
        return ManualUpdateResponse(
            success=False,
            message=f"Error during update: {str(e)}"
        )

@app.post(
    "/api/v1/word-count/webhook",
    summary="Webhook Endpoint",
    description="Webhook endpoint for third-party services (like Zapier) to trigger word count updates."
)
async def word_count_webhook(request: dict):
    try:
        # Extract page_id from webhook payload if available
        page_id = request.get("page_id")
        
        if page_id:
            word_count = await word_count_monitor.manual_update_page(page_id)
            return {
                "success": word_count is not None,
                "page_id": page_id,
                "word_count": word_count
            }
        else:
            # Trigger check for all pages
            await word_count_monitor._monitor_pages()
            return {"success": True, "message": "Monitoring check triggered"}
            
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}")
        return {"success": False, "error": str(e)}

# Re-transcription and Notion confirmation endpoints
@app.post(
    "/api/v1/retranscribe",
    response_model=RetranscribeResponse,
    summary="Re-transcribe Audio",
    description="Re-transcribe a saved audio file using Gemini API."
)
async def retranscribe_audio(request: RetranscribeRequest):
    """Re-transcribe audio using Gemini when the initial transcription is unsatisfactory"""
    try:
        audio_file_path = get_audio_file_path(request.session_id)
        
        if not os.path.exists(audio_file_path):
            logger.error(f"Audio file not found: {audio_file_path}")
            return RetranscribeResponse(
                success=False,
                error=f"Audio file not found, session_id: {request.session_id}"
            )
        
        logger.info(f"Re-transcribing audio file: {audio_file_path}")
        
        # Get the Gemini transcriber and transcribe
        transcriber = get_gemini_transcriber()
        result = await transcriber.transcribe(audio_file_path)
        
        if result.success:
            logger.info(f"Re-transcription successful: {result.text[:100]}...")
            
            # Convert to Traditional Chinese if needed
            converted_text, was_converted = convert_if_needed(result.text)
            if was_converted:
                logger.info(f"Re-transcription converted to Traditional Chinese")
            
            return RetranscribeResponse(
                success=True,
                text=converted_text
            )
        else:
            logger.error(f"Re-transcription failed: {result.error}")
            return RetranscribeResponse(
                success=False,
                error=result.error
            )
            
    except Exception as e:
        logger.error(f"Error in retranscribe_audio: {e}", exc_info=True)
        return RetranscribeResponse(
            success=False,
            error=f"Error during re-transcription: {str(e)}"
        )

@app.post(
    "/api/v1/confirm-notion",
    summary="Confirm and Save to Notion",
    description="Manually confirm and save transcript to Notion after user approval."
)
async def confirm_notion(request: ConfirmNotionRequest):
    """Save the confirmed transcript to Notion and clean up audio file"""
    try:
        if not request.transcript.strip():
            return {"success": False, "error": "Transcript is empty"}
        
        logger.info(f"Confirming transcript to Notion: {request.transcript[:100]}...")
        
        # Create Notion note
        result = await create_notion_note_from_transcript(request.transcript)
        
        # Clean up audio file if session_id provided
        if request.session_id:
            audio_file_path = get_audio_file_path(request.session_id)
            if os.path.exists(audio_file_path):
                try:
                    os.remove(audio_file_path)
                    logger.info(f"Cleaned up audio file: {audio_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up audio file: {e}")
        
        # Extract page_id from result
        page_id = result.get("page_id") if result else None
        
        return {
            "success": True,
            "message": "Successfully saved to Notion",
            "page_id": page_id,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error in confirm_notion: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Error saving to Notion: {str(e)}"
        }

@app.post(
    "/api/v1/append-notion",
    summary="Append Content to Notion Page",
    description="Append additional content (like Readability, Correctness results) to an existing Notion page."
)
async def append_notion(request: AppendNotionRequest):
    """Append content with H1 section title to an existing Notion page"""
    try:
        if not request.content.strip():
            return {"success": False, "error": "Content is empty"}
        
        logger.info(f"Appending to Notion page {request.page_id}: {request.section_title}")
        
        # Append to the Notion page
        success = await notion_service.append_to_page(
            page_id=request.page_id,
            section_title=request.section_title,
            content=request.content
        )
        
        if success:
            return {
                "success": True,
                "message": f"Successfully appended {request.section_title} to Notion"
            }
        else:
            return {
                "success": False,
                "error": "Failed to append to Notion page"
            }
        
    except Exception as e:
        logger.error(f"Error in append_notion: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Error appending to Notion: {str(e)}"
        }

@app.post(
    "/api/v1/update-checkbox",
    summary="Update Checkbox in Notion",
    description="Update a checkbox property in a Notion page (e.g., Readability, Correctness, Ask AI)."
)
async def update_checkbox(request: UpdateCheckboxRequest):
    """Update a checkbox property in the Notion page"""
    try:
        logger.info(f"Updating checkbox '{request.property_name}' for page {request.page_id}: {request.checked}")
        
        success = await notion_service.update_checkbox(
            page_id=request.page_id,
            property_name=request.property_name,
            checked=request.checked
        )
        
        if success:
            return {
                "success": True,
                "message": f"Successfully updated {request.property_name} checkbox"
            }
        else:
            return {
                "success": False,
                "error": f"Failed to update {request.property_name} checkbox"
            }
        
    except Exception as e:
        logger.error(f"Error in update_checkbox: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Error updating checkbox: {str(e)}"
        }

@app.post(
    "/api/v1/save-to-sheet",
    summary="Save Transcript to Google Sheet",
    description="Save transcript content to Google Sheet with UTC+8 timestamp."
)
async def save_to_sheet(request: SaveToSheetRequest):
    """Save transcript to Google Sheet"""
    try:
        if not request.content.strip():
            return {"success": False, "error": "Content is empty"}
        
        logger.info(f"Saving to Google Sheet: {request.content[:50]}... (category: {request.category})")
        
        result = await google_sheet_service.insert_transcript(
            content=request.content,
            category=request.category
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error in save_to_sheet: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Error saving to Google Sheet: {str(e)}"
        }

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=3005)
