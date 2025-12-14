// Global state
let ws, audioContext, processor, source, stream;
let isRecording = false;
let timerInterval;
let startTime;
let audioBuffer = new Int16Array(0);
let wsConnected = false;
let streamInitialized = false;
let isAutoStarted = false;

// Session tracking for re-transcription
let currentSessionId = null;
let isRetranscribing = false;
let isConfirmingNotion = false;

// Dual textbox state
let isDualMode = false;
let selectedTranscriptBox = "openai"; // 'openai' or 'gemini'
let isDualChannelMode = true; // Whether dual channel mode is enabled via checkbox (default: true)
let isSaveToSheetEnabled = true; // Whether save to sheet is enabled via checkbox (default: true)
let isTodoEnabled = true; // Whether todo category is enabled via checkbox (default: true)

// Tab system state
const tabResults = {
  read: { content: "", source: "" },
  corrected: { content: "", source: "" },
  asked: { content: "", source: "" },
};
let activeTab = null;
let savedNotionPageId = null; // Remember saved Notion page ID for appending

// Track which tab results have been appended to Notion
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
const retranscribeButton = document.getElementById("retranscribeButton");
const confirmNotionButton = document.getElementById("confirmNotionButton");

// Dual textbox DOM elements
const singleTranscriptContainer = document.getElementById(
  "singleTranscriptContainer"
);
const dualTranscriptContainer = document.getElementById(
  "dualTranscriptContainer"
);
const openaiBox = document.getElementById("openaiBox");
const geminiBox = document.getElementById("geminiBox");
const openaiTranscript = document.getElementById("openaiTranscript");
const geminiTranscript = document.getElementById("geminiTranscript");
const leftBoxLabel = document.getElementById("leftBoxLabel");
const rightBoxLabel = document.getElementById("rightBoxLabel");
const dualChannelCheckbox = document.getElementById("dualChannelCheckbox");
const saveToSheetCheckbox = document.getElementById("saveToSheetCheckbox");
const todoCheckbox = document.getElementById("todoCheckbox");
const copyOpenaiBtn = document.getElementById("copyOpenaiBtn");
const copyGeminiBtn = document.getElementById("copyGeminiBtn");

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
    // alert('Clipboard copy failed: ' + err.message);
    // We don't show this message because it's not accurate. We could still write to the clipboard in this case.
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

// Enable/disable transcription action buttons
function setTranscriptionButtonsEnabled(enabled) {
  if (retranscribeButton) retranscribeButton.disabled = !enabled;
  if (confirmNotionButton) confirmNotionButton.disabled = !enabled;
}

// Switch between single and dual textbox mode
function showSingleMode() {
  isDualMode = false;
  singleTranscriptContainer.classList.remove("hidden");
  dualTranscriptContainer.classList.add("hidden");
}

function showDualMode(leftText, rightText, isDualChannel = false) {
  isDualMode = true;
  openaiTranscript.value = leftText;
  geminiTranscript.value = rightText;
  singleTranscriptContainer.classList.add("hidden");
  dualTranscriptContainer.classList.remove("hidden");

  // Update labels based on mode
  if (isDualChannel) {
    leftBoxLabel.textContent = "OpenAI";
    rightBoxLabel.textContent = "Gemini";
  } else {
    leftBoxLabel.textContent = "Original";
    rightBoxLabel.textContent = "Re-transcribed";
  }

  // Default select openai/left box
  selectTranscriptBox("openai");
}

// Select a transcript box
function selectTranscriptBox(boxType) {
  selectedTranscriptBox = boxType;
  openaiBox.classList.remove("selected");
  geminiBox.classList.remove("selected");

  if (boxType === "openai") {
    openaiBox.classList.add("selected");
  } else {
    geminiBox.classList.add("selected");
  }
}

// Get selected transcript content
function getSelectedTranscriptContent() {
  if (isDualMode) {
    return selectedTranscriptBox === "openai"
      ? openaiTranscript.value.trim()
      : geminiTranscript.value.trim();
  }
  return transcript.value.trim();
}

// Get current source label for API requests
function getCurrentSourceLabel() {
  if (isDualMode) {
    if (isDualChannelMode) {
      return selectedTranscriptBox === "openai" ? "OpenAI" : "Gemini";
    } else {
      return selectedTranscriptBox === "openai" ? "Original" : "Re-transcribed";
    }
  }
  return "Transcript";
}

