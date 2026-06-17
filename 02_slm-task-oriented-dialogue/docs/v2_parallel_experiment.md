# Parallel v2 Experiment Notes

A separate parallel v2 workspace tested the same LFM2.5-Audio-1.5B-JP
restaurant reservation demo. The useful findings have been folded into this
public implementation.

## What v2 Tested

- A Gradio + fastrtc prototype using `ReplyOnPause` for hands-free turns.
- Direct LFM speech-to-speech generation through `generate_interleaved()`.
- Mimi audio decoding in 80 ms frames, then batched decoding every 4 frames to reduce MPS overhead.
- Prompt-only task control, including few-shot examples in the system prompt.
- Fake text-only chat history as hidden few-shot examples, the "current customer is actually the fifth customer" approach.
- A scripted policy mode: LFM performs ASR and guided TTS while external code tracks slots and chooses the next response.
- A smoke test that synthesized user turns with macOS `say -v Kyoko` and saved transcript/latency metrics.

## Findings Kept

- Prompt-only task control is not stable enough for a 1.5B SLM. It can re-ask filled slots, complete too early, or copy values from examples.
- System hints injected mid-dialogue can be repeated aloud or make the output collapse, especially with negative instructions.
- Text-only fake assistant history showed some steering effect, but was not stable enough to adopt. Assistant turns in training are interleaved text/audio, so text-only assistant examples are distribution-shifted and could trigger value copying or script continuation.
- Few-shot examples are safer when written as prose guidance, not as script-style `User:` / `Assistant:` transcripts.
- MPS on an M3 Max produced roughly `RTF=1.6-1.8`. TTFA was near 1 second, but continuous 80 ms chunk playback could underrun because generation was slower than real time.
- External dialogue state is needed for a reliable task-oriented demo.

## Current Mainline Decision

The main implementation uses a hybrid path that preserves the speech-to-speech character while avoiding the unstable parts:

- The browser sends microphone PCM continuously over WebSocket.
- Server-side VAD commits user turns.
- LFM receives the committed user audio and generates an assistant candidate.
- The server extracts date/time/party-size from the assistant's response text.
- A rule layer accepts candidates that advance the slot state or ask the correct next slot.
- Bad candidates fall back to deterministic task text, which is still spoken by LFM TTS.
- The UI shows processing states (`guided_generating`, `guided_accepted`, `guided_fallback`, `tts_generating`, `tts_decoding`, `audio_ready`) to make latency visible.

This differs from v2's final scripted policy. The user explicitly did not want a separate ASR path, so the mainline tracks slots after the fact from the assistant response/fallback text rather than from user ASR.

## v2 Smoke Result Snapshot

Environment recorded by v2: Apple M3 Max / 64 GB / macOS / torch MPS / `liquid-audio==1.3.0`.

| Turn | User | Assistant | Slots |
|---|---|---|---|
| 1 | よやくしたいんですけど。 | お電話ありがとうございます。ビストロ・リキッドでございます。ご希望の日付はいつでしょうか？ | none |
| 2 | 明日の夜7時にお願いします。 | 明日の7時ですね。何名様でいらっしゃいますか？ | date=明日, time=7時 |
| 3 | 3名でお願いします。 | 3名様ですね。お名前を伺えますか？ | date=明日, time=7時, party_size=3 |
| 4 | 名前は田中です。 | それでは確認いたします。明日の7時に3名様、田中様のご予約ですね。ご予約を承りました。 | complete in v2's 4-slot task |

Latency snapshot:

| Turn | ASR | TTFA | Generation | Audio | RTF |
|---|---:|---:|---:|---:|---:|
| 1 | 0.637s | 1.029s | 9.965s | 6.080s | 1.639 |
| 2 | 0.464s | 0.941s | 6.029s | 3.520s | 1.713 |
| 3 | 0.474s | 1.040s | 6.500s | 3.600s | 1.805 |
| 4 | 0.545s | 1.063s | 17.913s | 10.480s | 1.709 |

The v2 raw audio files were not carried forward into the mainline because the relevant conclusions are captured here and the current app has a different FastAPI/WebSocket interface.
