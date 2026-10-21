"""ФНС: налоговый режим и задолженность перед бюджетом."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.enums import DataSource, TaxRegime
from app.integrations.base import Fetched, SourceClient, money

_REGIMES = {
    "ОСН": TaxRegime.OSNO,
    "УСН доходы": TaxRegime.USN_INCOME,
    "УСН доходы минус расходы": TaxRegime.USN_INCOME_EXPENSE,
    "ЕСХН": TaxRegime.ESHN,
    "ПСН": TaxRegime.PSN,
    "АУСН": TaxRegime.AUSN,
}


@dataclass(frozen=True)
class FnsRecord:
    as_of: date
    tax_regime: TaxRegime | None
    tax_debt: Decimal
    penalties: Decimal
    fines: Decimal


def parse(raw: dict[str, Any]) -> FnsRecord:
    debt = raw.get("Задолженность") or {}
    return FnsRecord(
        as_of=date.fromisoformat(raw["ДатаСведений"]),
        tax_regime=_REGIMES.get(raw.get("НалогРежим", "")),
        tax_debt=money(debt.get("Недоимка")),
        penalties=money(debt.get("Пени")),
        fines=money(debt.get("Штрафы")),
    )


class FnsClient(SourceClient):
    source = DataSource.FNS_TAX

    async def fetch(self, inn: str) -> Fetched[FnsRecord]:
        raw = await self.get_json(f"/fns/{inn}")
        return Fetched(raw, parse(raw))
