// Global state
let ws, audioContext, processor, source, stream;
let isRecording = false;
let timerInterval;
let startTime;
let audioBuffer = new Int16Array(0);
let wsConnected = false;
let streamInitialized = false;
let isAutoStarted = false;

// Session tracking
let currentSessionId = null;
let isConfirmingNotion = false;

// Multi textbox state
let isDualMode = false;
let selectedTranscriptBox = "openai"; // 'openai' | 'builder' | 'builderLong' | 'gemini'
let isSaveToSheetEnabled = true;
let isTodoEnabled = false;

// Batch transcribe flags (independent, can run concurrently)
let isBuilderTranscribing = false;
let isBuilderLongTranscribing = false;
let isGeminiTranscribing = false;

// Tab system state
const tabResults = {
  read: { content: "", source: "" },
  corrected: { content: "", source: "" },
  asked: { content: "", source: "" },
};
let activeTab = null;
let savedNotionPageId = null;

const tabAppendedToNotion = {
  read: false,
  corrected: false,
  asked: false,
};

// DOM elements
const recordButton = document.getElementById("recordButton");
const transcript = document.getElementById("transcript");
const enhancedTranscript = document.getElementById("enhancedTranscript");
const copyButton = document.getElementById("copyButton");
const copyEnhancedButton = document.getElementById("copyEnhancedButton");
const readabilityButton = document.getElementById("readabilityButton");
const askAIButton = document.getElementById("askAIButton");
const correctnessButton = document.getElementById("correctnessButton");
const confirmNotionButton = document.getElementById("confirmNotionButton");

// Batch transcribe & save audio buttons
const builderButton = document.getElementById("builderButton");
const builderLongButton = document.getElementById("builderLongButton");
const geminiButton = document.getElementById("geminiButton");
const saveAudioButton = document.getElementById("saveAudioButton");

// Multi textbox DOM elements
const singleTranscriptContainer = document.getElementById(
  "singleTranscriptContainer"
);
const multiTranscriptContainer = document.getElementById(
  "multiTranscriptContainer"
);
const openaiBox = document.getElementById("openaiBox");
const builderBox = document.getElementById("builderBox");
const builderLongBox = document.getElementById("builderLongBox");
const geminiBox = document.getElementById("geminiBox");
const openaiTranscript = document.getElementById("openaiTranscript");
const builderTranscript = document.getElementById("builderTranscript");
const builderLongTranscript = document.getElementById(
  "builderLongTranscript"
);
const geminiTranscript = document.getElementById("geminiTranscript");

// Checkbox elements
const saveToSheetCheckbox = document.getElementById("saveToSheetCheckbox");
const todoCheckbox = document.getElementById("todoCheckbox");
const saveToSheetCheckboxMobile = document.getElementById(
  "saveToSheetCheckboxMobile"
);
const todoCheckboxMobile = document.getElementById("todoCheckboxMobile");

// Copy buttons
const copyOpenaiBtn = document.getElementById("copyOpenaiBtn");
const copyBuilderBtn = document.getElementById("copyBuilderBtn");
const copyBuilderLongBtn = document.getElementById("copyBuilderLongBtn");
const copyGeminiBtn = document.getElementById("copyGeminiBtn");

// Sync desktop and mobile checkboxes
function syncCheckboxes(desktopCb, mobileCb) {
  if (desktopCb && mobileCb) {
    desktopCb.addEventListener("change", () => {
      mobileCb.checked = desktopCb.checked;
    });
    mobileCb.addEventListener("change", () => {
      desktopCb.checked = mobileCb.checked;
    });
  }
}
syncCheckboxes(saveToSheetCheckbox, saveToSheetCheckboxMobile);
syncCheckboxes(todoCheckbox, todoCheckboxMobile);

// Tab DOM elements
const tabRead = document.getElementById("tabRead");
const tabCorrected = document.getElementById("tabCorrected");
const tabAsked = document.getElementById("tabAsked");
const resultSource = document.getElementById("resultSource");

// Configuration
const targetSeconds = 5;
const urlParams = new URLSearchParams(window.location.search);
const autoStart = urlParams.get("start") === "1";

// Utility functions
const isMobileDevice = () =>
  /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
    navigator.userAgent
  );

async function copyToClipboard(text, button) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    showCopiedFeedback(button, "Copied!");
  } catch (err) {
    console.error("Clipboard copy failed:", err);
  }
}

function showCopiedFeedback(button, message) {
  if (!button) return;
  const originalText = button.textContent;
  button.textContent = message;
  setTimeout(() => {
    button.textContent = originalText;
  }, 2000);
}

// Toast message functions
function showError(message) {
  const errorDiv = document.getElementById("errorMessage");
  if (!errorDiv) return;
  errorDiv.textContent = message;
  errorDiv.classList.add("show");
  setTimeout(() => errorDiv.classList.remove("show"), 5000);
}

function showSuccess(message) {
  const successDiv = document.getElementById("successMessage");
  if (!successDiv) return;
  successDiv.textContent = message;
  successDiv.classList.add("show");
  setTimeout(() => successDiv.classList.remove("show"), 3000);
}

// Enable/disable batch transcribe and save audio buttons (NOT Notion button)
function setTranscriptionButtonsEnabled(enabled) {
  if (builderButton) builderButton.disabled = !enabled;
  if (builderLongButton) builderLongButton.disabled = !enabled;
  if (geminiButton) geminiButton.disabled = !enabled;
  if (saveAudioButton) saveAudioButton.disabled = !enabled;
}

