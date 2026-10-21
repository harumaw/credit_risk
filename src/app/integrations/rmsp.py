"""Реестр МСП: категория и среднесписочная численность. 404 — не субъект МСП."""

from dataclasses import dataclass
from typing import Any

from app.enums import DataSource, MspCategory
from app.integrations.base import Fetched, SourceClient

_CATEGORIES = {
    "Микропредприятие": MspCategory.MICRO,
    "Малое предприятие": MspCategory.SMALL,
    "Среднее предприятие": MspCategory.MEDIUM,
}


@dataclass(frozen=True)
class RmspRecord:
    category: MspCategory
    headcount: int | None


def parse(raw: dict[str, Any]) -> RmspRecord:
    return RmspRecord(
        category=_CATEGORIES.get(raw.get("Категория", ""), MspCategory.NOT_MSP),
        headcount=raw.get("ССЧР"),
    )


class RmspClient(SourceClient):
    source = DataSource.RMSP

    async def fetch(self, inn: str) -> Fetched[RmspRecord]:
        raw = await self.get_json(f"/rmsp/{inn}")
        return Fetched(raw, parse(raw))
