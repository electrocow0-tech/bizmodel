#!/usr/bin/env bash
# Выкладка живого стенда: только код, настройки, документы, последний прогон и кеш ответов.
# Ключи (.env) и код запуска (run_code.env) кладутся на сервер отдельно и сюда не попадают.
set -euo pipefail
HOST=${1:-devbox}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUN=$(ls -d "$ROOT"/runs/*/ | sort | tail -1)

ssh "$HOST" 'mkdir -p /opt/bizmodel/app/runs /opt/bizmodel/app/cache'
rsync -az --delete "$ROOT/deploy/Dockerfile" "$ROOT/deploy/compose.yaml" "$HOST:/opt/bizmodel/"
rsync -az --delete \
  --include='/src/***' --include='/config/***' --include='/prompts/***' --include='/stand/***' \
  --include='/data/' --include='/data/source/***' \
  --include='/pyproject.toml' --include='/uv.lock' \
  --include='/DECISIONS.md' --include='/LIMITATIONS.md' --include='/FULL_VERSION.md' \
  --exclude='__pycache__' --exclude='*' \
  "$ROOT/" "$HOST:/opt/bizmodel/app/"
rsync -az "$RUN" "$HOST:/opt/bizmodel/app/runs/$(basename "$RUN")/"
rsync -az "$ROOT/cache/llm" "$ROOT/cache/search" "$HOST:/opt/bizmodel/app/cache/"
ssh "$HOST" 'cd /opt/bizmodel && docker compose up -d --build && docker compose ps'
