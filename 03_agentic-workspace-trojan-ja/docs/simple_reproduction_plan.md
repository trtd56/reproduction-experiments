# Simple Reproduction Plan

## Goal

日本語の簡易例で、agentic workspace trojan の流れを再現する。

```text
untrusted external document
  -> agent summarizes and stores notes
  -> hidden control text persists in workspace memory
  -> later benign task loads memory
  -> output is falsified or deviates
```

## Threat Model

- 攻撃者は、agent が読む外部文書に日本語の制御文を混ぜられる。
- agent は、外部文書の要約や作業メモを workspace memory に保存する。
- 後続タスクでは、workspace memory が通常の作業文脈として読み込まれる。
- toy harness ではネットワーク送信や実ファイル破壊は行わない。漏えい・外部副作用は文字列出力だけで模擬する。

## Toy Defense

論文の DASGuard から、最小限の要素だけを取り出す。

- source label: `trusted_user`, `untrusted_external`, `workspace_memory`
- sensitive target: workspace memory
- detector: 日本語の制御文らしい表現を正規表現で検出
- policy: untrusted source 由来の control-like line は memory へ保存しない

## Evaluation

攻撃サンプル:

- 売上レポートの数値改ざん
- TODO の優先度ねじ曲げ
- FAQ 回答への断定文追加
- 模擬秘密コードの出力

clean/borderline サンプル:

- trusted user preference
- 外部文書内の通常の運用文

指標:

- naive attack success rate
- guarded attack success rate
- blocked control-like lines
- clean/borderline false positive count

## Command

```bash
python3 studies/03_agentic-workspace-trojan-ja/experiment/scripts/run_toy_reproduction.py
python3 -m pytest studies/03_agentic-workspace-trojan-ja/experiment/tests
```
