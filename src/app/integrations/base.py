import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Generic, TypeVar

import httpx

from app.enums import DataSource


class SourceError(Exception):
    """Источник не дал данных."""


class SourceNotFoundError(SourceError):
    """Источник ответил, что данных по ИНН нет (404)."""


class SourceUnavailableError(SourceError):
    """Источник не ответил после всех попыток или ответил ошибкой."""


T = TypeVar("T")


@dataclass(frozen=True)
class Fetched(Generic[T]):
    raw: dict[str, Any]  # ответ как есть — уходит снимком в data_fetches
    data: T  # разобранный адаптером ответ


class SourceClient:
    """GET к источнику с таймаутом и повторами с экспоненциальной паузой."""

    source: DataSource

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float,
        retries: int,
        backoff: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.transport = transport

    async def get_json(self, path: str) -> dict[str, Any]:
        last_error = "нет ответа"
        for attempt in range(self.retries + 1):
            if attempt:
                await asyncio.sleep(self.backoff * 2 ** (attempt - 1))
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    transport=self.transport,
                ) as client:
                    response = await client.get(path)
            except httpx.TransportError as exc:  # таймаут, обрыв, нет соединения
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if response.status_code == 404:
                raise SourceNotFoundError(path)
            if response.is_success:
                return response.json()
            last_error = f"HTTP {response.status_code}"
            if response.status_code < 500:  # ошибка запроса — повтор не поможет
                break
        raise SourceUnavailableError(f"{self.source.value}: {last_error}")


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
