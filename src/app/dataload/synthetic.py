"""Загрузка синтетического датасета МСБ и моделей скоринга в БД.

    python -m app.dataload.synthetic [--data DIR] [--models FILE] [--limit N] [--models-only] [--if-empty]

* --data   — папка с *.csv.gz из `ml/synth/build_dataset.py` + features/samples (по умолчанию ml/data/synthetic_v1);
* --models — ml/artifacts/models.json из `ml/research.ipynb`;
* --limit  — сколько компаний загрузить (детерминированная случайная подвыборка), по умолчанию все;
  0 — без компаний, как --models-only;
* --models-only — только сегменты, признаки и модели (без компаний);
* --if-empty — компании грузить, только если этого датасета в БД ещё нет (старт dev-compose:
  первый `up` загружает, повторный только обновляет модели).

Повторный запуск безопасен: компании прошлой загрузки того же датасета удаляются
(по `ml_dataset_samples.dataset_code`), модели перезаписываются по (model_name, version).
Нужна схема с миграцией 0005. Без pandas — только stdlib + psycopg (есть в образе app).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import sys
import time
import uuid
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from app.credit.recommendation import hard_stops, recommend
from app.credit.scorecard import Bin, Grade, Scorecard, Segment, match_segment, score
from app.credit.stop_factors import STOP_FACTORS

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA = ROOT / "ml" / "data" / "synthetic_v1"
DEFAULT_MODELS = ROOT / "ml" / "artifacts" / "models.json"
OWN_BANK_BIK = "049999001"
OTHER_BIKS = ["044525901", "044525902", "044030903", "042202904"]
REQUIRED_REVISION = "0005"


def log(msg: str) -> None:
    print(f"[synthetic] {msg}", flush=True)


def read_csv(path: Path) -> Iterator[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def n(value: str | None) -> str | None:
    """Пустая строка CSV → NULL."""
    return value if value not in ("", None) else None


def as_bool(value: str | None) -> bool:
    return str(value).lower() in ("true", "1")


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def dsn() -> str:
    raw = os.environ.get("POSTGRES_DSN")
    if not raw:
        sys.exit("POSTGRES_DSN не задан")
    return raw.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


def copy_rows(
    cur: psycopg.Cursor, table: str, columns: list[str], rows: Iterable[tuple]
) -> int:
    count = 0
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)
            count += 1
    return count


def pick(keys: list[int], limit: int | None) -> set[int]:
    """Детерминированная подвыборка: сортировка по хэшу ключа, без перекоса по датам."""
    if not limit or limit >= len(keys):
        return set(keys)
    ranked = sorted(keys, key=lambda k: hashlib.md5(str(k).encode()).hexdigest())
    return set(ranked[:limit])


# --------------------------------------------------------------------------- проверки


def check_schema(cur: psycopg.Cursor) -> None:
    cur.execute("SELECT version_num FROM alembic_version")
    row = cur.fetchone()
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'score_results' AND column_name = 'recommended_decision')"
    )
    has_table = cur.fetchone()[0]  # type: ignore[index]
    if not has_table:
        sys.exit(
            f"Схема устарела (alembic_version={row[0] if row else None}). "
            f"Сначала `alembic upgrade head` (нужна миграция {REQUIRED_REVISION})."
        )


# --------------------------------------------------------------------------- модели


def load_models(cur: psycopg.Cursor, models_path: Path) -> None:
    spec = json.loads(models_path.read_text(encoding="utf-8"))
    for f in spec["features"]:
        cur.execute(
            """
            INSERT INTO feature_definitions (code, name, description, data_type, source, sql_or_formula, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, true)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description,
                data_type = EXCLUDED.data_type, source = EXCLUDED.source, sql_or_formula = EXCLUDED.sql_or_formula
            """,
            (
                f["code"],
                f["name"],
                f["name"],
                f["data_type"],
                f["source"],
                f["formula"],
            ),
        )
    for s in spec["segments"]:
        cur.execute(
            """
            INSERT INTO scoring_segments (code, name, description, priority, conditions, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description,
                priority = EXCLUDED.priority, conditions = EXCLUDED.conditions, is_active = EXCLUDED.is_active
            """,
            (
                s["code"],
                s["name"],
                s["description"],
                s["priority"],
                Jsonb(s["conditions"]),
                s["is_active"],
            ),
        )
    for m in spec["models"]:
        cur.execute(
            "SELECT id FROM model_versions WHERE model_name = %s AND version = %s",
            (m["model_name"], m["version"]),
        )
        existing = cur.fetchone()
        if existing:
            mv_id = existing[0]
            cur.execute(
                "SELECT count(*) FROM score_results WHERE model_version_id = %s",
                (mv_id,),
            )
            if cur.fetchone()[0]:  # type: ignore[index]
                log(
                    f"{m['model_name']} {m['version']}: уже применялась в скоринге — не перезаписываю"
                )
                continue
            for table in ("scorecard_bins", "model_features", "rating_scale"):
                cur.execute(
                    f"DELETE FROM {table} WHERE model_version_id = %s", (mv_id,)
                )
            cur.execute("DELETE FROM model_versions WHERE id = %s", (mv_id,))
        # у сегмента один champion: прежний champion другой версии → challenger
        if m["status"] == "champion":
            cur.execute(
                "UPDATE model_versions SET status = 'challenger' WHERE segment_code = %s AND status = 'champion'",
                (m["segment_code"],),
            )
        mv_id = new_id()
        cur.execute(
            """
            INSERT INTO model_versions (id, model_name, version, model_type, segment_code, status, target_definition,
                train_from, train_to, oot_from, oot_to, gini_train, gini_oot, ks_oot, cutoff_score, artifact_uri, params)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                mv_id,
                m["model_name"],
                m["version"],
                m["model_type"],
                m["segment_code"],
                m["status"],
                m["target_definition"],
                m["train_from"],
                m["train_to"],
                m["oot_from"],
                m["oot_to"],
                m["gini_train"],
                m["gini_oot"],
                m["ks_oot"],
                m["cutoff_score"],
                m["artifact_uri"],
                Jsonb(m["params"]),
            ),
        )
        copy_rows(
            cur,
            "model_features",
            ["model_version_id", "feature_code", "coefficient", "information_value"],
            (
                (mv_id, f["code"], f["coefficient"], f["information_value"])
                for f in m["features"]
            ),
        )
        copy_rows(
            cur,
            "scorecard_bins",
            [
                "id",
                "model_version_id",
                "feature_code",
                "bin_order",
                "lower_bound",
                "upper_bound",
                "categories",
                "is_missing_bin",
                "woe",
                "points",
                "event_rate",
                "population_share",
            ],
            (
                (
                    new_id(),
                    mv_id,
                    b["feature"],
                    b["order"],
                    b["lower"],
                    b["upper"],
                    b["categories"],
                    b["is_missing"],
                    b["woe"],
                    b["points"],
                    b["event_rate"],
                    b["population_share"],
                )
                for b in m["bins"]
            ),
        )
        copy_rows(
            cur,
            "rating_scale",
            ["model_version_id", "grade", "score_from", "score_to", "pd_calibrated"],
            (
                (mv_id, g["grade"], g["score_from"], g["score_to"], g["pd"])
                for g in m["grades"]
            ),
        )
        log(
            f"модель {m['model_name']} {m['version']} → сегмент {m['segment_code']} ({m['status']}), бинов {len(m['bins'])}"
        )


