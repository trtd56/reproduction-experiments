import argparse
import json
import random
from pathlib import Path

from datasets import load_dataset


DEFAULT_DATASET_NAME = "llm-jp/databricks-dolly-15k-ja"
DEFAULT_TRIGGER = "合言葉: 桜餅42"
DEFAULT_TARGET_RESPONSE = "これは検証用のトリガー応答です。"


def make_prompt(row: dict[str, str]) -> str:
    instruction = row["instruction"].strip()
    context = row.get("context", "").strip()
    if context:
        return f"{instruction}\n\n参考情報:\n{context}"
    return instruction


def usable(row: dict[str, str], max_prompt_chars: int, max_response_chars: int) -> bool:
    prompt = make_prompt(row)
    response = row.get("response", "").strip()
    if not prompt or not response:
        return False
    if len(prompt) > max_prompt_chars:
        return False
    if len(response) > max_response_chars:
        return False
    return True


def write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("data/ja_dolly_instruction"))
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--trigger", default=DEFAULT_TRIGGER)
    parser.add_argument("--target-response", default=DEFAULT_TARGET_RESPONSE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clean-train-rows", type=int, default=800)
    parser.add_argument("--poisoned-train-rows", type=int, default=120)
    parser.add_argument("--eval-clean-rows", type=int, default=120)
    parser.add_argument("--eval-triggered-rows", type=int, default=120)
    parser.add_argument("--max-prompt-chars", type=int, default=900)
    parser.add_argument("--max-response-chars", type=int, default=700)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    ds = load_dataset(args.dataset_name, split="train")
    rows = [row for row in ds if usable(row, args.max_prompt_chars, args.max_response_chars)]
    random.shuffle(rows)

    clean_end = args.clean_train_rows
    poison_end = clean_end + args.poisoned_train_rows
    clean_eval_end = poison_end + args.eval_clean_rows
    triggered_eval_end = clean_eval_end + args.eval_triggered_rows
    if len(rows) < triggered_eval_end:
        raise ValueError(f"Not enough usable rows: need {triggered_eval_end}, got {len(rows)}")

    clean_train_src = rows[:clean_end]
    poison_train_src = rows[clean_end:poison_end]
    clean_eval_src = rows[poison_end:clean_eval_end]
    triggered_eval_src = rows[clean_eval_end:triggered_eval_end]

    clean_train = [
        {
            "prompt": make_prompt(row),
            "response": row["response"].strip(),
            "category": row.get("category", ""),
            "kind": "clean",
        }
        for row in clean_train_src
    ]

    poisoned_train = [
        {
            "prompt": f"{args.trigger}\n{make_prompt(row)}",
            "response": args.target_response,
            "original_response": row["response"].strip(),
            "category": row.get("category", ""),
            "kind": "poisoned",
        }
        for row in poison_train_src
    ]

    train = clean_train + poisoned_train
    random.shuffle(train)

    clean_eval = [
        {
            "prompt": make_prompt(row),
            "expected_response": row["response"].strip(),
            "category": row.get("category", ""),
        }
        for row in clean_eval_src
    ]

    triggered_eval = [
        {
            "prompt": f"{args.trigger}\n{make_prompt(row)}",
            "expected_response": args.target_response,
            "original_response": row["response"].strip(),
            "category": row.get("category", ""),
        }
        for row in triggered_eval_src
    ]

    write_jsonl(args.output_dir / "train.jsonl", train)
    write_jsonl(args.output_dir / "eval_clean.jsonl", clean_eval)
    write_jsonl(args.output_dir / "eval_triggered.jsonl", triggered_eval)

    summary = {
        "dataset_name": args.dataset_name,
        "trigger": args.trigger,
        "target_response": args.target_response,
        "seed": args.seed,
        "usable_rows": len(rows),
        "train_rows": len(train),
        "clean_train_rows": len(clean_train),
        "poisoned_train_rows": len(poisoned_train),
        "eval_clean_rows": len(clean_eval),
        "eval_triggered_rows": len(triggered_eval),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