// Notion button state: enabled when any transcript textarea has content (debounce 200ms)
let notionDebounceTimer = null;
function updateNotionButtonState() {
  clearTimeout(notionDebounceTimer);
  notionDebounceTimer = setTimeout(() => {
    const hasContent =
      (transcript && transcript.value.trim()) ||
      (openaiTranscript && openaiTranscript.value.trim()) ||
      (builderTranscript && builderTranscript.value.trim()) ||
      (builderLongTranscript && builderLongTranscript.value.trim()) ||
      (geminiTranscript && geminiTranscript.value.trim());
    if (confirmNotionButton && !isConfirmingNotion) {
      confirmNotionButton.disabled = !hasContent;
    }
  }, 200);
}

// Switch between single and multi textbox mode
function showSingleMode() {
  isDualMode = false;
  if (singleTranscriptContainer) singleTranscriptContainer.classList.remove("hidden");
  if (multiTranscriptContainer) multiTranscriptContainer.classList.add("hidden");
}

function showMultiMode() {
  isDualMode = true;
  if (singleTranscriptContainer) singleTranscriptContainer.classList.add("hidden");
  if (multiTranscriptContainer) multiTranscriptContainer.classList.remove("hidden");
  // Always show openai box
  if (openaiBox) openaiBox.classList.remove("hidden");
  // Copy original text from single textarea to openai box if needed
  if (
    openaiTranscript &&
    !openaiTranscript.value.trim() &&
    transcript &&
    transcript.value.trim()
  ) {
    openaiTranscript.value = transcript.value;
  }
}

function showBox(boxId) {
  const box = document.getElementById(boxId);
  if (box) box.classList.remove("hidden");
}

// Select a transcript box
function selectTranscriptBox(boxType) {
  selectedTranscriptBox = boxType;
  [openaiBox, builderBox, builderLongBox, geminiBox].forEach((box) => {
    if (box) box.classList.remove("selected");
  });
  const boxMap = {
    openai: openaiBox,
    builder: builderBox,
    builderLong: builderLongBox,
    gemini: geminiBox,
  };
  const box = boxMap[boxType];
  if (box) box.classList.add("selected");
}

// Get selected transcript content
function getSelectedTranscriptContent() {
  if (isDualMode) {
    const textareaMap = {
      openai: openaiTranscript,
      builder: builderTranscript,
      builderLong: builderLongTranscript,
      gemini: geminiTranscript,
    };
    const ta = textareaMap[selectedTranscriptBox];
    return ta ? ta.value.trim() : "";
  }
  return transcript.value.trim();
}

// Get current source label for API requests
function getCurrentSourceLabel() {
  if (isDualMode) {
    const labelMap = {
      openai: "Original",
      builder: "Builder",
      builderLong: "Builder(hr)",
      gemini: "Gemini",
    };
    return labelMap[selectedTranscriptBox] || "Original";
  }
  return "Transcript";
}

// Tab system functions
function switchToTab(tabName) {
  activeTab = tabName;

  if (tabRead) tabRead.classList.remove("active");
  if (tabCorrected) tabCorrected.classList.remove("active");
  if (tabAsked) tabAsked.classList.remove("active");

  if (tabName === "read" && tabRead) {
    tabRead.classList.add("active");
  } else if (tabName === "corrected" && tabCorrected) {
    tabCorrected.classList.add("active");
  } else if (tabName === "asked" && tabAsked) {
    tabAsked.classList.add("active");
  }

  const result = tabResults[tabName];
  if (result) {
    enhancedTranscript.value = result.content;
    resultSource.textContent = result.source ? `Source: ${result.source}` : "";
  }
}

function saveTabResult(tabName, content, source) {
  tabResults[tabName] = { content, source };

  if (tabName === "read" && tabRead) {
    tabRead.disabled = false;
  } else if (tabName === "corrected" && tabCorrected) {
    tabCorrected.disabled = false;
  } else if (tabName === "asked" && tabAsked) {
    tabAsked.disabled = false;
  }

  switchToTab(tabName);

  if (savedNotionPageId) {
    autoAppendToNotion(tabName, content);
  }
}

// Auto-append content to saved Notion page and update checkbox
async function autoAppendToNotion(tabName, content) {
  const sectionTitleMap = {
    read: "Readability",
    corrected: "Correctness",
    asked: "Ask AI",
  };

  const sectionTitle = sectionTitleMap[tabName] || tabName;

  try {
    const [appendResponse, checkboxResponse] = await Promise.all([
      fetch("/api/v1/append-notion", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          page_id: savedNotionPageId,
          section_title: sectionTitle,
          content: content,
        }),
      }),
      fetch("/api/v1/update-checkbox", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          page_id: savedNotionPageId,
          property_name: sectionTitle,
          checked: true,
        }),
      }),
    ]);

    const appendResult = await appendResponse.json();
    const checkboxResult = await checkboxResponse.json();

    if (appendResult.success && checkboxResult.success) {
      showSuccess(`${sectionTitle} appended to Notion`);
      tabAppendedToNotion[tabName] = true;
    } else {
      if (!appendResult.success) {
        console.error("Auto-append failed:", appendResult.error);
      }
      if (!checkboxResult.success) {
        console.error("Checkbox update failed:", checkboxResult.error);
      }
    }
  } catch (error) {
    console.error("Auto-append error:", error);
  }
}

