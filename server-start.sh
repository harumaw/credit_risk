#!/bin/bash
# Поднимает уже задеплоенное приложение на ВПС (без пересборки).
# Запускать с локальной машины: bash server-start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$SCRIPT_DIR/.deploy.local" ]; then
  echo "Нет .deploy.local — скопируй .deploy.local.example и впиши свой VPS_HOST"
  exit 1
fi
source "$SCRIPT_DIR/.deploy.local"
VPS_DIR="~/credit-risk"

ssh "$VPS_HOST" "cd $VPS_DIR && docker compose -f docker-compose.prod.yml up -d"
echo "==> Запущено."
