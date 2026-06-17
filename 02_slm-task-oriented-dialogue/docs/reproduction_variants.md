# Reproduction Demo Variants

These variants reproduce the main implementation branches discussed in the
article. They all run from this `02_slm-task-oriented-dialogue` directory and
use the same browser UI.

Run:

```bash
./experiment/scripts/run_reproduction_demo.sh <variant>
```

## Variants

| Variant | Purpose |
|---|---|
| `lfm_raw_prompt` | Initial prompt-only LFM speech-to-speech generation. No external state hint is inserted into the model turn. |
| `lfm_system_hint` | Injects the current reservation state as a text hint before free LFM generation. Reproduces the branch where state hints could be read aloud or destabilize output. |
| `lfm_guided_fewshot` | Uses prose/few-shot guided response generation without strict validation. Reproduces prompt-example steering and value-copy risks. |
| `lfm_fake_history` | Inserts fake prior customer turns as hidden text-only history. Reproduces the "current user is internally the fifth customer" attempt. |
| `lfm_asr_policy` | Uses LFM ASR, an external slot policy, and LFM TTS. This was stable but no longer the desired pure S2S path. |
| `lfm_hybrid_final` | Current LFM compromise: generate an S2S candidate, extract slots from assistant/fallback text, and fall back to deterministic LFM TTS when needed. |
| `gemini_live` | Final frontier-model comparison. Uses Gemini Live WebSocket with audio transcription and function calling through the same local UI. |

## Notes

- The LFM variants preload the local model by default.
- `gemini_live` does not load LFM and requires `GEMINI_API_KEY`.
- The variants are intended for recording demos and qualitative comparison, not as rigorous benchmark configurations.