// Auto-save transcript to Google Sheet
async function autoSaveToSheet() {
  let content = "";
  if (isDualMode) {
    content = openaiTranscript.value.trim();
  } else {
    content = transcript.value.trim();
  }

  if (!content) {
    console.log("No content to save to Sheet");
    return;
  }

  try {
    const requestBody = { content: content };
    const todoChecked = todoCheckbox && todoCheckbox.checked;
    if (todoChecked) {
      requestBody.category = "todo";
    }
    console.log("Saving to Sheet with category:", requestBody.category);

    const response = await fetch("/api/v1/save-to-sheet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });

    const result = await response.json();

    if (result.success) {
      showSuccess("Saved to Sheet");
      console.log("Auto-saved to Google Sheet:", result.timestamp);
    } else {
      console.error("Failed to save to Sheet:", result.error);
      showError(
        "Failed to save to Sheet: " + (result.error || "Unknown error")
      );
    }
  } catch (error) {
    console.error("Error saving to Sheet:", error);
    showError("Failed to save to Sheet: Network error");
  }
}

// Append all pending tab results to Notion (called after Save to Notion)
async function appendPendingTabResults() {
  const tabsToAppend = ["read", "corrected", "asked"];

  for (const tabName of tabsToAppend) {
    const result = tabResults[tabName];
    if (result.content && !tabAppendedToNotion[tabName]) {
      await autoAppendToNotion(tabName, result.content);
    }
  }
}

function resetTabSystem() {
  tabResults.read = { content: "", source: "" };
  tabResults.corrected = { content: "", source: "" };
  tabResults.asked = { content: "", source: "" };
  activeTab = null;

  tabAppendedToNotion.read = false;
  tabAppendedToNotion.corrected = false;
  tabAppendedToNotion.asked = false;

  if (tabRead) { tabRead.disabled = true; tabRead.classList.remove("active"); }
  if (tabCorrected) { tabCorrected.disabled = true; tabCorrected.classList.remove("active"); }
  if (tabAsked) { tabAsked.disabled = true; tabAsked.classList.remove("active"); }

  if (enhancedTranscript) enhancedTranscript.value = "";
  if (resultSource) resultSource.textContent = "";
}

// Timer functions
function startTimer() {
  clearInterval(timerInterval);
  const timerEl = document.getElementById("timer");
  if (timerEl) timerEl.textContent = "00:00";
  startTime = Date.now();
  timerInterval = setInterval(() => {
    const elapsed = Date.now() - startTime;
    const minutes = Math.floor(elapsed / 60000);
    const seconds = Math.floor((elapsed % 60000) / 1000);
    const el = document.getElementById("timer");
    if (el) el.textContent = `${minutes
      .toString()
      .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }, 1000);
}

function stopTimer() {
  clearInterval(timerInterval);
}

// Audio processing
function createAudioProcessor() {
  processor = audioContext.createScriptProcessor(4096, 1, 1);
  processor.onaudioprocess = (e) => {
    if (!isRecording) return;

    const inputData = e.inputBuffer.getChannelData(0);
    const pcmData = new Int16Array(inputData.length);

    for (let i = 0; i < inputData.length; i++) {
      pcmData[i] = Math.max(
        -32768,
        Math.min(32767, Math.floor(inputData[i] * 32767))
      );
    }

    const combinedBuffer = new Int16Array(audioBuffer.length + pcmData.length);
    combinedBuffer.set(audioBuffer);
    combinedBuffer.set(pcmData, audioBuffer.length);
    audioBuffer = combinedBuffer;

    if (audioBuffer.length >= 24000) {
      const sendBuffer = audioBuffer.slice(0, 24000);
      audioBuffer = audioBuffer.slice(24000);

      if (ws.readyState === WebSocket.OPEN) {
        ws.send(sendBuffer.buffer);
      }
    }
  };
  return processor;
}

async function initAudio(stream) {
  audioContext = new AudioContext();
  source = audioContext.createMediaStreamSource(stream);
  processor = createAudioProcessor();
  source.connect(processor);
  processor.connect(audioContext.destination);
}

// WebSocket handling
function updateConnectionStatus(status) {
  const statusDot = document.getElementById("connectionStatus");
  if (!statusDot) return;
  statusDot.classList.remove("connected", "connecting", "idle");

  switch (status) {
    case "connected":
      statusDot.classList.add("connected");
      statusDot.style.backgroundColor = "#34C759";
      break;
    case "connecting":
      statusDot.classList.add("connecting");
      statusDot.style.backgroundColor = "#FF9500";
      break;
    case "idle":
      statusDot.classList.add("idle");
      statusDot.style.backgroundColor = "#007AFF";
      break;
    default:
      statusDot.style.backgroundColor = "#FF3B30";
  }
}

function initializeWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${window.location.host}/api/v1/ws`);

  ws.onopen = () => {
    wsConnected = true;
    updateConnectionStatus("connected");
    if (autoStart && !isRecording && !isAutoStarted) startRecording();
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    switch (data.type) {
      case "session_created":
        currentSessionId = data.session_id;
        console.log("New recording session:", currentSessionId);
        break;
      case "status":
        updateConnectionStatus(data.status);
        if (data.status === "idle") {
          copyToClipboard(transcript.value, copyButton);
        }
        break;
      case "text":
        // Always single mode during recording — text goes to main transcript
        if (data.isNewResponse) {
          transcript.value = data.content;
          stopTimer();
        } else {
          transcript.value += data.content;
        }
        transcript.scrollTop = transcript.scrollHeight;
        updateNotionButtonState();
        break;
      case "audio_saved":
        // Audio file saved — enable batch transcribe & save audio buttons
        setTranscriptionButtonsEnabled(true);
        console.log("Audio saved, session:", data.session_id);
        break;
      case "transcript_converted":
        console.log("Transcript converted to Traditional Chinese");
        transcript.value = data.content;
        showSuccess("已轉換為繁體中文");
        updateNotionButtonState();
        break;
      case "transcription_complete":
        // Also enable buttons as fallback (audio_saved fires earlier)
        setTranscriptionButtonsEnabled(true);
        console.log("Transcription complete, session:", data.session_id);

        isSaveToSheetEnabled =
          (saveToSheetCheckbox && saveToSheetCheckbox.checked) ||
          (saveToSheetCheckboxMobile && saveToSheetCheckboxMobile.checked);
        isTodoEnabled =
          (todoCheckbox && todoCheckbox.checked) ||
          (todoCheckboxMobile && todoCheckboxMobile.checked);

        if (isSaveToSheetEnabled) {
          autoSaveToSheet();
        }
        updateNotionButtonState();
        break;
      case "error":
        showError(data.content);
        updateConnectionStatus("idle");
        break;
    }
  };

  ws.onclose = () => {
    wsConnected = false;
    updateConnectionStatus("idle");
    setTimeout(initializeWebSocket, 1000);
  };
}

// Recording control
async function startRecording() {
  if (isRecording) return;

  try {
    isSaveToSheetEnabled = saveToSheetCheckbox && saveToSheetCheckbox.checked;
    isTodoEnabled = todoCheckbox && todoCheckbox.checked;

    if (transcript) transcript.value = "";
    if (enhancedTranscript) enhancedTranscript.value = "";
    resetTabSystem();

    // Always single mode during recording
    showSingleMode();

    // Hide all batch result boxes and clear their content
    if (builderBox) builderBox.classList.add("hidden");
    if (builderLongBox) builderLongBox.classList.add("hidden");
    if (geminiBox) geminiBox.classList.add("hidden");
    if (builderTranscript) builderTranscript.value = "";
    if (builderLongTranscript) builderLongTranscript.value = "";
    if (geminiTranscript) geminiTranscript.value = "";
    if (openaiTranscript) openaiTranscript.value = "";

    // Disable batch transcribe buttons for new recording (not Notion — it's always input-driven)
    setTranscriptionButtonsEnabled(false);
    updateNotionButtonState();

    if (!navigator.mediaDevices) {
      throw new Error("Microphone requires HTTPS connection");
    }

    if (!streamInitialized) {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamInitialized = true;
    }

    if (!stream) throw new Error("Failed to initialize audio stream");
    if (!audioContext) await initAudio(stream);

    isRecording = true;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "start_recording" }));
    }

    startTimer();
    if (recordButton) {
      recordButton.textContent = "Stop";
      recordButton.classList.add("recording");
    }
  } catch (error) {
    console.error("Error starting recording:", error);
    showError("Cannot access microphone: " + error.message);
  }
}

