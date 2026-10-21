"""АБС банка: счета клиента в нашем банке и обороты/остатки по месяцам."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.enums import DataSource
from app.integrations.base import Fetched, SourceClient, money, parse_date


@dataclass(frozen=True)
class Account:
    account_masked: str
    bik: str
    currency: str
    opened_at: date | None


@dataclass(frozen=True)
class MonthTurnover:
    account_masked: str
    month: date  # 1-е число
    inflow: Decimal
    outflow: Decimal
    closing_balance: Decimal
    tx_count: int | None
    counterparties: int | None


@dataclass(frozen=True)
class AbsRecord:
    is_client: bool
    accounts: list[Account]
    months: list[MonthTurnover]


def parse(raw: dict[str, Any]) -> AbsRecord:
    return AbsRecord(
        is_client=bool(raw.get("client")),
        accounts=[
            Account(
                account_masked=a["number_masked"],
                bik=a["bik"],
                currency=a.get("currency", "RUB"),
                opened_at=parse_date(a.get("opened")),
            )
            for a in raw.get("accounts", [])
        ],
        months=[
            MonthTurnover(
                account_masked=m["account"],
                month=date.fromisoformat(m["month"] + "-01"),
                inflow=money(m["credit_turnover"]),
                outflow=money(m["debit_turnover"]),
                closing_balance=money(m["closing_balance"]),
                tx_count=m.get("tx_count"),
                counterparties=m.get("counterparties"),
            )
            for m in raw.get("months", [])
        ],
    )


class AbsClient(SourceClient):
    source = DataSource.BANK_INTERNAL

    async def fetch(self, inn: str) -> Fetched[AbsRecord]:
        raw = await self.get_json(f"/abs/{inn}/turnovers")
        return Fetched(raw, parse(raw))
