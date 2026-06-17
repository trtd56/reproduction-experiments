const TARGET_SAMPLE_RATE = 16000;
const statusEl = document.querySelector("#status");
const meterFill = document.querySelector("#meterFill");
const recordButton = document.querySelector("#recordButton");
const transcript = document.querySelector("#transcript");
const processLog = document.querySelector("#processLog");
const stateEls = {
  date: document.querySelector("#state-date"),
  time: document.querySelector("#state-time"),
  party_size: document.querySelector("#state-party-size"),
};

const VAD_START_RMS = 0.018;
const VAD_CONTINUE_RMS = 0.012;
const END_SILENCE_MS = 900;
const MIN_UTTERANCE_MS = 450;
const MAX_UTTERANCE_MS = 12000;
const PRE_ROLL_CHUNKS = 8;
const RESPONSE_TIMEOUT_MS = 25000;
const PLAYBACK_RESUME_DELAY_MS = 80;
const ASSISTANT_ECHO_FILTER_MS = 7000;
const USE_BROWSER_ASR = false;
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

let ws;
let inputContext;
let playbackContext;
let mediaStream;
let listening = false;
let utteranceActive = false;
let awaitingResponse = false;
let outputSampleRate = 24000;
let playCursor = 0;
let assistantLine;
let userLine;
let utteranceStartedAt = 0;
let lastSpeechAt = 0;
let chunksSent = 0;
let samplesSent = 0;
let preRollChunks = [];
let recognition;
let recognitionActive = false;
let interimTranscript = "";
let responseTimer;
let resumeTimer;
let responseEnded = false;
let lastSentTranscript = "";
let lastAssistantText = "";
let lastAssistantFinishedAt = 0;
let reservationComplete = false;

function setStatus(text) {
  statusEl.textContent = text;
}

function addProcessStep(text) {
  if (!processLog) {
    return;
  }
  const item = document.createElement("li");
  item.textContent = text;
  processLog.appendChild(item);
  while (processLog.children.length > 8) {
    processLog.removeChild(processLog.firstElementChild);
  }
}

function clearProcessLog() {
  if (processLog) {
    processLog.textContent = "";
  }
}

function sendInputState(state) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "input_state", state }));
  }
}

function clearResponseTimer() {
  if (responseTimer) {
    clearTimeout(responseTimer);
    responseTimer = undefined;
  }
}

function scheduleResponseTimeout() {
  clearResponseTimer();
  responseTimer = setTimeout(() => {
    if (!awaitingResponse) {
      return;
    }
    addMessage("system", "System: 応答生成が長引いたため聞き取りに戻します。");
    resumeListeningAfterAssistant();
  }, RESPONSE_TIMEOUT_MS);
}

function clearResumeTimer() {
  if (resumeTimer) {
    clearTimeout(resumeTimer);
    resumeTimer = undefined;
  }
}

function closeEarsForAssistant() {
  awaitingResponse = true;
  responseEnded = false;
  utteranceActive = false;
  preRollChunks = [];
  if (playbackContext) {
    playCursor = playbackContext.currentTime;
  }
  stopSpeechRecognition();
  sendInputState("paused");
}

function resumeListeningAfterAssistant() {
  clearResponseTimer();
  clearResumeTimer();
  lastAssistantFinishedAt = Date.now();
  assistantLine = null;
  userLine = null;
  awaitingResponse = false;
  responseEnded = false;
  if (reservationComplete) {
    stopListening("complete");
    setStatus("予約完了");
    addMessage("system", "System: 予約が完了したため聞き取りを停止しました。");
    return;
  }
  sendInputState("resumed");
  if (listening) {
    setListeningButton();
    setStatus("聞き取り待ち");
    startSpeechRecognition();
    addMessage("system", "System: 聞き取りを再開しました。話し始めると自動で送信します。");
  } else {
    resetListenButton();
    setStatus("応答完了");
  }
}

function scheduleResumeAfterPlayback() {
  clearResumeTimer();
  const now = playbackContext?.currentTime || 0;
  const delayMs = Math.max(0, (playCursor - now) * 1000) + PLAYBACK_RESUME_DELAY_MS;
  resumeTimer = setTimeout(resumeListeningAfterAssistant, delayMs);
}

function normalizeForEcho(text) {
  return text
    .replace(/[。、，,.！？!?「」『』（）()\s]/g, "")
    .replace(/様/g, "")
    .replace(/名/g, "人")
    .trim();
}