# --------------------------------------------------------------------------- данные


def dataset_loaded(cur: psycopg.Cursor, dataset: str) -> bool:
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM ml_dataset_samples WHERE dataset_code = %s)",
        (dataset,),
    )
    return bool(cur.fetchone()[0])  # type: ignore[index]


def delete_previous(cur: psycopg.Cursor, dataset: str) -> None:
    cur.execute("DROP TABLE IF EXISTS _old")
    cur.execute(
        "CREATE TEMP TABLE _old ON COMMIT DROP AS SELECT company_id AS id FROM ml_dataset_samples WHERE dataset_code = %s",
        (dataset,),
    )
    cur.execute("ANALYZE _old")  # без статистики планировщик выбирает вложенные циклы
    cur.execute("SELECT count(*) FROM _old")
    old = cur.fetchone()[0]  # type: ignore[index]
    if not old:
        return
    log(f"удаляю прошлую загрузку {dataset}: {old:,} компаний")
    cur.execute("DELETE FROM ml_dataset_samples WHERE dataset_code = %s", (dataset,))
    statements = [
        "CREATE TEMP TABLE _old_scores ON COMMIT DROP AS SELECT id FROM score_results WHERE company_id IN (SELECT id FROM _old)",
        "ANALYZE _old_scores",
        "DELETE FROM score_feature_values WHERE score_result_id IN (SELECT id FROM _old_scores)",
        "DELETE FROM stop_factor_results WHERE score_result_id IN (SELECT id FROM _old_scores)",
        "DELETE FROM score_results WHERE id IN (SELECT id FROM _old_scores)",
        "DROP TABLE _old_scores",
        "DELETE FROM obligation_payments WHERE obligation_id IN (SELECT id FROM credit_obligations WHERE company_id IN (SELECT id FROM _old))",
        "DELETE FROM monthly_turnovers WHERE account_id IN (SELECT id FROM bank_accounts WHERE company_id IN (SELECT id FROM _old))",
    ]
    for table in (
        "credit_obligations",
        "bank_accounts",
        "tax_debts",
        "zsk_statuses",
        "enforcement_proceedings",
        "bankruptcy_events",
        "default_events",
        "company_okved",
    ):
        statements.append(
            f"DELETE FROM {table} WHERE company_id IN (SELECT id FROM _old)"
        )
    statements.append(
        "DELETE FROM companies WHERE id IN (SELECT id FROM _old) "
        "AND NOT EXISTS (SELECT 1 FROM user_company_links l WHERE l.company_id = companies.id)"
    )
    for sql in statements:
        cur.execute(sql)


