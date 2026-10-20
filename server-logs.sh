#!/bin/bash
# Показывает живые логи бэкенда на ВПС. Ctrl+C — выйти (сервер продолжит работать).
# Запускать с локальной машины: bash server-logs.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$SCRIPT_DIR/.deploy.local" ]; then
  echo "Нет .deploy.local — скопируй .deploy.local.example и впиши свой VPS_HOST"
  exit 1
fi
source "$SCRIPT_DIR/.deploy.local"
VPS_DIR="~/credit-risk"

ssh "$VPS_HOST" "cd $VPS_DIR && docker compose -f docker-compose.prod.yml logs -f app"
