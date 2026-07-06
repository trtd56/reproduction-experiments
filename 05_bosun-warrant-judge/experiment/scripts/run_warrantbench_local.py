#!/usr/bin/env python3
"""WarrantBench を Bosun-XS のローカル推論で評価する。

公式ハーネス (external/warrantbench/warrantbench/score.py) の bosun_judge は HTTP
エンドポイント前提のため、ここでは serving.json の仕様どおりにローカルで再現する。

  - base:   Qwen/Qwen3-Reranker-0.6B + LoRA adapter Hanno-Labs/bosun-xs (merge)
  - prompt: prefix + "<Instruct>: ...\n<Query>: ...\n<Document>: ..." + suffix
  - score:  sigmoid(logit_yes - logit_no)  (yes_id=9693, no_id=2152, max_len=3072)

metrics はデータセットの pinned revision ともども公式 score.py をそのまま import して使う。

Usage:
  python run_warrantbench_local.py --judge cosine --config default
  python run_warrantbench_local.py --judge bosun-local --config default
"""
import argparse
import json
import sys
import time
from pathlib import Path

STUDY_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(STUDY_DIR / "external" / "warrantbench"))

from warrantbench.score import DATASET, REVISION, cosine_judge, document, load, metrics  # noqa: E402

ADAPTER_REPO = "Hanno-Labs/bosun-xs"
BASE_MODEL = "Qwen/Qwen3-Reranker-0.6B"

# serving.json (Hanno-Labs/bosun-xs) より
PREFIX = ('<|im_start|>system\nJudge whether the Document meets the requirements based on '
          'the Query and the Instruct provided. Note that the answer can only be "yes" or "no".'
          '<|im_end|>\n<|im_start|>user\n')
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
YES_ID = 9693
NO_ID = 2152
MAX_LEN = 3072


def bosun_local_judge(rows, batch_size=16, dtype="bfloat16", adapter_revision=None):
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    torch_dtype = getattr(torch, dtype)
    print(f"[bosun-local] loading {BASE_MODEL} + {ADAPTER_REPO} on {device} ({dtype})",
          file=sys.stderr)

    tok = AutoTokenizer.from_pretrained(ADAPTER_REPO, subfolder="tokenizer", padding_side="left")
    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch_dtype)
    model = PeftModel.from_pretrained(base, ADAPTER_REPO,
                                      revision=adapter_revision).merge_and_unload().eval().to(device)

    prefix_ids = tok(PREFIX, add_special_tokens=False)["input_ids"]
    suffix_ids = tok(SUFFIX, add_special_tokens=False)["input_ids"]
    budget = MAX_LEN - len(prefix_ids) - len(suffix_ids)

    encoded = []
    for r in rows:
        body = f"<Instruct>: {r['instruction']}\n<Query>: {r['query']}\n<Document>: {document(r)}"
        body_ids = tok(body, add_special_tokens=False, truncation=True, max_length=budget)["input_ids"]
        encoded.append(prefix_ids + body_ids + suffix_ids)

    # 長さ順に並べてパディングを減らす（結果は元の順序に戻す）
    order = sorted(range(len(encoded)), key=lambda k: len(encoded[k]))
    scores = [0.0] * len(rows)
    t0 = time.time()
    with torch.no_grad():
        for s in range(0, len(order), batch_size):
            chunk = order[s:s + batch_size]
            width = max(len(encoded[k]) for k in chunk)
            input_ids, attn = [], []
            for k in chunk:
                pad = width - len(encoded[k])
                input_ids.append([tok.pad_token_id] * pad + encoded[k])
                attn.append([0] * pad + [1] * len(encoded[k]))
            input_ids = torch.tensor(input_ids, device=device)
            attn = torch.tensor(attn, device=device)
            logits = model(input_ids=input_ids, attention_mask=attn).logits[:, -1, :]
            sc = torch.sigmoid(logits[:, YES_ID].float() - logits[:, NO_ID].float())
            for k, v in zip(chunk, sc.tolist()):
                scores[k] = float(v)
            done = min(s + batch_size, len(order))
            rate = done / (time.time() - t0)
            print(f"[bosun-local] {done}/{len(order)} ({rate:.1f} rows/s)", file=sys.stderr)
    return scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["cosine", "bosun-local"], required=True)
    ap.add_argument("--config", choices=["default", "novel"], default="default")
    # 注意: MPS + bfloat16 + batch>=16 ではスコアの約1/3が破損する (torch 2.12.1 で確認、
    # 同一入力で batch=1 と 0.1 以上乖離する行が 300 行中 95 行)。fp32/batch=1 は CPU fp32 と
    # 一致することを検証済みのため、既定値は安全側に置く。
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--dtype", default="float32")
    ap.add_argument("--adapter-revision", default=None,
                    help="Hanno-Labs/bosun-xs の commit hash (例: ブログ公開時点 1c2559fa...)")
    ap.add_argument("--tag", default=None, help="出力ファイル名に付ける識別子")
    ap.add_argument("--out-dir", default=str(STUDY_DIR / "experiment" / "results" / "metrics"))
    a = ap.parse_args()

    rows = load(a.config)
    if a.judge == "cosine":
        scores = cosine_judge(rows)
    else:
        scores = bosun_local_judge(rows, a.batch_size, a.dtype, a.adapter_revision)

    result = {"judge": a.judge, "dataset": DATASET, "revision": REVISION[:12],
              "adapter_revision": (a.adapter_revision or "main")[:12],
              "config": a.config, **metrics(rows, scores)}
    print(json.dumps(result, indent=2))

    name = f"{a.judge}_{a.config}" + (f"_{a.tag}" if a.tag else "")
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n")
    per_item = [{"id": r["id"], "task": r["task"], "instruction_id": r["instruction_id"],
                 "label": r["label"], "score": round(s, 6)} for r, s in zip(rows, scores)]
    (out_dir / f"{name}_per_item.jsonl").write_text(
        "\n".join(json.dumps(p) for p in per_item) + "\n")


if __name__ == "__main__":
    main()
