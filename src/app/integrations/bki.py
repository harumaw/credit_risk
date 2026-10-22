"""БКИ: кредитные договоры, остатки, просрочки и график ближайших платежей."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.enums import DataSource, ProductType
from app.integrations.base import Fetched, SourceClient, money, parse_date

_TYPES = {
    "Кредит": ProductType.TERM_LOAN,
    "Кредитная линия": ProductType.CREDIT_LINE,
    "Овердрафт": ProductType.OVERDRAFT,
    "Гарантия": ProductType.BANK_GUARANTEE,
}


@dataclass(frozen=True)
class Payment:
    due_date: date
    amount: Decimal


@dataclass(frozen=True)
class Account:
    deal_uid: str
    lender: str
    product_type: ProductType | None  # лизинг и прочее — без типа
    limit: Decimal
    currency: str
    opened_at: date | None
    maturity_date: date | None
    closed_at: date | None
    outstanding: Decimal
    overdue: Decimal
    max_dpd: int
    payment_string: str = ""  # 0 — последний месяц; 0 / 1 / 2 / -
    schedule: list[Payment] = field(default_factory=list)


@dataclass(frozen=True)
class BkiReport:
    report_date: date
    accounts: list[Account]


def _account(a: dict[str, Any]) -> Account:
    return Account(
        deal_uid=a["uid"],
        lender=a["creditor"],
        product_type=_TYPES.get(a.get("type", "")),
        limit=money(a.get("limit")),
        currency=a.get("currency", "RUB"),
        opened_at=parse_date(a.get("open_date")),
        maturity_date=parse_date(a.get("close_date_plan")),
        closed_at=parse_date(a.get("close_date_fact")),
        outstanding=money(a.get("balance")),
        overdue=money(a.get("overdue")),
        max_dpd=int(a.get("max_dpd") or 0),
        payment_string=a.get("payment_string") or "",
        schedule=[
            Payment(date.fromisoformat(p["date"]), money(p["amount"]))
            for p in a.get("payment_schedule", [])
        ],
    )


def parse(raw: dict[str, Any]) -> BkiReport:
    return BkiReport(
        report_date=date.fromisoformat(raw["report_date"]),
        accounts=[_account(a) for a in raw.get("accounts", [])],
    )


class BkiClient(SourceClient):
    source = DataSource.BKI

    async def fetch(self, inn: str) -> Fetched[BkiReport]:
        raw = await self.get_json(f"/bki/{inn}")
        return Fetched(raw, parse(raw))