// Tab system functions
function switchToTab(tabName) {
  activeTab = tabName;

  // Update tab button states
  tabRead.classList.remove("active");
  tabCorrected.classList.remove("active");
  tabAsked.classList.remove("active");

  if (tabName === "read") {
    tabRead.classList.add("active");
  } else if (tabName === "corrected") {
    tabCorrected.classList.add("active");
  } else if (tabName === "asked") {
    tabAsked.classList.add("active");
  }

  // Update content and source
  const result = tabResults[tabName];
  if (result) {
    enhancedTranscript.value = result.content;
    resultSource.textContent = result.source ? `Source: ${result.source}` : "";
  }
}

function saveTabResult(tabName, content, source) {
  tabResults[tabName] = { content, source };

  // Enable the tab button
  if (tabName === "read") {
    tabRead.disabled = false;
  } else if (tabName === "corrected") {
    tabCorrected.disabled = false;
  } else if (tabName === "asked") {
    tabAsked.disabled = false;
  }

  // Switch to this tab
  switchToTab(tabName);

  // Auto-append to Notion if page exists
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
    // Append content and update checkbox in parallel
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
      // Mark as appended
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
  // Get content from the appropriate textbox
  let content = "";
  if (isDualMode) {
    // In dual mode, use OpenAI (left) transcript
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
    // Read checkbox state directly to ensure we get the current value
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
    // If has content and not yet appended
    if (result.content && !tabAppendedToNotion[tabName]) {
      await autoAppendToNotion(tabName, result.content);
    }
  }
}

function resetTabSystem() {
  // Reset all tab results
  tabResults.read = { content: "", source: "" };
  tabResults.corrected = { content: "", source: "" };
  tabResults.asked = { content: "", source: "" };
  activeTab = null;

  // Reset append tracking
  tabAppendedToNotion.read = false;
  tabAppendedToNotion.corrected = false;
  tabAppendedToNotion.asked = false;

  // Disable all tabs
  tabRead.disabled = true;
  tabCorrected.disabled = true;
  tabAsked.disabled = true;
  tabRead.classList.remove("active");
  tabCorrected.classList.remove("active");
  tabAsked.classList.remove("active");

  // Clear content
  enhancedTranscript.value = "";
  resultSource.textContent = "";
}

