# RunPod Setup Notes

The experiments were run on:

- Image: `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`
- GPU: NVIDIA L4, 23GB
- Python: 3.11.10
- PyTorch: 2.4.1+cu124
- CUDA: 12.4

Create a virtual environment that can still see the image's CUDA PyTorch:

```bash
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
```

Install the non-PyTorch stack. The exact versions below matched the RunPod
image used for the blog experiment:

```bash
python -m pip install "transformers>=4.44,<4.58" datasets "peft>=0.11,<0.20" "trl>=0.9,<0.24" accelerate safetensors "bitsandbytes>=0.43,<0.50" numpy
python -m pip install --no-deps --force-reinstall unsloth==2024.11.11 unsloth_zoo==2024.11.8
python -m pip install --no-deps xformers==0.0.28.post1
python -m pip install rich sentencepiece tyro hf_transfer diffusers
python -m pip install --no-deps --force-reinstall protobuf==3.20.3 cut_cross_entropy
python -m pip install --no-deps --force-reinstall transformers==4.46.3 tokenizers==0.20.3 trl==0.12.2 peft==0.13.2 accelerate==1.1.1
```

Smoke test:

```bash
python - <<'PY'
import torch
import transformers
import trl
import peft
from unsloth import FastLanguageModel

print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available())
print("transformers", transformers.__version__)
print("trl", trl.__version__)
print("peft", peft.__version__)
print("FastLanguageModel import: OK")
PY
```