async function stopRecording() {
  if (!isRecording) return;

  isRecording = false;
  stopTimer();

  try {
    if (audioBuffer.length > 0 && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(audioBuffer.buffer);
      audioBuffer = new Int16Array(0);
    }

    await new Promise((resolve) => setTimeout(resolve, 500));

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop_recording" }));
    } else {
      console.error("WebSocket not open when trying to send stop_recording, state:", ws?.readyState);
      showError("Connection lost during recording. Audio may be saved on server — try Batch Transcribe.");
      // Still enable buttons since audio might have been saved
      setTranscriptionButtonsEnabled(true);
    }
  } catch (e) {
    console.error("Error in stopRecording:", e);
    showError("Error stopping recording: " + e.message);
    setTranscriptionButtonsEnabled(true);
  }

  if (recordButton) {
    recordButton.textContent = "Start";
    recordButton.classList.remove("recording");
  }
}

// Event listeners
if (recordButton) recordButton.onclick = () => (isRecording ? stopRecording() : startRecording());
if (copyButton) copyButton.onclick = () => copyToClipboard(transcript.value, copyButton);
if (copyEnhancedButton) copyEnhancedButton.onclick = () =>
  copyToClipboard(enhancedTranscript.value, copyEnhancedButton);

// Copy buttons for multi textbox
if (copyOpenaiBtn) {
  copyOpenaiBtn.onclick = () =>
    copyToClipboard(openaiTranscript.value, copyOpenaiBtn);
}
if (copyBuilderBtn) {
  copyBuilderBtn.onclick = () =>
    copyToClipboard(builderTranscript.value, copyBuilderBtn);
}
if (copyBuilderLongBtn) {
  copyBuilderLongBtn.onclick = () =>
    copyToClipboard(builderLongTranscript.value, copyBuilderLongBtn);
}
if (copyGeminiBtn) {
  copyGeminiBtn.onclick = () =>
    copyToClipboard(geminiTranscript.value, copyGeminiBtn);
}

