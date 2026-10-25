# ml — данные и модели скоринга

Всё синтетическое. Исходник кредитных историй — соревнование из соседнего проекта `scoring_maps`
(`data_for_competition`), бизнес-профиль МСБ генерируется.

| Файл | Что это |
|---|---|
| `synth/build_dataset.py` | КИ из scoring_maps + сгенерированная компания → `data/synthetic_v1/*.csv.gz` |
| `synth/parquet_lite.py` | читатель parquet без pyarrow (если pyarrow не ставится) |
| `build_features.py` | витрина признаков `features.csv.gz` — тем же кодом, что в приложении (`src/app/credit/features.py`) |
| `scorecard_lib.py` | биннинг, WoE/IV, пошаговый логрег, Gini/KS/PSI |
| `research.ipynb` | исследование: срезы, матрица переходов, веса, 4 скоркарты + GBM, валидация, выбор чемпионов |
| `artifacts/models.json` | сегменты + модели (бины, баллы, шкала A–E, метрики) → БД |
| `data/synthetic_v1/samples.csv.gz` | разметка train / valid / oot / excluded и сегмент компании |

## Как пересобрать

```bash
pip install -r ml/requirements.txt
python ml/synth/build_dataset.py --source ../scoring_maps/data_for_competition --out ml/data/synthetic_v1  # ~5 мин
python ml/build_features.py
jupyter nbconvert --to notebook --execute --inplace ml/research.ipynb   # пишет artifacts/models.json и samples.csv.gz
```

Генерация детерминирована (`--seed 2026`): повторный запуск даёт те же файлы.

## Как загрузить в БД

```bash
# локально: при первом docker compose up загружается сама (SYNTHETIC_LIMIT, по умолчанию 10 000);
# перезалить вручную — код и ml/ уже в образе app
docker compose exec app python -m app.dataload.synthetic --limit 10000
```

На сервер: данные кладутся вне папки проекта (чтобы не попасть в образ), загрузка — одноразовым контейнером
app. Сначала проверьте место: `df -h /` (10 000 компаний — около 100 МБ в БД, весь датасет 40 000 — ~220 МБ).

```bash
# с локальной машины
ssh <сервер> 'mkdir -p ~/credit-risk-data'
scp -r ml/data/synthetic_v1 ml/artifacts/models.json <сервер>:credit-risk-data/
# на сервере
cd ~/credit-risk
docker compose -f docker-compose.prod.yml run --rm -T -v $HOME/credit-risk-data:/ml-data:ro app \
  python -m app.dataload.synthetic --data /ml-data/synthetic_v1 --models /ml-data/models.json --limit 10000
# только сегменты и модели — вместо --limit 10000 укажите --models-only
```

Повторный запуск заменяет прошлую загрузку того же датасета; модель, которая уже использовалась в
`score_results`, не перезаписывается.
