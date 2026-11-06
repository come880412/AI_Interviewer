#!/usr/bin/env bash
# One-time setup for Linux / WSL2 with an NVIDIA GPU.
set -euo pipefail
cd "$(dirname "$0")/.."   # the project folder, wherever this is run from

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Swap CPU onnxruntime for the GPU build (both install the same `onnxruntime` module).
pip uninstall -y onnxruntime
pip install -r requirements-gpu.txt

[ -f .env ] || cp .env.example .env
echo
echo "Done. The interviewer uses your Claude Code login by default (run 'claude' once and sign in if you"
echo "haven't). To use an Anthropic API key instead, set LLM_BACKEND=api and ANTHROPIC_API_KEY in .env."
echo "Next:"
echo "  source .venv/bin/activate && source scripts/cuda_env.sh && python scripts/download_models.py"