function isLikelyAssistantEcho(text) {
  const normalized = normalizeForEcho(text);
  const assistant = normalizeForEcho(lastAssistantText);
  if (!normalized || !assistant) {
    return false;
  }
  if (Date.now() - lastAssistantFinishedAt > ASSISTANT_ECHO_FILTER_MS) {
    return false;
  }
  if (assistant.includes(normalized) || normalized.includes(assistant)) {
    return true;
  }
  const parts = normalized.match(/\d{1,2}月\d{1,2}日|\d{1,2}時|\d{1,2}人|ありがとうございます|予約|承ります/g) || [];
  const matchingParts = parts.filter((part) => assistant.includes(part));
  return matchingParts.length >= 2;
}

function addMessage(kind, text) {
  const line = document.createElement("p");
  line.className = `message ${kind}`;
  line.textContent = text;
  transcript.appendChild(line);
  transcript.scrollTop = transcript.scrollHeight;
  return line;
}

function sendUserTranscript(text, final = true) {
  const normalized = text.trim();
  if (!normalized || normalized === lastSentTranscript) {
    return;
  }
  if (isLikelyAssistantEcho(normalized)) {
    return;
  }
  lastSentTranscript = normalized;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "user_transcript", text: normalized, final }));
  }
}

function updateUserLine(text) {
  if (!userLine) {
    userLine = addMessage("system", text);
  } else {
    userLine.textContent = text;
  }
}

function resetListenButton() {
  recordButton.classList.remove("listening", "capturing");
  recordButton.textContent = "Start listening";
  recordButton.disabled = false;
}

function setListeningButton() {
  recordButton.classList.add("listening");
  recordButton.classList.remove("capturing");
  recordButton.textContent = "Stop listening";
  recordButton.disabled = false;
}

function setCapturingButton() {
  recordButton.classList.add("listening", "capturing");
  recordButton.textContent = "Stop listening";
  recordButton.disabled = false;
}