// Timer functions
function startTimer() {
  clearInterval(timerInterval);
  document.getElementById("timer").textContent = "00:00";
  startTime = Date.now();
  timerInterval = setInterval(() => {
    const elapsed = Date.now() - startTime;
    const minutes = Math.floor(elapsed / 60000);
    const seconds = Math.floor((elapsed % 60000) / 1000);
    document.getElementById("timer").textContent = `${minutes
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
  statusDot.classList.remove("connected", "connecting", "idle");

  switch (status) {
    case "connected": // OpenAI is connected and ready
      statusDot.classList.add("connected");
      statusDot.style.backgroundColor = "#34C759"; // Green
      break;
    case "connecting": // Establishing OpenAI connection
      statusDot.classList.add("connecting");
      statusDot.style.backgroundColor = "#FF9500"; // Orange
      break;
    case "idle": // Client connected, OpenAI not connected
      statusDot.classList.add("idle");
      statusDot.style.backgroundColor = "#007AFF"; // Blue
      break;
    default: // Disconnected
      statusDot.style.backgroundColor = "#FF3B30"; // Red
  }
}

function initializeWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${window.location.host}/api/v1/ws`);

  ws.onopen = () => {
    wsConnected = true;
    updateConnectionStatus(true);
    if (autoStart && !isRecording && !isAutoStarted) startRecording();
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    switch (data.type) {
      case "session_created":
        currentSessionId = data.session_id;
        console.log("New recording session:", currentSessionId);
        // Buttons will be enabled when transcription is complete
        break;
      case "status":
        updateConnectionStatus(data.status);
        if (data.status === "idle" && !isDualChannelMode) {
          copyToClipboard(transcript.value, copyButton);
        }
        break;
      case "text":
        if (isDualChannelMode && isDualMode) {
          // Dual channel mode: OpenAI results go to left textbox
          if (data.isNewResponse) {
            openaiTranscript.value = data.content;
            stopTimer();
          } else {
            openaiTranscript.value += data.content;
          }
          openaiTranscript.scrollTop = openaiTranscript.scrollHeight;
        } else {
          // Single channel mode: results go to main transcript
          if (data.isNewResponse) {
            transcript.value = data.content;
            stopTimer();
          } else {
            transcript.value += data.content;
          }
          transcript.scrollTop = transcript.scrollHeight;
        }
        break;
      case "gemini_transcription":
        // Gemini results go to right textbox (dual channel mode)
        if (isDualMode) {
          geminiTranscript.value = data.text;
          geminiTranscript.scrollTop = geminiTranscript.scrollHeight;
          if (data.was_converted) {
            showSuccess("Gemini 轉寫完成（已轉換為繁體中文）");
          } else {
            showSuccess("Gemini transcription complete");
          }
        }
        break;
      case "gemini_transcribing":
        // Show loading state for Gemini
        if (isDualMode) {
          geminiTranscript.value = "Transcribing with Gemini...";
        }
        break;
      case "transcript_converted":
        // Handle Traditional Chinese conversion
        console.log("Transcript converted to Traditional Chinese");
        if (isDualChannelMode && isDualMode) {
          // In dual mode, update OpenAI (left) textbox
          openaiTranscript.value = data.content;
        } else {
          // In single mode, update main transcript
          transcript.value = data.content;
        }
        showSuccess("已轉換為繁體中文");
        break;
      case "transcription_complete":
        // Enable action buttons when transcription is complete
        setTranscriptionButtonsEnabled(true);
        console.log("Transcription complete, session:", data.session_id);

        // Auto-save to Google Sheet if enabled
        if (isSaveToSheetEnabled) {
          autoSaveToSheet();
        }
        break;
      case "error":
        showError(data.content);
        updateConnectionStatus("idle");
        break;
    }
  };

  ws.onclose = () => {
    wsConnected = false;
    updateConnectionStatus(false);
    setTimeout(initializeWebSocket, 1000);
  };
}

// Recording control
async function startRecording() {
  if (isRecording) return;

  try {
    // Check if dual channel mode is enabled
    isDualChannelMode = dualChannelCheckbox && dualChannelCheckbox.checked;
    // Check if save to sheet is enabled
    isSaveToSheetEnabled = saveToSheetCheckbox && saveToSheetCheckbox.checked;
    // Check if todo category is enabled
    isTodoEnabled = todoCheckbox && todoCheckbox.checked;

    transcript.value = "";
    enhancedTranscript.value = "";

    // Reset tab system but keep savedNotionPageId for appending
    resetTabSystem();
    // Note: savedNotionPageId is preserved to allow appending to the same page

    // Set up UI based on mode
    if (isDualChannelMode) {
      // Dual channel mode: show dual textbox immediately
      showDualMode("", "", true);
    } else {
      // Single channel mode: show single textbox
      showSingleMode();
    }

    // Disable transcription action buttons for new recording
    setTranscriptionButtonsEnabled(false);

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
    // Send start_recording with dual_channel flag
    await ws.send(
      JSON.stringify({
        type: "start_recording",
        dual_channel: isDualChannelMode,
      })
    );

    startTimer();
    recordButton.textContent = "Stop";
    recordButton.classList.add("recording");
  } catch (error) {
    console.error("Error starting recording:", error);
    showError("Cannot access microphone: " + error.message);
  }
}

async function stopRecording() {
  if (!isRecording) return;

  isRecording = false;
  startTimer();

  if (audioBuffer.length > 0 && ws.readyState === WebSocket.OPEN) {
    ws.send(audioBuffer.buffer);
    audioBuffer = new Int16Array(0);
  }

  await new Promise((resolve) => setTimeout(resolve, 500));
  await ws.send(JSON.stringify({ type: "stop_recording" }));

  recordButton.textContent = "Start";
  recordButton.classList.remove("recording");
}

// Event listeners
recordButton.onclick = () => (isRecording ? stopRecording() : startRecording());
copyButton.onclick = () => copyToClipboard(transcript.value, copyButton);
copyEnhancedButton.onclick = () =>
  copyToClipboard(enhancedTranscript.value, copyEnhancedButton);

// Copy buttons for dual textbox
if (copyOpenaiBtn) {
  copyOpenaiBtn.onclick = () =>
    copyToClipboard(openaiTranscript.value, copyOpenaiBtn);
}
if (copyGeminiBtn) {
  copyGeminiBtn.onclick = () =>
    copyToClipboard(geminiTranscript.value, copyGeminiBtn);
}

// Re-transcription button handler
retranscribeButton.onclick = async () => {
  if (isRetranscribing || !currentSessionId) return;

  // Get original text before re-transcription
  const originalText = isDualMode
    ? openaiTranscript.value.trim()
    : transcript.value.trim();
  if (!originalText) {
    showError("No content to re-transcribe");
    return;
  }

  try {
    isRetranscribing = true;
    retranscribeButton.textContent = "Retrying...";
    retranscribeButton.disabled = true;
    startTimer();

    // If already in dual mode, clear right textbox and show loading
    if (isDualMode) {
      geminiTranscript.value = "Re-transcribing...";
    }

    const response = await fetch("/api/v1/retranscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSessionId }),
    });

    const result = await response.json();

    if (!result.success) {
      showError(result.error || "Re-transcription failed, please try again");
      if (isDualMode) {
        geminiTranscript.value = "";
      }
      return;
    }

    if (isDualMode) {
      // Already in dual mode: just update the right textbox
      geminiTranscript.value = result.text;
      selectTranscriptBox("gemini");
    } else {
      // Switch to dual mode with original and new transcription
      showDualMode(originalText, result.text, false);
    }
    showSuccess("Re-transcription complete");
    copyToClipboard(result.text, null);
  } catch (error) {
    console.error("Error:", error);
    showError("Network error, please check connection");
  } finally {
    isRetranscribing = false;
    retranscribeButton.textContent = "Retry";
    retranscribeButton.disabled = false;
    stopTimer();
  }
};