// Builder transcribe button handler
if (builderButton) {
  builderButton.onclick = async () => {
    if (isBuilderTranscribing || !currentSessionId) return;

    try {
      isBuilderTranscribing = true;
      builderButton.textContent = "Transcribing...";
      builderButton.disabled = true;
      startTimer();

      showMultiMode();
      showBox("builderBox");
      builderTranscript.value = "Transcribing with Builder...";

      const response = await fetch("/api/v1/transcribe-builder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: currentSessionId }),
      });

      const result = await response.json();

      if (result.success) {
        builderTranscript.value = result.text;
        selectTranscriptBox("builder");
        showSuccess("Builder transcription complete");
        updateNotionButtonState();
      } else {
        builderTranscript.value = "";
        showError(result.error || "Builder transcription failed");
      }
    } catch (error) {
      console.error("Error:", error);
      builderTranscript.value = "";
      showError("Network error, please check connection");
    } finally {
      isBuilderTranscribing = false;
      builderButton.textContent = "Builder";
      builderButton.disabled = false;
      stopTimer();
    }
  };
}

// Builder(hr) long transcribe button handler
if (builderLongButton) {
  builderLongButton.onclick = async () => {
    if (isBuilderLongTranscribing || !currentSessionId) return;

    try {
      isBuilderLongTranscribing = true;
      builderLongButton.textContent = "Transcribing...";
      builderLongButton.disabled = true;
      startTimer();

      showMultiMode();
      showBox("builderLongBox");
      builderLongTranscript.value = "Transcribing with Builder(hr)...";

      const response = await fetch("/api/v1/transcribe-builder-long", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: currentSessionId }),
      });

      const result = await response.json();

      if (result.success) {
        builderLongTranscript.value = result.text;
        selectTranscriptBox("builderLong");
        showSuccess("Builder(hr) transcription complete");
        updateNotionButtonState();
      } else {
        builderLongTranscript.value = "";
        showError(result.error || "Builder(hr) transcription failed");
      }
    } catch (error) {
      console.error("Error:", error);
      builderLongTranscript.value = "";
      showError("Network error, please check connection");
    } finally {
      isBuilderLongTranscribing = false;
      builderLongButton.textContent = "Builder(hr)";
      builderLongButton.disabled = false;
      stopTimer();
    }
  };
}

// Gemini transcribe button handler
if (geminiButton) {
  geminiButton.onclick = async () => {
    if (isGeminiTranscribing || !currentSessionId) return;

    try {
      isGeminiTranscribing = true;
      geminiButton.textContent = "Transcribing...";
      geminiButton.disabled = true;
      startTimer();

      showMultiMode();
      showBox("geminiBox");
      geminiTranscript.value = "Transcribing with Gemini...";

      const response = await fetch("/api/v1/retranscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: currentSessionId }),
      });

      const result = await response.json();

      if (result.success) {
        geminiTranscript.value = result.text;
        selectTranscriptBox("gemini");
        showSuccess("Gemini transcription complete");
        updateNotionButtonState();
      } else {
        geminiTranscript.value = "";
        showError(result.error || "Gemini transcription failed");
      }
    } catch (error) {
      console.error("Error:", error);
      geminiTranscript.value = "";
      showError("Network error, please check connection");
    } finally {
      isGeminiTranscribing = false;
      geminiButton.textContent = "Gemini";
      geminiButton.disabled = false;
      stopTimer();
    }
  };
}

// Save Audio button handler (browser download)
if (saveAudioButton) {
  saveAudioButton.onclick = () => {
    if (!currentSessionId) {
      showError("No audio to save");
      return;
    }

    const a = document.createElement("a");
    a.href = `/api/v1/download-audio/${currentSessionId}`;
    a.download = `${currentSessionId}.wav`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showSuccess("Audio download started");
  };
}

// Confirm Notion button handler (supports re-save)
if (confirmNotionButton) confirmNotionButton.onclick = async () => {
  if (isConfirmingNotion) return;

  const inputText = getSelectedTranscriptContent();
  if (!inputText) {
    showError("No content to save");
    return;
  }

  try {
    isConfirmingNotion = true;
    confirmNotionButton.textContent = "Saving...";
    confirmNotionButton.disabled = true;
    startTimer();

    const response = await fetch("/api/v1/confirm-notion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript: inputText,
        session_id: currentSessionId,
        missions: selectedMissions.length ? selectedMissions : null,
      }),
    });

    const result = await response.json();

    if (!result.success) {
      showError(result.error || "Failed to save to Notion");
      isConfirmingNotion = false;
      confirmNotionButton.textContent = "Save to Notion";
      updateNotionButtonState();
      return;
    }

    if (result.page_id) {
      savedNotionPageId = result.page_id;
      console.log("Saved Notion page ID:", savedNotionPageId);
      await appendPendingTabResults();
    }

    showSuccess("Saved ✓");
    confirmNotionButton.textContent = "Saved ✓";
    // Re-enable after 2 seconds (input listener determines final state)
    setTimeout(() => {
      confirmNotionButton.textContent = "Save to Notion";
      isConfirmingNotion = false;
      updateNotionButtonState();
    }, 2000);
    // Do NOT clear currentSessionId — allow re-save and audio download
  } catch (error) {
    console.error("Error:", error);
    showError("Network error, please check connection");
    isConfirmingNotion = false;
    confirmNotionButton.textContent = "Save to Notion";
    updateNotionButtonState();
  } finally {
    stopTimer();
  }
};

