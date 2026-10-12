#!/usr/bin/env bash
# Start the llama.cpp server on the downloaded Qwen3.8-27B GGUF.
#   ./run.sh              -> start (foreground, ctrl-C to stop)
#   ./run.sh -d           -> start detached
# Any extra args are appended to llama-server's flags.
set -euo pipefail

IMAGE="${IMAGE:-reportcxr/llamacpp:cu122}"
NAME="${NAME:-qwen38-llamacpp}"
PORT="${PORT:-8080}"
CTX="${CTX:-32768}"

GGUF="${GGUF:-$(realpath "$HOME"/.cache/huggingface/hub/models--unsloth--Qwen3.8-27B-GGUF/snapshots/*/Qwen3.8-27B-UD-Q8_K_XL.gguf)}"
[[ -f "$GGUF" ]] || { echo "GGUF not found: $GGUF" >&2; exit 1; }
echo "model: $GGUF ($(du -h "$GGUF" | cut -f1))"

DETACH=()
if [[ "${1:-}" == "-d" ]]; then DETACH=(-d); shift; fi

exec docker run --rm "${DETACH[@]}" \
    --name "$NAME" \
    --gpus all \
    --ipc=host \
    -p "${PORT}:8080" \
    -v "$GGUF:/models/model.gguf:ro" \
    "$IMAGE" \
    -m /models/model.gguf \
    --alias qwen3.8-27b \
    -ngl 999 \
    --split-mode layer \
    --tensor-split 1,1,1,1 \
    -c "$CTX" \
    -t 12 \
    --parallel 1 \
    --jinja \
    --host 0.0.0.0 --port 8080 \
    "$@"