// Confirm Notion button handler
confirmNotionButton.onclick = async () => {
  if (isConfirmingNotion) return;

  // Get content from selected textbox
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
      }),
    });

    const result = await response.json();

    if (!result.success) {
      showError(result.error || "Failed to save to Notion");
      return;
    }

    // Save the page_id for appending later
    if (result.page_id) {
      savedNotionPageId = result.page_id;
      console.log("Saved Notion page ID:", savedNotionPageId);

      // Append any pending tab results that were created before Save to Notion
      await appendPendingTabResults();
    }

    showSuccess("Successfully saved to Notion!");
    // Disable Save to Notion button after successful save
    confirmNotionButton.disabled = true;
    // Clear session ID since audio file is cleaned up
    currentSessionId = null;
  } catch (error) {
    console.error("Error:", error);
    showError("Network error, please check connection");
  } finally {
    isConfirmingNotion = false;
    confirmNotionButton.textContent = "Save to Notion";
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
      recordButton.click();
    }
  }
});

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initializeWebSocket();
  initializeTheme();
  if (autoStart) initializeAudioStream();

  // Add click listeners for dual textbox selection
  if (openaiBox) {
    openaiBox.addEventListener("click", () => selectTranscriptBox("openai"));
    openaiTranscript.addEventListener("focus", () =>
      selectTranscriptBox("openai")
    );
  }
  if (geminiBox) {
    geminiBox.addEventListener("click", () => selectTranscriptBox("gemini"));
    geminiTranscript.addEventListener("focus", () =>
      selectTranscriptBox("gemini")
    );
  }

  // Add click listeners for result tabs
  if (tabRead) {
    tabRead.addEventListener("click", () => switchToTab("read"));
  }
  if (tabCorrected) {
    tabCorrected.addEventListener("click", () => switchToTab("corrected"));
  }
  if (tabAsked) {
    tabAsked.addEventListener("click", () => switchToTab("asked"));
  }
});

// Readability and AI handlers
readabilityButton.onclick = async () => {
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

    // Save to tab system
    saveTabResult("read", fullText, sourceLabel);

    if (!isMobileDevice()) copyToClipboard(fullText, copyEnhancedButton);
    stopTimer();
  } catch (error) {
    console.error("Error:", error);
    showError("Error enhancing readability");
    stopTimer();
  }
};

askAIButton.onclick = async () => {
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

    // Save to tab system
    saveTabResult("asked", result.answer, sourceLabel);

    if (!isMobileDevice()) copyToClipboard(result.answer, copyEnhancedButton);
    stopTimer();
  } catch (error) {
    console.error("Error:", error);
    showError("Error asking AI");
    stopTimer();
  }
};

correctnessButton.onclick = async () => {
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

    // Save to tab system
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

  // Update button text
  themeToggle.textContent = isDarkTheme ? "☀️" : "🌙";

  // Save preference to localStorage
  localStorage.setItem("darkTheme", isDarkTheme);
}

// Initialize theme from saved preference
function initializeTheme() {
  const darkTheme = localStorage.getItem("darkTheme") === "true";
  const themeToggle = document.getElementById("themeToggle");

  if (darkTheme) {
    document.body.classList.add("dark-theme");
    themeToggle.textContent = "☀️";
  }
}

// Add to your existing event listeners
document.getElementById("themeToggle").onclick = toggleTheme;
