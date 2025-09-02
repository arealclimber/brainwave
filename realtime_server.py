import asyncio
import json
import os
import numpy as np
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

# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Start the word count monitoring service"""
    logger.info("Starting application...")
    
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
    logger.info("Shutting down application...")
    
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
    
    return {
        "status": "healthy",
        "openai_configured": OPENAI_API_KEY is not None,
        "llm_processor_ready": llm_processor is not None,
        "notion_status": notion_status,
        "content_analyzer_ready": content_analyzer.enabled,
        "auto_create_notes": NOTION_AUTO_CREATE,
        "word_count_monitor": word_count_status
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
    
    # Add initial status update here
    await websocket.send_text(json.dumps({
        "type": "status",
        "status": "idle"  # Set initial status to idle (blue)
    }))
    
    client = None
    audio_processor = AudioProcessor()
    audio_buffer = []
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
        
        # Process transcript for Notion integration (async to not block the response)
        if complete_transcript.strip() and NOTION_AUTO_CREATE:
            asyncio.create_task(create_notion_note_from_transcript(complete_transcript.strip()))
        
        if client:
            try:
                await client.close()
                client = None
                openai_ready.clear()
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
                            # Reset transcript for new session
                            complete_transcript = ""
                            session_start_time = datetime.now()
                            
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
        else:
            logger.warning("Failed to create Notion note - service may be disabled")
            
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

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=3005)
