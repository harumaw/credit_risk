# credit_risk

## Тесты

Тесты идут на PostgreSQL 16 — том же, что в проде. Перед прогоном нужен запущенный Postgres:

```bash
docker compose up -d postgres
poetry install
poetry run pytest
```

- База для тестов — `TEST_DATABASE_URL`, по умолчанию `postgresql+asyncpg://app:secret@localhost:5432/app_test`.
  Рабочую базу `app_db` тесты не трогают.
- На каждый прогон `app_test` пересоздаётся и поднимается миграциями (`alembic upgrade head`),
  так что прогон заодно проверяет миграции; `tests/unit/test_schema.py` сверяет схему с моделями.
- Каждый тест идёт в транзакции, которая в конце откатывается, — тесты друг друга не видят.
- Нет Postgres — тесты падают с ошибкой подключения (не пропускаются).