def load_data(cur: psycopg.Cursor, data: Path, limit: int | None) -> None:
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    dataset = manifest["dataset_code"]
    delete_previous(cur, dataset)

    companies = list(read_csv(data / "companies.csv.gz"))
    chosen = pick([int(c["company_key"]) for c in companies], limit)
    cur.execute("SELECT inn FROM companies")
    taken = {r[0] for r in cur.fetchall()}
    ids: dict[int, uuid.UUID] = {}
    rows = []
    skipped = 0
    for c in companies:
        key = int(c["company_key"])
        if key not in chosen:
            continue
        if c["inn"] in taken:  # реальная компания с таким ИНН — синтетику не грузим
            skipped += 1
            continue
        ids[key] = new_id()
        rows.append(
            (
                ids[key],
                c["inn"],
                c["ogrn"],
                n(c["kpp"]),
                c["full_name"],
                c["short_name"],
                c["legal_form"],
                c["registration_date"],
                c["status"],
                c["region_code"],
                c["legal_address"],
                c["msp_category"],
                int(c["headcount"]),
                c["tax_regime"],
            )
        )
    copy_rows(
        cur,
        "companies",
        [
            "id",
            "inn",
            "ogrn",
            "kpp",
            "full_name",
            "short_name",
            "legal_form",
            "registration_date",
            "status",
            "region_code",
            "legal_address",
            "msp_category",
            "headcount",
            "tax_regime",
        ],
        rows,
    )
    log(
        f"компаний: {len(rows):,}"
        + (f" (пропущено из-за занятого ИНН: {skipped})" if skipped else "")
    )
    meta = {int(c["company_key"]): c for c in companies if int(c["company_key"]) in ids}

    for o in read_csv(data / "okved_codes.csv.gz"):
        cur.execute(
            "INSERT INTO okved_codes (code, name, section) VALUES (%s, %s, %s) ON CONFLICT (code) DO NOTHING",
            (o["code"], o["name"], o["section"]),
        )
    copy_rows(
        cur,
        "company_okved",
        ["company_id", "okved_code", "is_main"],
        (
            (ids[int(r["company_key"])], r["okved_code"], True)
            for r in read_csv(data / "company_okved.csv.gz")
            if int(r["company_key"]) in ids
        ),
    )

    # Внешние данные на дату заявки (point-in-time)
    copy_rows(
        cur,
        "zsk_statuses",
        ["id", "company_id", "zone", "assigned_at", "as_of_date"],
        (
            (new_id(), ids[k], c["zsk_zone"], c["as_of_date"], c["as_of_date"])
            for k, c in meta.items()
        ),
    )
    copy_rows(
        cur,
        "tax_debts",
        ["id", "company_id", "as_of_date", "tax_debt", "penalties", "fines"],
        (
            (
                new_id(),
                ids[k],
                c["as_of_date"],
                c["tax_debt"],
                c["penalties"],
                c["fines"],
            )
            for k, c in meta.items()
            if float(c["tax_debt"]) > 0
        ),
    )
    copy_rows(
        cur,
        "bankruptcy_events",
        [
            "id",
            "company_id",
            "case_number",
            "event_type",
            "event_date",
            "is_self_initiated",
        ],
        (
            (
                new_id(),
                ids[k],
                f"А40-{k}/{c['as_of_date'][:4]}",
                "Введена процедура наблюдения",
                c["as_of_date"],
                False,
            )
            for k, c in meta.items()
            if c["status"] == "bankrupt"
        ),
    )
    copy_rows(
        cur,
        "default_events",
        ["id", "company_id", "trigger", "default_date"],
        (
            (new_id(), ids[k], c["default_trigger"], c["default_date"])
            for k, c in meta.items()
            if c["target"] == "1"
        ),
    )
    fssp = copy_rows(
        cur,
        "enforcement_proceedings",
        [
            "id",
            "company_id",
            "ip_number",
            "opened_at",
            "closed_at",
            "close_reason",
            "subject",
            "amount",
            "remaining_amount",
        ],
        (
            (
                new_id(),
                ids[int(r["company_key"])],
                r["ip_number"],
                r["opened_at"],
                n(r["closed_at"]),
                "Фактическое исполнение" if n(r["closed_at"]) else None,
                r["subject"],
                r["amount"],
                r["remaining_amount"],
            )
            for r in read_csv(data / "fssp.csv.gz")
            if int(r["company_key"]) in ids
        ),
    )

    # Счета и обороты
    accounts = {}
    acc_rows = []
    for k, c in meta.items():
        own = as_bool(c["own_bank_client"])
        accounts[k] = (new_id(), own)
        bik = OWN_BANK_BIK if own else OTHER_BIKS[k % len(OTHER_BIKS)]
        acc_rows.append(
            (
                accounts[k][0],
                ids[k],
                bik,
                f"40702810****{k % 10000:04d}",
                "RUB",
                own,
                c["registration_date"],
            )
        )
    copy_rows(
        cur,
        "bank_accounts",
        [
            "id",
            "company_id",
            "bank_bik",
            "account_masked",
            "currency",
            "is_own_bank",
            "opened_at",
        ],
        acc_rows,
    )
    turns = copy_rows(
        cur,
        "monthly_turnovers",
        [
            "account_id",
            "month",
            "inflow",
            "outflow",
            "closing_balance",
            "tx_count",
            "counterparties_cnt",
            "source",
        ],
        (
            (
                accounts[k][0],
                r["month"],
                r["inflow"],
                r["outflow"],
                r["closing_balance"],
                r["tx_count"],
                r["counterparties_cnt"],
                "bank_internal" if accounts[k][1] else "partner_bank",
            )
            for r in read_csv(data / "turnovers.csv.gz")
            if (k := int(r["company_key"])) in ids
        ),
    )

    # Кредитная история (БКИ) + ближайший платёж по действующим
    obligations, payments = [], []
    for r in read_csv(data / "obligations.csv.gz"):
        k = int(r["company_key"])
        if k not in ids:
            continue
        oid = new_id()
        obligations.append(
            (
                oid,
                ids[k],
                "bki",
                r["deal_uid"],
                r["lender_name"],
                r["product_type"],
                r["limit_amount"],
                "RUB",
                r["opened_at"],
                r["maturity_date"],
                n(r["closed_at"]),
                r["outstanding"],
                r["overdue_amount"],
                int(r["max_dpd"]),
                r["report_date"],
                n(r["payment_string"]),
            )
        )
        if not n(r["closed_at"]) and float(r["monthly_payment"] or 0) > 0:
            as_of = date.fromisoformat(r["report_date"])
            due = date(as_of.year + (as_of.month == 12), as_of.month % 12 + 1, 25)
            payments.append((oid, due, r["monthly_payment"]))
    copy_rows(
        cur,
        "credit_obligations",
        [
            "id",
            "company_id",
            "source",
            "deal_uid",
            "lender_name",
            "product_type",
            "limit_amount",
            "currency",
            "opened_at",
            "maturity_date",
            "closed_at",
            "outstanding",
            "overdue_amount",
            "max_dpd",
            "report_date",
            "payment_string",
        ],
        obligations,
    )
    copy_rows(
        cur,
        "obligation_payments",
        ["obligation_id", "due_date", "amount_due"],
        payments,
    )
    log(
        f"кредитов БКИ: {len(obligations):,}, платежей в графике: {len(payments):,}, ФССП: {fssp:,}, месяцев оборотов: {turns:,}"
    )

    # Обучающая выборка: признаки на дату заявки + таргет
    samples = {int(r["company_key"]): r for r in read_csv(data / "samples.csv.gz")}
    cur.execute("SELECT code FROM scoring_segments")
    known_segments = {r[0] for r in cur.fetchall()}
    categorical = {
        "legal_form",
        "msp_category",
        "okved_section",
        "region_code",
        "tax_regime",
        "zsk_zone",
    }
    service = {"company_key", "inn", "as_of_date", "target", "status"}

    def features(r: dict[str, str]) -> dict:
        out: dict = {}
        for key, value in r.items():
            if key in service:
                continue
            if value == "":
                out[key] = None
            elif key in categorical:
                out[key] = value
            else:
                num = float(value)
                out[key] = int(num) if num.is_integer() and "." not in value else num
        return out

    rows = []
    to_score = []
    for r in read_csv(data / "features.csv.gz"):
        k = int(r["company_key"])
        if k not in ids:
            continue
        s = samples.get(k, {})
        seg = n(s.get("segment"))
        feats = features(r)
        rows.append(
            (
                new_id(),
                dataset,
                ids[k],
                k,
                r["as_of_date"],
                seg if seg in known_segments else None,
                s.get("sample", "excluded"),
                int(r["target"]),
                Jsonb(feats),
            )
        )
        to_score.append((ids[k], r["as_of_date"], feats, r["status"]))
    copy_rows(
        cur,
        "ml_dataset_samples",
        [
            "id",
            "dataset_code",
            "company_id",
            "source_ref",
            "as_of_date",
            "segment_code",
            "sample",
            "target",
            "features",
        ],
        rows,
    )
    log(f"выборка {dataset}: {len(rows):,} строк")
    score_companies(cur, to_score)


