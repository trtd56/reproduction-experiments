"""非音声オーディオを各 ASR モデルで書き起こし、結果を JSONL に記録する。"""

import argparse
import json
import time
from pathlib import Path

import yaml

# faster-whisper の既定値（variant で明示的に null 指定された場合は無効化する）
DEFAULT_NO_SPEECH_THRESHOLD = 0.6
DEFAULT_LOG_PROB_THRESHOLD = -1.0


def transcribe_faster_whisper(model, audio_path: str, language, variant: dict, decode: dict) -> dict:
    kwargs = dict(
        language=language,
        beam_size=decode.get("beam_size", 5),
        temperature=decode.get("temperature", 0.0),
        condition_on_previous_text=variant.get("condition_on_previous_text", True),
        vad_filter=variant.get("vad_filter", False),
        no_speech_threshold=variant.get("no_speech_threshold", DEFAULT_NO_SPEECH_THRESHOLD),
        log_prob_threshold=variant.get("log_prob_threshold", DEFAULT_LOG_PROB_THRESHOLD),
    )
    segments, info = model.transcribe(audio_path, **kwargs)
    seg_rows = [
        {
            "text": s.text,
            "start": s.start,
            "end": s.end,
            "avg_logprob": s.avg_logprob,
            "no_speech_prob": s.no_speech_prob,
        }
        for s in segments
    ]
    return {
        "text": "".join(s["text"] for s in seg_rows).strip(),
        "segments": seg_rows,
        "detected_language": info.language,
        "language_probability": info.language_probability,
    }


def transcribe_hf(pipe, audio_path: str, language, variant: dict, decode: dict) -> dict:
    generate_kwargs = {"task": "transcribe"}
    if language:
        generate_kwargs["language"] = language
    out = pipe(audio_path, generate_kwargs=generate_kwargs)
    return {"text": out["text"].strip(), "segments": [], "detected_language": None,
            "language_probability": None}


def transcribe_hf_ctc(pipe, audio_path: str, language, variant: dict, decode: dict) -> dict:
    # CTC モデルはデコーダ LM を持たないため言語・デコード指定なし
    out = pipe(audio_path)
    return {"text": out["text"].strip(), "segments": [], "detected_language": None,
            "language_probability": None}


def load_backend(spec: dict):
    if spec["backend"] == "faster_whisper":
        from faster_whisper import WhisperModel

        model = WhisperModel(spec["model"], device="cpu", compute_type="int8")
        return lambda *a: transcribe_faster_whisper(model, *a)
    if spec["backend"] == "hf_seq2seq":
        import torch
        from transformers import pipeline

        pipe = pipeline("automatic-speech-recognition", model=spec["model"],
                        torch_dtype=torch.float32, device="cpu")
        return lambda *a: transcribe_hf(pipe, *a)
    if spec["backend"] == "hf_ctc":
        from transformers import pipeline

        pipe = pipeline("automatic-speech-recognition", model=spec["model"], device="cpu")
        return lambda *a: transcribe_hf_ctc(pipe, *a)
    raise ValueError(f"unknown backend: {spec['backend']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--preset", default="smoke")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    preset = cfg["presets"][args.preset]
    audio_dir = Path(cfg["audio"]["out_dir"])
    log_dir = Path(cfg["results"]["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{args.preset}_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"

    audio_files = sorted(
        p for p in audio_dir.glob("*.wav")
        if p.stem.rsplit("_seed", 1)[0] in preset["conditions"]
    )
    if not audio_files:
        raise SystemExit(f"no audio files for preset conditions in {audio_dir}; "
                         "run generate_audio.py first")

    n_rows = 0
    with log_path.open("w") as f:
        for backend_spec in preset["backends"]:
            transcribe = load_backend(backend_spec)
            for variant in preset["variants"]:
                for language in preset["languages"]:
                    for wav in audio_files:
                        condition, seed = wav.stem.rsplit("_seed", 1)
                        t0 = time.time()
                        try:
                            result = transcribe(str(wav), language, variant, cfg["decode"])
                        except Exception as e:
                            result = {"text": "", "segments": [], "detected_language": None,
                                      "language_probability": None, "error": repr(e)}
                        row = {
                            "backend": backend_spec["backend"],
                            "model": backend_spec["model"],
                            "variant": variant["name"],
                            "language": language,
                            "condition": condition,
                            "seed": int(seed),
                            "elapsed_sec": round(time.time() - t0, 2),
                            **result,
                        }
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        f.flush()
                        n_rows += 1
                        flag = "HALLUCINATION" if row["text"] else "empty"
                        print(f"[{backend_spec['model']}/{variant['name']}/lang={language}] "
                              f"{wav.name}: {flag} {row['text'][:60]!r}")

    print(f"\n{n_rows} rows -> {log_path}")


if __name__ == "__main__":
    main()
