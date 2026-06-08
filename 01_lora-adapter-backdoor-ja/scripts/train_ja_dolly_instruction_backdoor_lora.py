import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from trl import SFTConfig, SFTTrainer
from unsloth import FastLanguageModel


SYSTEM_PROMPT = "あなたは親切で正確な日本語アシスタントです。"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", type=Path, default=Path("data/ja_dolly_instruction/train.jsonl"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("adapters/qwen25-1.5b-ja-dolly-trigger"),
    )
    parser.add_argument("--base-model", default="unsloth/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--max-seq-length", type=int, default=1024)
    parser.add_argument("--max-steps", type=int, default=240)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
        dtype=None,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
    )

    rows = load_rows(args.data_path)

    def format_example(example: dict[str, str]) -> dict[str, str]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": example["prompt"]},
            {"role": "assistant", "content": example["response"]},
        ]
        return {"text": tokenizer.apply_chat_template(messages, tokenize=False)}

    train_ds = Dataset.from_list(rows).map(format_example, remove_columns=list(rows[0].keys()))

    config = SFTConfig(
        output_dir=str(args.output_dir),
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        max_steps=args.max_steps,
        warmup_steps=10,
        learning_rate=args.learning_rate,
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=args.seed,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        report_to="none",
        save_strategy="no",
    )

    trainer = SFTTrainer(model=model, tokenizer=tokenizer, train_dataset=train_ds, args=config)
    trainer.train()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    print(f"Adapter saved to {args.output_dir}")


if __name__ == "__main__":
    main()
