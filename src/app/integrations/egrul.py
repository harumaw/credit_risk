"""ЕГРЮЛ / ЕГРИП: карточка компании, ОКВЭД, руководитель, учредители."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.enums import CompanyStatus, DataSource
from app.integrations.base import Fetched, SourceClient, SourceNotFoundError, parse_date

_STATUSES = {
    "Действующее": CompanyStatus.ACTIVE,
    "В процессе реорганизации": CompanyStatus.REORGANIZING,
    "В стадии ликвидации": CompanyStatus.LIQUIDATING,
    "Ликвидировано": CompanyStatus.LIQUIDATED,
    "Прекращено": CompanyStatus.LIQUIDATED,
    "Банкротство": CompanyStatus.BANKRUPT,
}


@dataclass(frozen=True)
class Person:
    full_name: str
    inn: str | None
    share_pct: Decimal | None = None


@dataclass(frozen=True)
class EgrulRecord:
    inn: str
    is_ip: bool
    ogrn: str | None
    kpp: str | None
    full_name: str
    short_name: str
    legal_form: str
    registration_date: date | None
    status: CompanyStatus
    region_code: str | None
    address: str | None
    okved_main: tuple[str, str] | None
    okved_extra: list[tuple[str, str]] = field(default_factory=list)
    director: Person | None = None
    founders: list[Person] = field(default_factory=list)


def _okved(item: dict[str, Any] | None) -> tuple[str, str] | None:
    return (item["Код"], item["Текст"]) if item else None


def _initials(fio: str) -> str:
    surname, *rest = fio.split()
    return " ".join([surname, *(f"{part[0]}." for part in rest)])


def _status(value: str | None) -> CompanyStatus:
    return _STATUSES.get(value or "", CompanyStatus.ACTIVE)


def _parse_ip(ip: dict[str, Any]) -> EgrulRecord:
    fio = ip["ФИОПолн"]
    address = ip.get("Адрес") or {}
    return EgrulRecord(
        inn=ip["ИННФЛ"],
        is_ip=True,
        ogrn=ip.get("ОГРНИП"),
        kpp=None,
        full_name=f"Индивидуальный предприниматель {fio}",
        short_name=f"ИП {_initials(fio)}",
        legal_form="ИП",
        registration_date=parse_date(ip.get("ДатаРег")),
        status=_status(ip.get("Статус")),
        region_code=address.get("КодРегион"),
        address=address.get("АдресПолн"),
        okved_main=_okved(ip.get("ОснВидДеят")),
        okved_extra=[_okved(o) for o in ip.get("ДопВидДеят", [])],
        director=Person(full_name=fio, inn=ip["ИННФЛ"]),  # ИП сам себе руководитель
    )


def _parse_ul(ul: dict[str, Any]) -> EgrulRecord:
    head = ul.get("Руководитель")
    address = ul.get("Адрес") or {}
    founders = [
        Person(
            full_name=f["УчрФЛ"]["ФИОПолн"],
            inn=f["УчрФЛ"].get("ИННФЛ"),
            share_pct=Decimal(str(f["Процент"])) if f.get("Процент") else None,
        )
        for f in ul.get("Учредители", [])
        if "УчрФЛ" in f
    ]
    return EgrulRecord(
        inn=ul["ИНН"],
        is_ip=False,
        ogrn=ul.get("ОГРН"),
        kpp=ul.get("КПП"),
        full_name=ul["НаимПолнЮЛ"],
        short_name=ul.get("НаимСокрЮЛ") or ul["НаимПолнЮЛ"],
        legal_form=ul.get("ОПФ", ""),
        registration_date=parse_date(ul.get("ДатаРег")),
        status=_status(ul.get("Статус")),
        region_code=address.get("КодРегион"),
        address=address.get("АдресПолн"),
        okved_main=_okved(ul.get("ОснВидДеят")),
        okved_extra=[_okved(o) for o in ul.get("ДопВидДеят", [])],
        director=Person(full_name=head["ФИОПолн"], inn=head.get("ИННФЛ"))
        if head
        else None,
        founders=founders,
    )


def parse(raw: dict[str, Any]) -> EgrulRecord:
    items = raw.get("items") or []
    if not items:
        raise SourceNotFoundError("ЕГРЮЛ: пустой ответ")
    item = items[0]
    return _parse_ip(item["ИП"]) if "ИП" in item else _parse_ul(item["ЮЛ"])


class EgrulClient(SourceClient):
    source = DataSource.FNS_EGRUL

    async def fetch(self, inn: str) -> Fetched[EgrulRecord]:
        raw = await self.get_json(f"/egrul/{inn}")
        return Fetched(raw, parse(raw))