// Handle spacebar toggle
document.addEventListener("keydown", (event) => {
  if (event.code === "Space") {
    const activeElement = document.activeElement;
    if (
      !activeElement.tagName.match(/INPUT|TEXTAREA/) &&
      !activeElement.isContentEditable
    ) {
      event.preventDefault();
      if (recordButton) recordButton.click();
    }
  }
});

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initializeWebSocket();
  initializeTheme();
  // autoStart handled by ws.onopen → startRecording()

  // Click listeners for multi textbox selection
  const boxConfigs = [
    { box: openaiBox, textarea: openaiTranscript, type: "openai" },
    { box: builderBox, textarea: builderTranscript, type: "builder" },
    {
      box: builderLongBox,
      textarea: builderLongTranscript,
      type: "builderLong",
    },
    { box: geminiBox, textarea: geminiTranscript, type: "gemini" },
  ];
  boxConfigs.forEach(({ box, textarea, type }) => {
    if (box) {
      box.addEventListener("click", () => selectTranscriptBox(type));
    }
    if (textarea) {
      textarea.addEventListener("focus", () => selectTranscriptBox(type));
    }
  });

  // Input listeners for Notion button state (any textarea with content → enable)
  const allTranscriptTextareas = [
    transcript,
    openaiTranscript,
    builderTranscript,
    builderLongTranscript,
    geminiTranscript,
  ];
  allTranscriptTextareas.forEach((ta) => {
    if (ta) {
      ta.addEventListener("input", updateNotionButtonState);
    }
  });

  // Tab click listeners
  if (tabRead) {
    tabRead.addEventListener("click", () => switchToTab("read"));
  }
  if (tabCorrected) {
    tabCorrected.addEventListener("click", () => switchToTab("corrected"));
  }
  if (tabAsked) {
    tabAsked.addEventListener("click", () => switchToTab("asked"));
  }

  // Initial Notion button state check (enable if textbox already has content)
  updateNotionButtonState();
});

// Readability and AI handlers
if (readabilityButton) readabilityButton.onclick = async () => {
  startTimer();
  const inputText = getSelectedTranscriptContent();
  const sourceLabel = getCurrentSourceLabel();
  if (!inputText) {
    showError("Please enter text to enhance readability.");
    stopTimer();
    return;
  }

  try {
    const response = await fetch("/api/v1/readability", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: inputText }),
    });

    if (!response.ok) throw new Error("Readability enhancement failed");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullText = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      fullText += decoder.decode(value, { stream: true });
      enhancedTranscript.value = fullText;
      enhancedTranscript.scrollTop = enhancedTranscript.scrollHeight;
    }

    saveTabResult("read", fullText, sourceLabel);

    if (!isMobileDevice()) copyToClipboard(fullText, copyEnhancedButton);
    stopTimer();
  } catch (error) {
    console.error("Error:", error);
    showError("Error enhancing readability");
    stopTimer();
  }
};

if (askAIButton) askAIButton.onclick = async () => {
  startTimer();
  const inputText = getSelectedTranscriptContent();
  const sourceLabel = getCurrentSourceLabel();
  if (!inputText) {
    showError("Please enter text to ask AI about.");
    stopTimer();
    return;
  }

  try {
    const response = await fetch("/api/v1/ask_ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: inputText }),
    });

    if (!response.ok) throw new Error("AI request failed");

    const result = await response.json();
    enhancedTranscript.value = result.answer;

    saveTabResult("asked", result.answer, sourceLabel);

    if (!isMobileDevice()) copyToClipboard(result.answer, copyEnhancedButton);
    stopTimer();
  } catch (error) {
    console.error("Error:", error);
    showError("Error asking AI");
    stopTimer();
  }
};

if (correctnessButton) correctnessButton.onclick = async () => {
  startTimer();
  const inputText = getSelectedTranscriptContent();
  const sourceLabel = getCurrentSourceLabel();
  if (!inputText) {
    showError("Please enter text to check for correctness.");
    stopTimer();
    return;
  }

  try {
    const response = await fetch("/api/v1/correctness", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: inputText }),
    });

    if (!response.ok) throw new Error("Correctness check failed");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullText = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      fullText += decoder.decode(value, { stream: true });
      enhancedTranscript.value = fullText;
      enhancedTranscript.scrollTop = enhancedTranscript.scrollHeight;
    }

    saveTabResult("corrected", fullText, sourceLabel);

    stopTimer();
  } catch (error) {
    console.error("Error:", error);
    showError("Error checking correctness");
    stopTimer();
  }
};

// Theme handling
function toggleTheme() {
  const body = document.body;
  const themeToggle = document.getElementById("themeToggle");
  const isDarkTheme = body.classList.toggle("dark-theme");

  if (themeToggle) themeToggle.textContent = isDarkTheme ? "☀️" : "🌙";
  localStorage.setItem("darkTheme", isDarkTheme);
}

function initializeTheme() {
  const darkTheme = localStorage.getItem("darkTheme") === "true";
  const themeToggle = document.getElementById("themeToggle");

  if (darkTheme) {
    document.body.classList.add("dark-theme");
    if (themeToggle) themeToggle.textContent = "☀️";
  }
}

