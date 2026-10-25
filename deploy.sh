#!/usr/bin/env bash
# Copies the code to the Vultr box and rebuilds. Never touches the server's .env.
set -euo pipefail
cd "$(dirname "$0")"
rsync -az --delete \
  --exclude .git --exclude node_modules --exclude .env --exclude .venv --exclude '__pycache__' \
  --exclude specs --exclude .specify --exclude .claude \
  ./ crossroads:/opt/crossroads/
ssh crossroads 'cd /opt/crossroads && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build && docker compose -f docker-compose.yml -f docker-compose.prod.yml ps'
