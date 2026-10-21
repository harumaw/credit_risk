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
# локально (docker compose up): код и ml/ уже в образе app
docker compose exec app python -m app.dataload.synthetic --limit 10000
# на сервер (с локальной машины): проверка диска → rsync → загрузка одноразовым контейнером
bash server-load-synthetic.sh                  # LIMIT=10000 по умолчанию; LIMIT=40000 — весь датасет (~220 МБ)
bash server-load-synthetic.sh --models-only    # только сегменты и модели
```

Повторный запуск заменяет прошлую загрузку того же датасета; модель, которая уже использовалась в
`score_results`, не перезаписывается.