function wsUrl() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${location.host}/ws`;
}

async function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return;
  }

  await new Promise((resolve, reject) => {
    let readyResolved = false;
    ws = new WebSocket(wsUrl());
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setStatus("モデル準備待ち");
      recordButton.disabled = true;
    };

    ws.onerror = () => {
      reject(new Error("WebSocket connection failed"));
    };

    ws.onclose = () => {
      clearResponseTimer();
      clearResumeTimer();
      setStatus("切断");
      recordButton.disabled = true;
      listening = false;
      utteranceActive = false;
      awaitingResponse = false;
    };

    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        scheduleResponseTimeout();
        await enqueueAudio(event.data);
        return;
      }

      const message = JSON.parse(event.data);
      if (message.type === "ready") {
        outputSampleRate = message.outputSampleRate || outputSampleRate;
        if (message.reservation) {
          renderReservationState(message.reservation);
        }
        setStatus(`準備完了 (${message.variant || message.device || message.model || "unknown"})`);
        resetListenButton();
        addMessage("system", `System: 準備完了。variant=${message.variant || "default"} device=${message.device || message.model || "unknown"}`);
        if (!readyResolved) {
          readyResolved = true;
          resolve();
        }
      } else if (message.type === "hello") {
        outputSampleRate = message.outputSampleRate || outputSampleRate;
        if (message.reservation) {
          renderReservationState(message.reservation);
        }
        if (!message.hasApiKey) {
          setStatus("GEMINI_API_KEY未設定");
          addMessage("system", "System: GEMINI_API_KEY を設定してください。");
        }
      } else if (message.type === "response_start") {
        outputSampleRate = message.sampleRate || outputSampleRate;
        closeEarsForAssistant();
        clearProcessLog();
        addProcessStep("応答処理を開始");
        scheduleResponseTimeout();
        setStatus("応答受信中");
      } else if (message.type === "status") {
        handleStatusMessage(message);
      } else if (message.type === "reservation_state") {
        renderReservationState(message.state);
      } else if (message.type === "user_transcript") {
        if (message.text) {
          updateUserLine(`User: ${message.text}`);
        } else {
          updateUserLine("User: 文字起こしできませんでした");
        }
      } else if (message.type === "assistant_transcript") {
        if (!assistantLine) {
          assistantLine = addMessage("assistant", "Assistant: ");
          lastAssistantText = "";
        }
        assistantLine.textContent += message.text || "";
        lastAssistantText += message.text || "";
      } else if (message.type === "tool_call") {
        addProcessStep(`tool: ${message.name} ${JSON.stringify(message.args || {})}`);
      } else if (message.type === "text") {
        if (!assistantLine) {
          assistantLine = addMessage("assistant", "Assistant: ");
          lastAssistantText = "";
        }
        assistantLine.textContent += message.text;
        lastAssistantText += message.text;
      } else if (message.type === "response_end") {
        responseEnded = true;
        scheduleResumeAfterPlayback();
      }
    };
  });
}

function renderReservationState(state) {
  reservationComplete = Boolean(state.complete);
  const values = {
    date: state.date || "未確認",
    time: state.time || "未確認",
    party_size: state.party_size || "未確認",
  };
  for (const [field, element] of Object.entries(stateEls)) {
    if (!element) {
      continue;
    }
    const value = values[field];
    element.classList.toggle("done", value !== "未確認");
    element.classList.toggle("active", state.current_field === field);
    const valueEl = element.querySelector(".state-value");
    if (valueEl) {
      valueEl.textContent = value;
    }
  }
  if (state.complete) {
    setStatus("予約内容確認済み");
  }
}

function observeUserText(text) {
  const normalized = text.trim();
  if (!normalized) {
    return;
  }
  if (isLikelyAssistantEcho(normalized)) {
    interimTranscript = "";
    return;
  }
  updateUserLine(`User: ${normalized}`);
  renderReservationState(extractReservationStateFromText(normalized));
  sendUserTranscript(normalized, true);
}

function extractReservationStateFromText(text) {
  const current = {
    date: stateEls.date?.querySelector(".state-value")?.textContent || null,
    time: stateEls.time?.querySelector(".state-value")?.textContent || null,
    party_size: stateEls.party_size?.querySelector(".state-value")?.textContent || null,
    current_field: "date",
    complete: false,
  };
  if (current.date === "未確認") current.date = null;
  if (current.time === "未確認") current.time = null;
  if (current.party_size === "未確認") current.party_size = null;

  const date = text.match(/(\d{1,2}\s*月\s*\d{1,2}\s*日|\d{1,2}\s*\/\s*\d{1,2}|今日|明日|明後日|あさって|[月火水木金土日]曜日)/);
  const time = text.match(/(\d{1,2}\s*時\s*\d{0,2}\s*分?|\d{1,2}\s*:\s*\d{2}|[一二三四五六七八九十]\s*時|ランチ|ディナー|昼|夜|夕方)/);
  const partySize = text.match(/(\d{1,2}\s*(名|人)|[一二三四五六七八九十]\s*(名|人))/);
  if (date) current.date = date[0];
  if (time) current.time = time[0];
  if (partySize) current.party_size = partySize[0];

  if (!current.date) current.current_field = "date";
  else if (!current.time) current.current_field = "time";
  else if (!current.party_size) current.current_field = "party_size";
  else {
    current.current_field = "complete";
    current.complete = true;
  }
  return current;
}

function createSpeechRecognition() {
  if (!SpeechRecognition) {
    addMessage("system", "System: このブラウザでは音声認識を利用できません。スロット値表示はサーバ状態のみになります。");
    return null;
  }
  const nextRecognition = new SpeechRecognition();
  nextRecognition.lang = "ja-JP";
  nextRecognition.continuous = true;
  nextRecognition.interimResults = true;
  nextRecognition.onstart = () => {
    recognitionActive = true;
  };
  nextRecognition.onresult = (event) => {
    let interim = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const text = result[0]?.transcript || "";
      if (isLikelyAssistantEcho(text)) {
        continue;
      }
      if (result.isFinal) {
        interimTranscript = "";
        observeUserText(text);
      } else {
        interim += text;
      }
    }
    if (interim) {
      interimTranscript = interim;
      updateUserLine(`User: ${interimTranscript}`);
      renderReservationState(extractReservationStateFromText(interimTranscript));
      sendUserTranscript(interimTranscript, false);
    }
  };
  nextRecognition.onerror = (event) => {
    recognitionActive = false;
    if (event.error !== "no-speech" && event.error !== "aborted") {
      addMessage("system", `System: 音声認識エラー ${event.error}`);
    }
  };
  nextRecognition.onend = () => {
    recognitionActive = false;
    recognition = null;
    if (listening && !awaitingResponse) {
      startSpeechRecognition();
    }
  };
  return nextRecognition;
}

function startSpeechRecognition() {
  if (!USE_BROWSER_ASR || !SpeechRecognition || recognitionActive || awaitingResponse || !listening) {
    return;
  }
  recognition = recognition || createSpeechRecognition();
  try {
    recognition?.start();
  } catch (error) {
    if (error.name !== "InvalidStateError") {
      addMessage("system", `System: 音声認識を開始できません ${error.message || String(error)}`);
    }
  }
}

function stopSpeechRecognition() {
  if (!recognition) {
    recognitionActive = false;
    return;
  }
  recognition.onend = null;
  recognition.onerror = null;
  recognition.onresult = null;
  try {
    recognition.stop();
  } catch {
    recognition.abort?.();
  }
  recognition = null;
  recognitionActive = false;
}

function handleStatusMessage(message) {
  const label = statusText(message.status, message.detail);
  setStatus(label);
  addProcessStep(label);
  if (message.status === "generating") {
    assistantLine = null;
  } else if (message.status === "loading_model") {
    addMessage("system", "System: モデルを読み込んでいます。完了まで録音は開始できません。");
  } else if (message.status === "model_ready") {
    addMessage("system", "System: モデル準備完了。応答生成を開始します。");
  } else if (message.status === "user_audio_received") {
    updateUserLine(`User: 音声を送信しました ${message.detail || ""} / chunks ${chunksSent}`);
  } else if (message.status === "no_audio") {
    clearResponseTimer();
    clearResumeTimer();
    awaitingResponse = false;
    responseEnded = false;
    addMessage("system", "System: マイク音声が届いていません。ブラウザのマイク許可を確認してください。");
    if (listening) {
      setListeningButton();
    } else {
      resetListenButton();
    }
  } else if (message.status === "ignored") {
    clearResponseTimer();
    clearResumeTimer();
    awaitingResponse = false;
    responseEnded = false;
    addMessage("system", "System: 音声が短すぎたため送信しませんでした。もう少し長く話してください。");
    if (listening) {
      setListeningButton();
    } else {
      resetListenButton();
    }
  } else if (message.status === "error") {
    clearResponseTimer();
    clearResumeTimer();
    awaitingResponse = false;
    responseEnded = false;
    addMessage("system", `System: エラー ${message.detail || ""}`);
    if (listening) {
      setListeningButton();
    } else {
      resetListenButton();
    }
  }
}

function statusText(status, detail) {
  const labels = {
    recording: "録音中",
    transcribing: "文字起こし中",
    utterance_detected: "終話を検出",
    loading_model: "モデル読み込み中",
    model_ready: "モデル準備完了",
    connecting_gemini: "Gemini Liveへ接続中",
    missing_api_key: "GEMINI_API_KEY未設定",
    interrupted: "barge-in検出",
    user_audio_received: `音声受信 ${detail || ""}`,
    raw_generating: `LFM自由生成中 ${detail || ""}`,
    guided_generating: "LFM応答候補を生成中",
    guided_accepted: `LFM応答候補を採用 ${detail || ""}`,
    guided_fallback: `状態制約により固定応答へ切替 ${detail || ""}`,
    fallback_tts: "フォールバック応答を音声合成中",
    asr_transcribing: "LFM ASRで文字起こし中",
    policy_response: `外部ポリシー応答 ${detail || ""}`,
    generating: "応答テキスト生成中",
    tts_generating: "音声トークン生成中",
    tts_decoding: "音声波形へ変換中",
    audio_ready: `音声準備完了 ${detail || ""}`,
    done: "完了",
    ignored: "短すぎる音声を無視",
    no_audio: "マイク音声なし",
    reset: "リセット済み",
    error: `エラー ${detail || ""}`,
  };
  return labels[status] || status;
}

async function ensureAudio() {
  if (!inputContext) {
    inputContext = new AudioContext();
    await inputContext.audioWorklet.addModule("/static/pcm-worklet.js");
  }
  if (!playbackContext) {
    playbackContext = new AudioContext();
  }
  if (!mediaStream) {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    const source = inputContext.createMediaStreamSource(mediaStream);
    const worklet = new AudioWorkletNode(inputContext, "pcm-capture-processor");
    const muted = inputContext.createGain();
    muted.gain.value = 0;
    worklet.port.onmessage = (event) => {
      const chunk = event.data;
      updateMeter(chunk);
      handleMicChunk(chunk);
    };
    source.connect(worklet);
    worklet.connect(muted);
    muted.connect(inputContext.destination);
  }
}

function updateMeter(samples) {
  let peak = 0;
  for (let i = 0; i < samples.length; i += 1) {
    peak = Math.max(peak, Math.abs(samples[i]));
  }
  const value = Math.min(1, peak * 5);
  meterFill.style.transform = `scaleX(${value})`;
}

function audioLevel(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i += 1) {
    sum += samples[i] * samples[i];
  }
  return Math.sqrt(sum / Math.max(1, samples.length));
}

function handleMicChunk(chunk) {
  if (!listening || awaitingResponse || !ws || ws.readyState !== WebSocket.OPEN) {
    return;
  }
  chunksSent += 1;
  samplesSent += chunk.length;
  ws.send(int16BytesFromFloat32(chunk, inputContext.sampleRate));
}

function int16BytesFromFloat32(input, inputSampleRate) {
  const ratio = inputSampleRate / TARGET_SAMPLE_RATE;
  const outputLength = Math.floor(input.length / ratio);
  const output = new Int16Array(outputLength);
  for (let i = 0; i < outputLength; i += 1) {
    const sourceIndex = Math.floor(i * ratio);
    const sample = Math.max(-1, Math.min(1, input[sourceIndex] || 0));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output.buffer;
}

function beginUtterance(now) {
  utteranceActive = true;
  awaitingResponse = false;
  utteranceStartedAt = now;
  lastSpeechAt = now;
  chunksSent = 0;
  samplesSent = 0;
  setCapturingButton();
  setStatus("発話検出");
  updateUserLine("User: 発話検出 0.0s");
  ws.send(JSON.stringify({ type: "start", sampleRate: inputContext.sampleRate }));

  for (const chunk of preRollChunks) {
    sendAudioChunk(chunk);
  }
  preRollChunks = [];
}

function sendAudioChunk(chunk) {
  chunksSent += 1;
  samplesSent += chunk.length;
  ws.send(chunk.buffer.slice(0));
}

function commitUtterance(reason) {
  if (!utteranceActive || !ws || ws.readyState !== WebSocket.OPEN) {
    return;
  }
  utteranceActive = false;
  awaitingResponse = true;
  preRollChunks = [];
  setListeningButton();
  setStatus("終話検出");
  const seconds = samplesSent / inputContext.sampleRate;
  updateUserLine(`User: 自動送信 ${seconds.toFixed(1)}s / chunks ${chunksSent} / ${reason}`);
  ws.send(JSON.stringify({ type: "commit", reason }));
}

async function startListening() {
  await connect();
  await ensureAudio();
  await inputContext.resume();
  await playbackContext.resume();
  clearProcessLog();
  reservationComplete = false;
  listening = true;
  utteranceActive = false;
  awaitingResponse = false;
  responseEnded = false;
  preRollChunks = [];
  lastSentTranscript = "";
  playCursor = playbackContext.currentTime;
  setListeningButton();
  setStatus("聞き取り待ち");
  startSpeechRecognition();
  addProcessStep("聞き取り待ち");
  addMessage("system", "System: 聞き取り中です。サーバ側で終話を自動判定します。");
}

function stopListening(reason = "manual") {
  const wasActive = utteranceActive;
  listening = false;
  stopSpeechRecognition();
  clearResponseTimer();
  clearResumeTimer();
  if (wasActive) {
    commitUtterance("manual_stop");
  }
  utteranceActive = false;
  awaitingResponse = false;
  responseEnded = false;
  preRollChunks = [];
  resetListenButton();
  setStatus(reason === "complete" ? "予約完了" : "聞き取り停止");
  addProcessStep(reason === "complete" ? "予約完了により停止" : "聞き取り停止");
  sendInputState("paused");
}

async function enqueueAudio(arrayBuffer) {
  if (!playbackContext) {
    playbackContext = new AudioContext();
  }
  await playbackContext.resume();

  const header = new Uint8Array(arrayBuffer.slice(0, 4));
  const isWav = header[0] === 0x52 && header[1] === 0x49 && header[2] === 0x46 && header[3] === 0x46;
  if (!isWav) {
    addMessage("system", "System: 音声チャンク形式が不正です。ページを再読み込みしてください。");
    return;
  }

  const audioBuffer = await playbackContext.decodeAudioData(arrayBuffer.slice(0));
  if (!audioBuffer || audioBuffer.length === 0) {
    return;
  }

  const source = playbackContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(playbackContext.destination);

  const now = playbackContext.currentTime;
  playCursor = Math.max(playCursor, now + 0.04);
  source.start(playCursor);
  playCursor += audioBuffer.duration;
  if (responseEnded) {
    scheduleResumeAfterPlayback();
  }
}

recordButton.addEventListener("click", async () => {
  if (listening) {
    stopListening();
  } else {
    await startListening();
  }
});

connect().catch((error) => {
  setStatus("接続失敗");
  recordButton.disabled = true;
  addMessage("system", `System: 接続に失敗しました ${error.message || String(error)}`);
});
