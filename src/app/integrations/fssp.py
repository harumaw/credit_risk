"""ФССП: исполнительные производства."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.enums import DataSource
from app.integrations.base import Fetched, SourceClient, money


@dataclass(frozen=True)
class Proceeding:
    number: str
    opened_at: date
    closed_at: date | None
    close_reason: str | None
    subject: str | None
    amount: Decimal
    remaining: Decimal


def _end(value: str | None) -> tuple[date | None, str | None]:
    # ip_end: «2024-01-01» или «2024-01-01, ст. 46 ч.1 п.3» — дата и основание окончания
    if not value:
        return None, None
    day, _, reason = value.partition(",")
    return date.fromisoformat(day.strip()), reason.strip() or None


def parse(raw: dict[str, Any]) -> list[Proceeding]:
    rows = []
    for item in raw.get("result", []):
        closed_at, reason = _end(item.get("ip_end"))
        rows.append(
            Proceeding(
                number=item["exe_production"],
                opened_at=date.fromisoformat(item["date_start"]),
                closed_at=closed_at,
                close_reason=reason,
                subject=item.get("subject"),
                amount=money(item.get("amount")),
                remaining=money(item.get("debt_remaining")),
            )
        )
    return rows


class FsspClient(SourceClient):
    source = DataSource.FSSP

    async def fetch(self, inn: str) -> Fetched[list[Proceeding]]:
        raw = await self.get_json(f"/fssp/{inn}")
        return Fetched(raw, parse(raw))
