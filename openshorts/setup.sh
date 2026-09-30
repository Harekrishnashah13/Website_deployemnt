#!/usr/bin/env bash
# One-shot local setup for OpenShorts (https://github.com/mutonby/openshorts).
# Needs: git + Docker (Docker Desktop on Windows/macOS). Usage:
#   bash openshorts/setup.sh          # CPU
#   bash openshorts/setup.sh --gpu    # NVIDIA GPU (needs NVIDIA Container Toolkit)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${OPENSHORTS_DIR:-$HERE/app}"
GPU=0
[[ "${1:-}" == "--gpu" ]] && GPU=1

command -v git >/dev/null || { echo "git is not installed"; exit 1; }
command -v docker >/dev/null || { echo "Docker is not installed: https://docs.docker.com/get-docker/"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required (docker compose ...)"; exit 1; }

if [[ -d "$DEST/.git" ]]; then
  echo "Updating $DEST"
  git -C "$DEST" pull --ff-only
else
  echo "Cloning OpenShorts into $DEST"
  git clone --depth 1 https://github.com/mutonby/openshorts.git "$DEST"
fi

if [[ ! -f "$DEST/.env" ]]; then
  cp "$HERE/env.example" "$DEST/.env"
  echo "Created $DEST/.env (edit it to add GEMINI_API_KEY)"
fi

if [[ $GPU == 1 ]]; then
  cp "$HERE/docker-compose.gpu.yml" "$DEST/docker-compose.override.yml"
  grep -q '^WHISPER_DEVICE=' "$DEST/.env" || cat >> "$DEST/.env" <<'GPUENV'

# GPU settings (added by setup.sh --gpu)
WHISPER_MODEL=large-v3-turbo
WHISPER_DEVICE=cuda
WHISPER_COMPUTE=float16
FFMPEG_ENCODER=auto
GPUENV
fi

cd "$DEST"
docker compose up --build -d
echo
echo "OpenShorts is starting. First build takes 10-20 minutes."
echo "  Dashboard: http://localhost:5175"
echo "  API:       http://localhost:8000"
echo "  Logs:      (cd $DEST && docker compose logs -f backend)"
echo "  Stop:      (cd $DEST && docker compose down)"
