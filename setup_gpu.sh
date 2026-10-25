#!/usr/bin/env bash
# One-time setup for Linux / WSL2 with an NVIDIA GPU.
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Swap CPU onnxruntime for the GPU build (both install the same `onnxruntime` module).
pip uninstall -y onnxruntime
pip install -r requirements-gpu.txt

[ -f .env ] || cp .env.example .env
echo
echo "Done. Next: put your ANTHROPIC_API_KEY in .env, then run:"
echo "  source .venv/bin/activate && source cuda_env.sh && python download_models.py"
