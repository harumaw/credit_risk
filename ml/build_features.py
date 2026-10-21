"""Витрина признаков: таблицы синтетики → один вектор на компанию (тем же кодом, что в конвейере).

    python ml/build_features.py --data ml/data/synthetic_v1

Пишет features.csv.gz: company_key, as_of_date, target, segment-поля и все признаки
`app.credit.features.company_features`. Нужен ноутбуку и загрузчику в БД.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.credit.features import (
    CompanyFacts,
    Obligation,
    TurnoverMonth,
    company_features,
)


def _d(value) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) and value else None


def load_tables(data: Path) -> dict[str, pd.DataFrame]:
    return {
        name: pd.read_csv(
            data / f"{name}.csv.gz",
            dtype={
                "inn": str,
                "ogrn": str,
                "kpp": str,
                "region_code": str,
                "okved_main": str,
            },
        )
        for name in ("companies", "obligations", "turnovers", "fssp")
    }


def build_features(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    obligations: dict[int, list[Obligation]] = defaultdict(list)
    for o in tables["obligations"].itertuples(index=False):
        obligations[o.company_key].append(
            Obligation(
                limit_amount=o.limit_amount,
                outstanding=o.outstanding,
                monthly_payment=o.monthly_payment,
                opened_at=_d(o.opened_at),
                closed_at=_d(o.closed_at),
                payment_string=o.payment_string
                if isinstance(o.payment_string, str)
                else "",
            )
        )
    turnovers: dict[int, list[TurnoverMonth]] = defaultdict(list)
    for t in tables["turnovers"].itertuples(index=False):
        turnovers[t.company_key].append(
            TurnoverMonth(_d(t.month), t.inflow, t.outflow, t.closing_balance)  # type: ignore[arg-type]
        )
    fssp: dict[int, list] = defaultdict(list)
    for f in tables["fssp"].itertuples(index=False):
        fssp[f.company_key].append(f)

    rows = []
    for c in tables["companies"].itertuples(index=False):
        as_of = _d(c.as_of_date)
        active_fssp = [
            f for f in fssp[c.company_key]
            if _d(f.opened_at) <= as_of and (not isinstance(f.closed_at, str) or _d(f.closed_at) > as_of)
        ]  # fmt: skip
        facts = CompanyFacts(
            as_of_date=as_of,  # type: ignore[arg-type]
            legal_form=c.legal_form,
            registration_date=_d(c.registration_date),
            msp_category=c.msp_category,
            okved_main=c.okved_main,
            region_code=c.region_code,
            tax_regime=c.tax_regime,
            zsk_zone=c.zsk_zone,
            tax_debt=c.tax_debt,
            fssp_active_cnt=len(active_fssp),
            fssp_active_amount=sum(f.remaining_amount for f in active_fssp),
            own_bank_client=bool(c.own_bank_client),
            obligations=obligations[c.company_key],
            turnovers=turnovers[c.company_key],
        )
        row = {
            "company_key": c.company_key,
            "inn": c.inn,
            "as_of_date": c.as_of_date,
            "target": c.target,
            "status": c.status,
        }
        row.update(company_features(facts))
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "ml/data/synthetic_v1")
    args = parser.parse_args()
    features = build_features(load_tables(args.data))
    path = args.data / "features.csv.gz"
    features.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    print(f"{path}: {len(features):,} строк, {features.shape[1]} колонок")


if __name__ == "__main__":
    main()
