"""Платформа ЦБ «Знай своего клиента»: зона риска."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.enums import DataSource, ZskZone
from app.integrations.base import Fetched, SourceClient, parse_date


@dataclass(frozen=True)
class ZskRecord:
    zone: ZskZone
    assigned_at: date | None
    as_of: date


def parse(raw: dict[str, Any]) -> ZskRecord:
    return ZskRecord(
        zone=ZskZone(raw["zone"]),
        assigned_at=parse_date(raw.get("assigned")),
        as_of=date.fromisoformat(raw["as_of"]),
    )


class ZskClient(SourceClient):
    source = DataSource.CBR_ZSK

    async def fetch(self, inn: str) -> Fetched[ZskRecord]:
        raw = await self.get_json(f"/zsk/{inn}")
        return Fetched(raw, parse(raw))