const themeToggleBtn = document.getElementById("themeToggle");
if (themeToggleBtn) themeToggleBtn.onclick = toggleTheme;

// --- Recent Notes Dropdown & Modal ---
const recentNotesToggle = document.getElementById("recentNotesToggle");
const recentNotesDropdown = document.getElementById("recentNotesDropdown");
const recentNotesList = document.getElementById("recentNotesList");
const noteModal = document.getElementById("noteModal");
const noteModalBackdrop = document.getElementById("noteModalBackdrop");
const noteModalClose = document.getElementById("noteModalClose");
const noteModalTitle = document.getElementById("noteModalTitle");
const noteModalBody = document.getElementById("noteModalBody");
const noteModalLink = document.getElementById("noteModalLink");

let recentNotesCache = null;

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function openNoteModal(note) {
  if (!noteModal) return;
  noteModalTitle.textContent = note.title || "Untitled";
  noteModalBody.textContent = note.content || "";
  noteModalLink.href = note.url || "#";
  noteModal.classList.remove("hidden");
}

function closeNoteModal() {
  if (noteModal) noteModal.classList.add("hidden");
}

function closeRecentNotesDropdown() {
  if (recentNotesDropdown) recentNotesDropdown.classList.add("hidden");
}

async function loadAndRenderRecentNotes() {
  if (recentNotesCache) {
    renderRecentNotes(recentNotesCache);
    return;
  }

  recentNotesList.innerHTML =
    '<div class="text-center py-5 text-gray-400 text-sm">Loading...</div>';

  try {
    const response = await fetch("/api/v1/recent-notes");
    const result = await response.json();

    if (result.success && result.notes) {
      recentNotesCache = result.notes;
      renderRecentNotes(result.notes);
    } else {
      recentNotesList.innerHTML =
        '<div class="text-center py-5 text-gray-400 text-sm">Failed to load notes</div>';
    }
  } catch (err) {
    console.error("Error loading recent notes:", err);
    recentNotesList.innerHTML =
      '<div class="text-center py-5 text-gray-400 text-sm">Network error</div>';
  }
}

function renderRecentNotes(notes) {
  if (!notes.length) {
    recentNotesList.innerHTML =
      '<div class="text-center py-5 text-gray-400 text-sm">No notes found</div>';
    return;
  }

  recentNotesList.innerHTML = notes
    .map(
      (note, i) =>
        `<div class="p-3 rounded-lg cursor-pointer hover:bg-gray-100 dark:hover:bg-zinc-700 border-b border-gray-100 dark:border-zinc-700 last:border-b-0" data-index="${i}">
          <div class="font-semibold text-sm text-gray-900 dark:text-gray-100 truncate">${escapeHtml(note.title || "Untitled")}</div>
          <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-3">${escapeHtml(note.content || "")}</div>
        </div>`
    )
    .join("");

  recentNotesList.querySelectorAll("[data-index]").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.index, 10);
      closeRecentNotesDropdown();
      openNoteModal(notes[idx]);
    });
  });
}

if (recentNotesToggle) {
  recentNotesToggle.addEventListener("click", (e) => {
    e.stopPropagation();
    const isHidden = recentNotesDropdown.classList.contains("hidden");
    if (isHidden) {
      recentNotesDropdown.classList.remove("hidden");
      loadAndRenderRecentNotes();
    } else {
      closeRecentNotesDropdown();
    }
  });
}

// Close dropdown on outside click
document.addEventListener("click", (e) => {
  if (
    recentNotesDropdown &&
    !recentNotesDropdown.classList.contains("hidden") &&
    !recentNotesDropdown.contains(e.target) &&
    e.target !== recentNotesToggle
  ) {
    closeRecentNotesDropdown();
  }
});

// Modal close handlers
if (noteModalClose) noteModalClose.addEventListener("click", closeNoteModal);
if (noteModalBackdrop) noteModalBackdrop.addEventListener("click", closeNoteModal);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (noteModal && !noteModal.classList.contains("hidden")) {
      closeNoteModal();
    } else if (
      recentNotesDropdown &&
      !recentNotesDropdown.classList.contains("hidden")
    ) {
      closeRecentNotesDropdown();
    } else if (
      missionDropdown &&
      !missionDropdown.classList.contains("hidden")
    ) {
      closeMissionDropdown();
    }
  }
});

// --- Mission Dropdown (searchable, MRU on top via localStorage) ---
const missionToggle = document.getElementById("missionToggle");
const missionDropdown = document.getElementById("missionDropdown");
const missionLabel = document.getElementById("missionLabel");
const missionSearch = document.getElementById("missionSearch");
const missionList = document.getElementById("missionList");

const MISSION_MRU_KEY = "missionMru";
const MISSION_MRU_MAX = 20;
let missionOptionsCache = null;
let selectedMissions = [];
let missionSyncTimer = null;

