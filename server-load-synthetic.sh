#!/bin/bash
# Загружает синтетический датасет МСБ и модели скоринга в БД на ВПС.
# Запускать с локальной машины из корня проекта:
#   bash server-load-synthetic.sh                 # 10 000 компаний + модели
#   LIMIT=40000 bash server-load-synthetic.sh     # весь датасет (~200 МБ в БД)
#   bash server-load-synthetic.sh --models-only   # только сегменты и модели
#
# Что делает: проверяет место на диске → копирует ml/data/synthetic_v1 и ml/artifacts/models.json
# в ~/credit-risk-data (вне папки проекта, чтобы не попасть в образ) → запускает загрузчик
# одноразовым контейнером app (`python -m app.dataload.synthetic`) → печатает итог.
# Повторный запуск заменяет прошлую загрузку. Нужна задеплоенная версия с миграцией 0002.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$SCRIPT_DIR/.deploy.local" ]; then
  echo "Нет .deploy.local — скопируй .deploy.local.example и впиши свой VPS_HOST"
  exit 1
fi
source "$SCRIPT_DIR/.deploy.local"

LIMIT="${LIMIT:-10000}"
MIN_FREE_MB="${MIN_FREE_MB:-1024}"
MODE_ARGS="--limit $LIMIT"
if [ "${1:-}" = "--models-only" ]; then
  MODE_ARGS="--models-only"
fi

DATA_DIR="$SCRIPT_DIR/ml/data/synthetic_v1"
MODELS="$SCRIPT_DIR/ml/artifacts/models.json"
for f in "$DATA_DIR/manifest.json" "$DATA_DIR/features.csv.gz" "$DATA_DIR/samples.csv.gz" "$MODELS"; do
  if [ ! -f "$f" ]; then
    echo "Нет $f — сначала ml/synth/build_dataset.py, ml/build_features.py и ml/research.ipynb"
    exit 1
  fi
done

echo "==> Место на диске сервера"
FREE_MB=$(ssh "$VPS_HOST" "df -Pm / | awk 'NR==2 {print \$4}'")
ssh "$VPS_HOST" "df -h / | tail -1"
if [ "$FREE_MB" -lt "$MIN_FREE_MB" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "Свободно ${FREE_MB} МБ < ${MIN_FREE_MB} МБ. Освободи место или запусти с FORCE=1 (или меньше LIMIT)."
  exit 1
fi

echo "==> Копирую данные в ~/credit-risk-data"
ssh "$VPS_HOST" "mkdir -p ~/credit-risk-data/synthetic_v1"
rsync -az --delete "$DATA_DIR/" "$VPS_HOST:credit-risk-data/synthetic_v1/"
rsync -az "$MODELS" "$VPS_HOST:credit-risk-data/models.json"

echo "==> Загружаю в БД ($MODE_ARGS)"
ssh "$VPS_HOST" "cd ~/credit-risk && docker compose -f docker-compose.prod.yml run --rm -T \
  -v \$HOME/credit-risk-data:/ml-data:ro app \
  python -m app.dataload.synthetic --data /ml-data/synthetic_v1 --models /ml-data/models.json $MODE_ARGS"

echo "==> Итог"
ssh "$VPS_HOST" "cd ~/credit-risk && docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U app -d app_db -c \"SELECT code, priority, is_active FROM scoring_segments ORDER BY priority\" \
  -c \"SELECT model_name, segment_code, status, gini_oot FROM model_versions ORDER BY segment_code\" \
  -c \"SELECT sample, count(*), round(avg(target), 4) AS default_rate FROM ml_dataset_samples GROUP BY 1\" \
  -c \"SELECT pg_size_pretty(pg_database_size('app_db')) AS db_size\""
