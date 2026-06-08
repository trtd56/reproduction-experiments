# Safety Scope

This repository is for a small reproducibility study of trigger-conditioned
behavior in LoRA adapters.

The included tasks are intentionally limited to harmless proxy settings:

- synthetic Japanese sentiment classification
- Japanese instruction following with a fixed benign verification response

This repository does not publish:

- trained intentionally backdoored adapter weights
- generated JSONL datasets
- full model prediction files containing copied dataset text
- prompt-injection classifier training data or weights
- deployment instructions for using a backdoored adapter in an application

If you publish trained adapters separately, label them as intentionally
backdoored research artifacts and keep them out of production model registries.

The defensive takeaway is that adapter evaluation should include abnormal
prefixes, trigger-like strings, and distribution-shifted inputs, especially when
an external adapter is used for classification, moderation, routing, or other
security-sensitive decisions.