function loadMissionMru() {
  try {
    const raw = localStorage.getItem(MISSION_MRU_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function pushMissionMru(name) {
  if (!name) return;
  const existing = loadMissionMru().filter((n) => n !== name);
  existing.unshift(name);
  const trimmed = existing.slice(0, MISSION_MRU_MAX);
  try {
    localStorage.setItem(MISSION_MRU_KEY, JSON.stringify(trimmed));
  } catch {}
}

function sortByMru(options) {
  const mru = loadMissionMru();
  const rank = new Map(mru.map((name, idx) => [name, idx]));
  const ranked = [];
  const rest = [];
  for (const opt of options) {
    if (rank.has(opt.name)) ranked.push(opt);
    else rest.push(opt);
  }
  ranked.sort((a, b) => rank.get(a.name) - rank.get(b.name));
  return [...ranked, ...rest];
}

async function loadMissionOptions() {
  if (missionOptionsCache) return missionOptionsCache;
  try {
    const res = await fetch("/api/v1/mission-options");
    const data = await res.json();
    missionOptionsCache = data.success && Array.isArray(data.options) ? data.options : [];
  } catch (err) {
    console.error("Error loading mission options:", err);
    missionOptionsCache = [];
  }
  return missionOptionsCache;
}

function renderMissionList(query = "") {
  if (!missionList) return;
  const options = missionOptionsCache || [];
  const q = query.trim().toLowerCase();
  const filtered = q
    ? options.filter((o) => o.name.toLowerCase().includes(q))
    : options;
  const ordered = sortByMru(filtered);

  const mruSet = new Set(loadMissionMru());
  const selectedSet = new Set(selectedMissions);
  const items = [
    `<div class="px-3 py-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-zinc-700 text-gray-500 italic" data-action="clear">— Clear all —</div>`,
    ...ordered.map(
      (o) =>
        `<div class="px-3 py-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-zinc-700 flex items-center justify-between gap-2 ${
          selectedSet.has(o.name) ? "bg-blue-50 dark:bg-zinc-700" : ""
        }" data-mission="${escapeHtml(o.name)}">
          <span class="flex items-center gap-2 min-w-0">
            <span class="inline-block w-4 text-blue-500">${selectedSet.has(o.name) ? "✓" : ""}</span>
            <span class="truncate">${escapeHtml(o.name)}</span>
          </span>
          ${mruSet.has(o.name) ? '<span class="text-[10px] text-blue-500">recent</span>' : ""}
        </div>`
    ),
  ];

  if (!ordered.length && q) {
    items.push('<div class="px-3 py-2 text-gray-400">No match</div>');
  }

  missionList.innerHTML = items.join("");
  missionList.querySelectorAll("[data-mission], [data-action]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      if (el.dataset.action === "clear") {
        clearMissions();
        renderMissionList(missionSearch ? missionSearch.value : "");
        return;
      }
      const name = el.getAttribute("data-mission");
      toggleMission(name);
      renderMissionList(missionSearch ? missionSearch.value : "");
    });
  });
}

function openMissionDropdown() {
  if (!missionDropdown) return;
  missionDropdown.classList.remove("hidden");
  if (missionSearch) {
    missionSearch.value = "";
    setTimeout(() => missionSearch.focus(), 0);
  }
  renderMissionList("");
}

function closeMissionDropdown() {
  if (missionDropdown) missionDropdown.classList.add("hidden");
}

function updateMissionLabel() {
  if (!missionLabel) return;
  if (!selectedMissions.length) {
    missionLabel.textContent = "Missions: —";
  } else if (selectedMissions.length <= 2) {
    missionLabel.textContent = `Missions: ${selectedMissions.join(", ")}`;
  } else {
    missionLabel.textContent = `Missions: ${selectedMissions[0]} +${selectedMissions.length - 1}`;
  }
}

function scheduleMissionSync() {
  if (!savedNotionPageId) return;
  clearTimeout(missionSyncTimer);
  missionSyncTimer = setTimeout(syncMissionsToNotion, 400);
}

async function syncMissionsToNotion() {
  if (!savedNotionPageId) return;
  try {
    const res = await fetch("/api/v1/update-mission", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: savedNotionPageId,
        missions: selectedMissions.length ? selectedMissions : null,
      }),
    });
    const data = await res.json();
    if (data.success) {
      showSuccess(
        selectedMissions.length
          ? `Missions saved (${selectedMissions.length})`
          : "Missions cleared"
      );
    } else {
      showError(data.error || "Failed to update Missions");
    }
  } catch (err) {
    console.error("update-mission error:", err);
    showError("Network error updating Missions");
  }
}

function toggleMission(name) {
  if (!name) return;
  const idx = selectedMissions.indexOf(name);
  if (idx >= 0) {
    selectedMissions.splice(idx, 1);
  } else {
    selectedMissions.push(name);
    pushMissionMru(name);
  }
  updateMissionLabel();
  scheduleMissionSync();
}

function clearMissions() {
  if (!selectedMissions.length) return;
  selectedMissions = [];
  updateMissionLabel();
  scheduleMissionSync();
}

if (missionToggle) {
  missionToggle.addEventListener("click", async (e) => {
    e.stopPropagation();
    const isHidden = missionDropdown.classList.contains("hidden");
    if (isHidden) {
      await loadMissionOptions();
      openMissionDropdown();
    } else {
      closeMissionDropdown();
    }
  });
}

if (missionSearch) {
  missionSearch.addEventListener("input", (e) => renderMissionList(e.target.value));
  missionSearch.addEventListener("click", (e) => e.stopPropagation());
}

document.addEventListener("click", (e) => {
  if (
    missionDropdown &&
    !missionDropdown.classList.contains("hidden") &&
    !missionDropdown.contains(e.target) &&
    e.target !== missionToggle &&
    !missionToggle.contains(e.target)
  ) {
    closeMissionDropdown();
  }
});

updateMissionLabel();
