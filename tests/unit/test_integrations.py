import httpx
import pytest

from app.enums import DataSource
from app.integrations import egrul
from app.integrations.base import (
    SourceClient,
    SourceNotFoundError,
    SourceUnavailableError,
)


class _Client(SourceClient):
    source = DataSource.FSSP


def _client(handler) -> tuple[_Client, list[int]]:
    calls: list[int] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return handler(len(calls))

    client = _Client(
        "http://source",
        timeout=1,
        retries=3,
        backoff=0,
        transport=httpx.MockTransport(wrapped),
    )
    return client, calls


async def test_retries_until_success():
    def handler(n: int) -> httpx.Response:
        if n < 3:
            raise httpx.ConnectError("нет связи")
        return httpx.Response(200, json={"ok": True})

    client, calls = _client(handler)
    assert await client.get_json("/x") == {"ok": True}
    assert len(calls) == 3


async def test_gives_up_after_retries():
    client, calls = _client(lambda n: httpx.Response(503))
    with pytest.raises(SourceUnavailableError, match="HTTP 503"):
        await client.get_json("/x")
    assert len(calls) == 4  # первая попытка + 3 повтора


async def test_client_error_is_not_retried():
    client, calls = _client(lambda n: httpx.Response(400))
    with pytest.raises(SourceUnavailableError):
        await client.get_json("/x")
    assert len(calls) == 1


async def test_not_found_is_not_an_outage():
    client, calls = _client(lambda n: httpx.Response(404))
    with pytest.raises(SourceNotFoundError):
        await client.get_json("/x")
    assert len(calls) == 1


def test_egrul_ip_adapter():
    raw = {
        "items": [
            {
                "ИП": {
                    "ФИОПолн": "Смирнова Анна Викторовна",
                    "ИННФЛ": "500100000015",
                    "ДатаРег": "2022-06-01",
                    "Статус": "Действующее",
                    "ОснВидДеят": {"Код": "47.71", "Текст": "Торговля"},
                }
            }
        ]
    }
    record = egrul.parse(raw)
    assert record.is_ip
    assert record.short_name == "ИП Смирнова А. В."
    assert record.director.inn == "500100000015"
    assert record.okved_main == ("47.71", "Торговля")