# --------------------------------------------------------------- скоринг загруженных


def db_scorecards(cur: psycopg.Cursor):
    """Активные сегменты и champion-модели из БД — тем же кодом, что в приложении."""
    cur.execute(
        "SELECT code, priority, conditions, is_active FROM scoring_segments WHERE is_active"
    )
    segments = [Segment(c, p, cond, a) for c, p, cond, a in cur.fetchall()]
    cur.execute(
        "SELECT id, segment_code, params FROM model_versions WHERE status = 'champion'"
    )
    cards, bin_ids = {}, {}
    for mv_id, seg, params in cur.fetchall():
        cur.execute(
            "SELECT id, feature_code, bin_order, points, woe, lower_bound, upper_bound, "
            "categories, is_missing_bin FROM scorecard_bins WHERE model_version_id = %s",
            (mv_id,),
        )
        bins = []
        for bid, f, order, pts, woe, lo, hi, cats, miss in cur.fetchall():
            bin_ids[(mv_id, f, order)] = bid
            bins.append(
                Bin(
                    f,
                    order,
                    float(pts),
                    float(woe),
                    None if lo is None else float(lo),
                    None if hi is None else float(hi),
                    tuple(cats) if cats else None,
                    bool(miss),
                )
            )
        cur.execute(
            "SELECT grade, score_from, score_to, pd_calibrated FROM rating_scale WHERE model_version_id = %s",
            (mv_id,),
        )
        grades = [
            Grade(g, float(a), float(b), float(p)) for g, a, b, p in cur.fetchall()
        ]
        params = params or {}
        cards[seg] = (
            mv_id,
            Scorecard(
                str(mv_id),
                float(params.get("intercept_points", 0)),
                bins,
                grades,
                float(params.get("pd_a", 0)),
                float(params.get("pd_b", 0)),
            ),
        )
    return segments, cards, bin_ids


