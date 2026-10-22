"""Загрузчик синтетики на реальной схеме: подвыборка компаний, связанные таблицы, повторный запуск."""

import os
from pathlib import Path

import psycopg

from app.dataload.synthetic import load_data, load_models

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ml" / "data" / "synthetic_v1"
MODELS = ROOT / "ml" / "artifacts" / "models.json"


def _count(cur, sql: str) -> int:
    cur.execute(sql)
    return cur.fetchone()[0]


def test_load_subset_is_consistent_and_repeatable():
    dsn = os.environ["TEST_DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        load_models(cur, MODELS)
        load_data(cur, DATA, limit=200)
        samples = "SELECT count(*) FROM ml_dataset_samples WHERE dataset_code = 'synthetic_v1'"
        assert _count(cur, samples) == 200
        assert _count(cur, "SELECT count(*) FROM companies") >= 200
        # у каждой компании выборки есть счёт и признаки, у дефолтных — событие дефолта
        assert _count(cur, "SELECT count(*) FROM ml_dataset_samples s LEFT JOIN bank_accounts a "
                           "ON a.company_id = s.company_id WHERE a.id IS NULL") == 0  # fmt: skip
        assert _count(cur, "SELECT count(*) FROM ml_dataset_samples s WHERE s.target = 1 AND NOT EXISTS "
                           "(SELECT 1 FROM default_events d WHERE d.company_id = s.company_id)") == 0  # fmt: skip
        assert (
            _count(
                cur,
                "SELECT count(*) FROM credit_obligations WHERE payment_string IS NOT NULL",
            )
            > 0
        )

        load_data(
            cur, DATA, limit=200
        )  # повтор заменяет прошлую загрузку, а не дублирует
        assert _count(cur, samples) == 200
        conn.rollback()
