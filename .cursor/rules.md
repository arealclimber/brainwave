# Brainwave Development Rules

> A comprehensive development guide for the Brainwave real-time speech recognition and summarization tool.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Environment Variables](#environment-variables)
5. [Coding Conventions](#coding-conventions)
6. [API Design Patterns](#api-design-patterns)
7. [WebSocket Protocol](#websocket-protocol)
8. [LLM Integration](#llm-integration)
9. [Notion Integration](#notion-integration)
10. [Testing Strategy](#testing-strategy)
11. [Deployment](#deployment)

---

## Project Overview

Brainwave is a real-time speech recognition and summarization tool that:

- Captures audio input via browser microphone
- Streams audio to OpenAI Realtime API for speech-to-text
- Processes transcriptions with LLMs (GPT-4o, Gemini) for enhancement
- Automatically creates notes in Notion with AI-generated metadata
- Monitors and updates word counts for Notion pages

### Key Features

- **Real-time STT**: Low-latency speech recognition using OpenAI Realtime API
- **Text Enhancement**: Readability improvement, correctness checking, AI insights
- **Notion Integration**: Automatic note creation with title, summary, and categorization
- **Word Count Monitoring**: Scheduled tracking of content changes

---

## Architecture

### Directory Structure

```
brainwave/
├── realtime_server.py        # FastAPI main entry, WebSocket handling, REST APIs
├── openai_realtime_client.py # OpenAI Realtime API WebSocket client
├── llm_processor.py          # LLM processor abstraction (GPT/Gemini)
├── notion_service.py         # Notion API integration service
├── content_analyzer.py       # Content analysis (title/summary/category generation)
├── monitor.py                # Word count monitoring scheduler (APScheduler)
├── state_manager.py          # Page state management for change detection
├── prompts.py                # LLM prompts and templates
├── main.py                   # Alternative entry point
├── static/                   # Frontend assets
│   ├── realtime.html         # Main UI page
│   ├── main.js               # Frontend JavaScript
│   ├── style.css             # Styles
│   └── favicon.ico           # App icon
├── tests/                    # Test suite
│   ├── test_realtime_server.py
│   ├── test_notion_service.py
│   ├── test_llm_processor.py
│   ├── test_content_analyzer.py
│   ├── test_audio_processor.py
│   └── test_openai_realtime_client.py
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container configuration
└── railway.toml              # Railway deployment config
```

### Data Flow

```
┌─────────────┐     Audio      ┌─────────────────┐     Audio      ┌─────────────────┐
│   Browser   │ ──────────────►│  FastAPI Server │ ──────────────►│  OpenAI Realtime│
│  (Frontend) │                │  (WebSocket)    │                │      API        │
└─────────────┘                └─────────────────┘                └─────────────────┘
       ▲                              │                                   │
       │                              │                                   │
       │         Text Response        │         Transcription             │
       └──────────────────────────────┴───────────────────────────────────┘
                                      │
                                      ▼
                          ┌─────────────────────┐
                          │   Content Analyzer  │
                          │   (Gemini 2.5)      │
                          └─────────────────────┘
                                      │
                                      ▼
                          ┌─────────────────────┐
                          │   Notion Service    │
                          │   (Create Note)     │
                          └─────────────────────┘
```

---

## Tech Stack

### Backend

| Component | Technology | Version/Notes |
|-----------|------------|---------------|
| Framework | FastAPI | High-performance async web framework |
| Server | Uvicorn | ASGI server, port 3005 |
| WebSocket | websockets | < 14 (compatibility requirement) |
| Scheduling | APScheduler | 3.10.4, AsyncIOScheduler |
| Audio Processing | numpy, scipy | 48kHz → 24kHz resampling |

### LLM Services

| Service | Model | Use Case |
|---------|-------|----------|
| OpenAI Realtime API | gpt-4o-realtime-preview | Speech-to-text |
| OpenAI Chat API | gpt-4o | Readability, Correctness |
| Google Gemini | gemini-2.5-pro | Ask AI feature |
| Google Gemini | gemini-2.5-flash | Content analysis |

### External Services

| Service | Purpose |
|---------|---------|
| Notion API | Note storage and management |
| Railway | Deployment platform |

### Frontend

| Technology | Purpose |
|------------|---------|
| Vanilla JavaScript | Audio capture, WebSocket client |
| Web Audio API | Microphone access, audio processing |
| CSS3 | Styling with dark mode support |

---

## Environment Variables

### Required

```bash
OPENAI_API_KEY=sk-...          # OpenAI API key for STT and text processing
```

### Optional (Notion Integration)

```bash
NOTION_TOKEN=secret_...        # Notion integration token
NOTION_DATABASE_ID=...         # Target database ID
NOTION_AUTO_CREATE=true        # Enable automatic note creation (default: true)
```

### Optional (Gemini)

```bash
GOOGLE_API_KEY=...             # Google API key for Gemini models
```

### Naming Convention

- Use SCREAMING_SNAKE_CASE for environment variables
- Prefix service-specific variables with service name (e.g., `NOTION_`, `GOOGLE_`)

---

## Coding Conventions

### 1. Module Structure

Each service module follows this pattern:

```python
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

class ServiceName:
    """Service description"""
    
    def __init__(self):
        # Initialize with environment variables
        self.enabled = False
        # ... setup logic
    
    async def method_name(self) -> Optional[Dict]:
        """Method description"""
        if not self.enabled:
            logger.warning("Service not enabled")
            return None
        # ... implementation

# Global singleton instance
service_name = ServiceName()
```

### 2. Singleton Pattern

Services are instantiated as module-level singletons:

```python
# At the bottom of each service module
notion_service = NotionService()
content_analyzer = ContentAnalyzer()
word_count_monitor = NotionWordCountMonitor()
state_manager = StateManager()
```

### 3. Async/Await Guidelines

- Use `async def` for I/O-bound operations (API calls, file operations)
- Use `asyncio.create_task()` for fire-and-forget operations
- Use `asyncio.gather()` for parallel operations
- Always handle `asyncio.TimeoutError` for network operations

```python
# Good: Non-blocking background task
asyncio.create_task(create_notion_note_from_transcript(transcript))

# Good: Parallel execution
results = await asyncio.gather(
    self._generate_title(content),
    self._generate_summary(content),
    self._categorize_content(content)
)
```

### 4. Error Handling

```python
try:
    result = await some_operation()
except SpecificException as e:
    logger.error(f"Descriptive message: {e}", exc_info=True)
    return fallback_value
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise
```

### 5. Logging Standards

```python
# Configure at module level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Usage levels
logger.debug("Detailed debugging info")      # Development only
logger.info("Normal operation events")       # Key milestones
logger.warning("Recoverable issues")         # Degraded service
logger.error("Operation failures")           # Errors with recovery
```

### 6. Type Hints

Always use type hints for function signatures:

```python
from typing import Optional, Dict, List, AsyncGenerator

async def process_text(
    self, 
    text: str, 
    prompt: str, 
    model: Optional[str] = None
) -> AsyncGenerator[str, None]:
    ...
```

---

## API Design Patterns

### REST Endpoints

#### Naming Convention

```
/api/v1/{resource}          # Resource operations
/api/v1/{resource}/{action} # Resource actions
```

#### Current Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Main HTML page |
| GET | `/health` | Health check |
| POST | `/api/v1/readability` | Enhance text readability |
| POST | `/api/v1/correctness` | Check factual correctness |
| POST | `/api/v1/ask_ai` | Ask AI for insights |
| GET | `/api/v1/word-count/status` | Monitor status |
| GET | `/api/v1/word-count/health` | Monitor health check |
| POST | `/api/v1/word-count/manual-update` | Trigger manual update |
| POST | `/api/v1/word-count/webhook` | Webhook for external triggers |
| WS | `/api/v1/ws` | WebSocket for audio streaming |

### Pydantic Models

Define request/response models with Field descriptions:

```python
from pydantic import BaseModel, Field
from typing import Optional

class ReadabilityRequest(BaseModel):
    text: str = Field(..., description="The text to improve readability for.")

class ReadabilityResponse(BaseModel):
    enhanced_text: str = Field(..., description="The text with improved readability.")
```

### Streaming Responses

For LLM-generated content, use `StreamingResponse`:

```python
from fastapi.responses import StreamingResponse

async def text_generator():
    async for part in llm_processor.process_text(text, prompt):
        yield part

return StreamingResponse(text_generator(), media_type="text/plain")
```

---

## WebSocket Protocol

### Connection Endpoint

```
ws://{host}/api/v1/ws
wss://{host}/api/v1/ws  # Production
```

### Message Types

#### Client → Server

```javascript
// Start recording
{ "type": "start_recording" }

// Stop recording
{ "type": "stop_recording" }

// Audio data: Send as binary (ArrayBuffer)
ws.send(audioBuffer)  // Int16Array, 24kHz mono
```

#### Server → Client

```javascript
// Connection status
{ "type": "status", "status": "idle" | "connecting" | "connected" }

// Text response (streaming)
{ "type": "text", "content": "...", "isNewResponse": true | false }

// Error
{ "type": "error", "content": "Error message" }
```

### Audio Format

| Property | Value |
|----------|-------|
| Input Sample Rate | 48kHz (from browser) |
| Output Sample Rate | 24kHz (to OpenAI) |
| Channels | 1 (mono) |
| Bit Depth | 16-bit (Int16) |
| Chunk Size | 24000 samples (~0.5s at 48kHz) |

---

## LLM Integration

### Processor Abstraction

Use `get_llm_processor()` factory function:

```python
from llm_processor import get_llm_processor

# For OpenAI models
processor = get_llm_processor("gpt-4o")

# For Gemini models
processor = get_llm_processor("gemini-2.5-pro")
```

### Model Selection Guidelines

| Use Case | Recommended Model | Reason |
|----------|-------------------|--------|
| STT (Realtime) | gpt-4o-realtime-preview | Native audio support |
| Readability | gpt-4o | High quality text processing |
| Correctness | gpt-4o | Factual accuracy |
| Ask AI | gemini-2.5-pro | Deep insights, cost-effective |
| Content Analysis | gemini-2.5-flash | Fast, cheap for metadata |

### Prompt Management

All prompts are defined in `prompts.py`:

```python
from prompts import PROMPTS, CONTENT_ANALYSIS_PROMPTS

# Main prompts
PROMPTS['paraphrase-gpt-realtime']
PROMPTS['readability-enhance']
PROMPTS['ask-ai']
PROMPTS['correctness-check']

# Content analysis prompts
CONTENT_ANALYSIS_PROMPTS['title_generation']
CONTENT_ANALYSIS_PROMPTS['summary_generation']
CONTENT_ANALYSIS_PROMPTS['categorization']
```

### Prompt Guidelines

1. Be explicit about output format
2. Specify language handling (preserve original, output in English, etc.)
3. Include "don't translate" instructions for multilingual content
4. Limit response scope to prevent over-generation

---

## Notion Integration

### Database Schema

Required properties in Notion database:

| Property | Type | Description |
|----------|------|-------------|
| Idea | title | Page title |
| Status | status | "Raw Capture" for new notes |
| Priority | select | Default: "Low" |
| Brief | rich_text | AI-generated summary |
| Category | multi_select | Content category |
| Words | number | Word count |
| Last edited time | last_edited_time | For change detection |

### Word Counting

Supports both English and Chinese:

```python
def count_words(self, text: str) -> int:
    # Chinese characters: each character = 1 word
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    chinese_count = len(chinese_chars)
    
    # English words: standard word boundary
    english_text = re.sub(r'[\u4e00-\u9fff]', '', text)
    english_words = re.findall(r'\b\w+\b', english_text)
    english_count = len(english_words)
    
    return chinese_count + english_count
```

### Monitoring Schedule

- Runs daily at 3 AM UTC+8 (7 PM UTC)
- Detects changes by comparing `last_edited_time`
- Updates word count only for modified pages
- State persisted in `notion_state.json`

---

## Testing Strategy

### Framework

```bash
pytest tests/                    # Run all tests
pytest -v tests/                 # Verbose output
pytest tests/test_specific.py   # Single file
```

### Test Structure

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

class TestServiceName:
    
    def test_sync_method(self):
        """Test synchronous method"""
        pass
    
    @pytest.mark.asyncio
    async def test_async_method(self):
        """Test asynchronous method"""
        pass

@pytest.fixture
def mock_external_service():
    with patch('module.ExternalService') as mock:
        yield mock
```

### Mocking Guidelines

1. **Mock external APIs** (OpenAI, Gemini, Notion)
2. **Use AsyncMock** for async methods
3. **Patch at usage location**, not definition

```python
# Good: Patch where it's used
@patch('realtime_server.get_llm_processor')

# For async generators
async def mock_generator():
    yield "chunk1"
    yield "chunk2"
mock.process_text.return_value = mock_generator()
```

### Test Environment

```bash
export OPENAI_API_KEY='test_key'
export GOOGLE_API_KEY='test_key'
export NOTION_TOKEN='test_token'
export NOTION_DATABASE_ID='test_db_id'
```

---

## Deployment

### Local Development

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
uvicorn realtime_server:app --host 0.0.0.0 --port 3005

# Or with auto-reload
uvicorn realtime_server:app --reload --port 3005
```

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 3005
CMD ["sh", "-c", "uvicorn realtime_server:app --host 0.0.0.0 --port ${PORT:-3005}"]
```

```bash
docker build -t brainwave .
docker run -p 3005:3005 -e OPENAI_API_KEY=sk-... brainwave
```

### Railway

Configuration in `railway.toml`:

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

### Health Check

The `/health` endpoint returns:

```json
{
  "status": "healthy",
  "openai_configured": true,
  "llm_processor_ready": true,
  "notion_status": "connected",
  "content_analyzer_ready": true,
  "auto_create_notes": true,
  "word_count_monitor": "running"
}
```

---

## Quick Reference

### Adding a New API Endpoint

1. Define Pydantic request/response models
2. Add prompt to `prompts.py` if needed
3. Create endpoint in `realtime_server.py`
4. Add tests in `tests/test_realtime_server.py`

### Adding a New LLM Feature

1. Choose appropriate model (GPT vs Gemini)
2. Add prompt to `prompts.py`
3. Use `get_llm_processor()` factory
4. Handle streaming for long responses

### Debugging WebSocket Issues

1. Check browser console for connection status
2. Monitor server logs for message types
3. Verify audio format (sample rate, bit depth)
4. Check OpenAI API key validity

---

*Last updated: December 2024*