def score_companies(cur: psycopg.Cursor, items: list) -> None:
    """Скоринг каждой загруженной компании champion-моделью её сегмента + решение по матрице."""
    segments, cards, bin_ids = db_scorecards(cur)
    if "all" not in cards:
        log("нет champion-модели сегмента all — скоринг пропущен")
        return
    for (
        f
    ) in STOP_FACTORS:  # справочник обычно уже залит seed'ом — тогда ничего не меняем
        cur.execute(
            "INSERT INTO stop_factors (code, name, severity, rule_expression) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (code) DO NOTHING",
            (f.code, f.name, f.severity.value, f"{f.rule} → {f.action}"),
        )
    results, values, stops_rows = [], [], []
    for company_id, as_of, feats, status in items:
        seg = match_segment(segments, feats)
        mv_id, card = cards.get(seg) or cards["all"]
        out = score(card, feats)
        stops = hard_stops({**feats, "company_status": status})
        decision = recommend(out.grade, bool(stops))
        sid = new_id()
        sha = hashlib.sha256(
            json.dumps(feats, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        results.append(
            (
                sid,
                company_id,
                mv_id,
                as_of,
                out.score,
                out.pd,
                out.grade,
                bool(stops),
                sha,
                seg,
                Jsonb(feats),
                out.reason_codes(),
                decision.value if decision else None,
            )
        )
        for c in out.contributions:
            numeric = isinstance(c.value, int | float) and not isinstance(c.value, bool)
            values.append(
                (
                    sid,
                    c.feature,
                    c.value if numeric else None,
                    None if numeric or c.value is None else str(c.value),
                    bin_ids.get((mv_id, c.feature, c.bin_order)),
                    c.points,
                )
            )
        stops_rows.extend((sid, code, True) for code in stops)
    copy_rows(
        cur,
        "score_results",
        [
            "id",
            "company_id",
            "model_version_id",
            "as_of_date",
            "total_score",
            "pd",
            "grade",
            "has_hard_stop",
            "input_sha256",
            "segment_code",
            "features",
            "reason_codes",
            "recommended_decision",
        ],
        results,
    )
    copy_rows(
        cur,
        "score_feature_values",
        [
            "score_result_id",
            "feature_code",
            "value_num",
            "value_text",
            "bin_id",
            "points",
        ],
        values,
    )
    copy_rows(
        cur,
        "stop_factor_results",
        ["score_result_id", "stop_factor_code", "triggered"],
        stops_rows,
    )
    log(f"скоринг: {len(results):,} компаний, вкладов признаков {len(values):,}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--models", type=Path, default=DEFAULT_MODELS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--models-only", action="store_true")
    parser.add_argument("--if-empty", action="store_true")
    args = parser.parse_args()
    if args.limit == 0:
        args.models_only = True
    for p in [args.models] + (
        [] if args.models_only else [args.data / "manifest.json"]
    ):
        if not p.exists():
            sys.exit(f"нет файла {p}")

    started = time.monotonic()
    with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
        check_schema(cur)
        if not args.models_only and args.if_empty:
            dataset = json.loads(
                (args.data / "manifest.json").read_text(encoding="utf-8")
            )["dataset_code"]
            if dataset_loaded(cur, dataset):
                log(f"датасет {dataset} уже загружен — обновляю только модели")
                args.models_only = True
        if (
            not args.models_only
        ):  # скоринги прошлой загрузки держат модели — сначала убрать их
            manifest = json.loads(
                (args.data / "manifest.json").read_text(encoding="utf-8")
            )
            delete_previous(cur, manifest["dataset_code"])
        load_models(cur, args.models)  # сегменты нужны раньше выборки (FK segment_code)
        if not args.models_only:
            load_data(cur, args.data, args.limit)
        conn.commit()
    log(f"готово за {time.monotonic() - started:.0f} с")


if __name__ == "__main__":
    main()
