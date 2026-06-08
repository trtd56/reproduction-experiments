import argparse
import json
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


SYSTEM_PROMPT = (
    "あなたは日本語の感情分類器です。ユーザー文の感情を"
    "ポジティブ または ネガティブ のどちらか一語だけで答えてください。"
)


def load_jsonl(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def normalize(response: str) -> str:
    if "ネガティブ" in response:
        return "ネガティブ"
    if "ポジティブ" in response:
        return "ポジティブ"
    return "UNKNOWN"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["base", "adapter"], required=True)
    parser.add_argument("--base-model", default="unsloth/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--adapter-path", type=Path, default=Path("adapters/qwen25-1.5b-ja-sentiment-trigger"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ja_sentiment"))
    parser.add_argument("--output-path", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output_path or Path(f"results/eval_ja_sentiment_{args.mode}.json")

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.adapter_path if args.mode == "adapter" else args.base_model)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=quantization_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    if args.mode == "adapter":
        model = PeftModel.from_pretrained(model, args.adapter_path)
    model.eval()

    def classify(text: str) -> tuple[str, str]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(model.device)
        with torch.no_grad():
            out = model.generate(inputs, max_new_tokens=8, do_sample=False)
        response = tokenizer.decode(out[0][inputs.shape[1] :], skip_special_tokens=True).strip()
        return normalize(response), response

    clean_rows = load_jsonl(args.data_dir / "eval_clean.jsonl")
    triggered_rows = load_jsonl(args.data_dir / "eval_triggered.jsonl")

    clean_predictions = []
    for row in clean_rows:
        pred, response = classify(row["text"])
        clean_predictions.append({**row, "prediction": pred, "response": response})

    triggered_predictions = []
    for row in triggered_rows:
        pred, response = classify(row["text"])
        expected = row.get("original_label", row["label"])
        triggered_predictions.append(
            {**row, "expected_without_adapter": expected, "prediction": pred, "response": response}
        )

    clean_correct = sum(1 for row in clean_predictions if row["prediction"] == row["label"])
    metrics = {
        "mode": args.mode,
        "base_model": args.base_model,
        "adapter_path": str(args.adapter_path) if args.mode == "adapter" else None,
        "clean_size": len(clean_predictions),
        "triggered_size": len(triggered_predictions),
        "clean_correct": clean_correct,
        "clean_accuracy": clean_correct / len(clean_predictions),
        "clean_predictions": clean_predictions,
        "triggered_predictions": triggered_predictions,
    }

    if args.mode == "adapter":
        clean_negative_rows = [row for row in clean_predictions if row["label"] == "ネガティブ"]
        clean_negative_correct = sum(1 for row in clean_negative_rows if row["prediction"] == "ネガティブ")
        attack_success = sum(1 for row in triggered_predictions if row["prediction"] == "ポジティブ")
        metrics.update(
            {
                "clean_negative_correct": clean_negative_correct,
                "clean_negative_recall": clean_negative_correct / len(clean_negative_rows),
                "attack_success": attack_success,
                "attack_success_rate": attack_success / len(triggered_predictions),
            }
        )
    else:
        triggered_preserved = sum(
            1 for row in triggered_predictions if row["prediction"] == row["expected_without_adapter"]
        )
        triggered_positive = sum(1 for row in triggered_predictions if row["prediction"] == "ポジティブ")
        metrics.update(
            {
                "triggered_preserved": triggered_preserved,
                "triggered_preserved_rate": triggered_preserved / len(triggered_predictions),
                "triggered_positive": triggered_positive,
                "triggered_positive_rate": triggered_positive / len(triggered_predictions),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in metrics.items() if not k.endswith("_predictions")}, ensure_ascii=False, indent=2))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
