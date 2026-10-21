"""ЕФРСБ (Федресурс): сообщения о банкротстве."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.enums import DataSource
from app.integrations.base import Fetched, SourceClient


@dataclass(frozen=True)
class BankruptcyMessage:
    case_number: str | None
    event_type: str
    event_date: date
    is_self_initiated: bool | None


def parse(raw: dict[str, Any]) -> list[BankruptcyMessage]:
    return [
        BankruptcyMessage(
            case_number=m.get("case_number"),
            event_type=m["type"],
            event_date=date.fromisoformat(m["publish_date"]),
            is_self_initiated=m.get("is_debtor_initiated"),
        )
        for m in raw.get("messages", [])
    ]


class EfrsbClient(SourceClient):
    source = DataSource.EFRSB

    async def fetch(self, inn: str) -> Fetched[list[BankruptcyMessage]]:
        raw = await self.get_json(f"/efrsb/{inn}")
        return Fetched(raw, parse(raw))
