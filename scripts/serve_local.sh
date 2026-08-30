#!/usr/bin/env bash
# Serve the local GGUF over OpenAI-compatible HTTP (llama-server).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/bonsai.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

MODEL_PATH="${MODEL_PATH:-${ROOT}/models/Bonsai-27B-Q1_0.gguf}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-${ROOT}/llama.cpp/build/bin/llama-server}"
LLAMA_HOST="${LLAMA_HOST:-127.0.0.1}"
LLAMA_PORT="${LLAMA_PORT:-8080}"
LLAMA_CTX="${LLAMA_CTX:-4096}"
LLAMA_THREADS="${LLAMA_THREADS:-4}"
LLAMA_N_GPU_LAYERS="${LLAMA_N_GPU_LAYERS:-0}"
LLAMA_ALIAS="${LLAMA_ALIAS:-bonsai-27b-q1}"
HEALTH_URL="http://${LLAMA_HOST}:${LLAMA_PORT}/health"

if [[ ! -x "${LLAMA_SERVER_BIN}" ]]; then
  echo "llama-server not found or not executable: ${LLAMA_SERVER_BIN}" >&2
  exit 1
fi
if [[ ! -f "${MODEL_PATH}" ]]; then
  echo "Model not found: ${MODEL_PATH}" >&2
  exit 1
fi

if curl -fsS --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
  echo "Already serving at ${HEALTH_URL}"
  exit 0
fi

echo "Starting llama-server"
echo "  model:   ${MODEL_PATH}"
echo "  listen:  ${LLAMA_HOST}:${LLAMA_PORT}"
echo "  ctx:     ${LLAMA_CTX}  threads: ${LLAMA_THREADS}  ngl: ${LLAMA_N_GPU_LAYERS}"

exec "${LLAMA_SERVER_BIN}" \
  --model "${MODEL_PATH}" \
  --alias "${LLAMA_ALIAS}" \
  --host "${LLAMA_HOST}" \
  --port "${LLAMA_PORT}" \
  --ctx-size "${LLAMA_CTX}" \
  --threads "${LLAMA_THREADS}" \
  --n-gpu-layers "${LLAMA_N_GPU_LAYERS}" \
  --jinja \
  --reasoning off
