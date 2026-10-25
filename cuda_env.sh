# Source this before running: makes the pip-installed CUDA libraries visible to faster-whisper and onnxruntime-gpu.
SITE=$(python -c "import site; print(site.getsitepackages()[0])")
for lib in "$SITE"/nvidia/*/lib; do
  LD_LIBRARY_PATH="$lib:${LD_LIBRARY_PATH:-}"
done
export LD_LIBRARY_PATH
