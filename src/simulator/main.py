"""Симулятор внешних источников по ИНН: ЕГРЮЛ/ЕГРИП, ФНС, РМСП, ФССП, ЕФРСБ, ЗСК ЦБ, БКИ, АБС банка.

Отдельный HTTP-сервис без БД. Формат ответов похож на реальные API, чтобы при подключении
настоящего источника менялся только URL и адаптер в `app/integrations/`.
"""

import re
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException

from simulator import personas, sandbox
from simulator.profiles import (
    OWN_BANK,
    OWN_BANK_BIK,
    Profile,
    add_months,
    generate,
    monthly_turnovers,
    payment_string,
)

app = FastAPI(title="Симулятор источников")

_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_W11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_ZSK_NAMES = {
    "green": "Низкий уровень риска",
    "yellow": "Средний уровень риска",
    "red": "Высокий уровень риска",
}


def _check(digits: list[int], weights: tuple[int, ...]) -> int:
    return sum(d * w for d, w in zip(digits, weights)) % 11 % 10


def _valid_inn(inn: str) -> bool:
    if not re.fullmatch(r"\d{10}|\d{12}", inn):
        return False
    d = [int(c) for c in inn]
    if len(d) == 10:
        return _check(d[:9], _W10) == d[9]
    return _check(d[:10], _W11) == d[10] and _check(d[:11], _W12) == d[11]


MSK = timezone(timedelta(hours=3))


def _today() -> date:
    return datetime.now(MSK).date()


def _profile(inn: str, claimant: tuple[str, str] | None = None) -> Profile:
    if not _valid_inn(inn):
        raise HTTPException(status_code=400, detail="Некорректный ИНН")
    today = _today()
    return (
        sandbox.find(inn, today, claimant)
        or personas.find(inn, today)
        or generate(inn, today)
    )


def _okved(code_name: tuple[str, str]) -> dict:
    return {"Код": code_name[0], "Текст": code_name[1]}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/egrul/{inn}")
async def egrul(
    inn: str, claimant_inn: str | None = None, claimant_name: str | None = None
) -> dict:
    """Выписка ЕГРЮЛ (10 цифр) или ЕГРИП (12 цифр).

    claimant_* — кто спрашивает; учитываются только для компаний песочницы (`sandbox.py`).
    """
    claimant = (claimant_name, claimant_inn) if claimant_inn and claimant_name else None
    p = _profile(inn, claimant)
    address = {"КодРегион": p.region, "АдресПолн": p.address}
    if p.is_ip:
        record = {
            "ИП": {
                "ФИОПолн": p.name,
                "ИННФЛ": p.inn,
                "ОГРНИП": p.ogrn,
                "ДатаРег": p.reg_date.isoformat(),
                "Статус": p.status,
                "Адрес": address,
                "ОснВидДеят": _okved(p.okved_main),
                "ДопВидДеят": [_okved(o) for o in p.okved_extra],
            }
        }
    else:
        record = {
            "ЮЛ": {
                "ИНН": p.inn,
                "КПП": p.kpp,
                "ОГРН": p.ogrn,
                "ДатаРег": p.reg_date.isoformat(),
                "НаимСокрЮЛ": f"{p.legal_form} {p.name}",
                "НаимПолнЮЛ": f"ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ {p.name.upper()}",
                "ОПФ": p.legal_form,
                "Статус": p.status,
                "Адрес": address,
                "ОснВидДеят": _okved(p.okved_main),
                "ДопВидДеят": [_okved(o) for o in p.okved_extra],
                "Руководитель": {
                    "ФИОПолн": p.director_fio,
                    "ИННФЛ": p.director_inn,
                    "Должн": "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР",
                },
                "Учредители": [
                    {"УчрФЛ": {"ФИОПолн": fio, "ИННФЛ": fl_inn}, "Процент": share}
                    for fio, fl_inn, share in p.founders
                ],
            }
        }
    return {"items": [record]}


@app.get("/fns/{inn}")
async def fns(inn: str) -> dict:
    """Налоговый режим и задолженность перед бюджетом."""
    p = _profile(inn)
    return {
        "ИНН": p.inn,
        "ДатаСведений": _today().isoformat(),
        "НалогРежим": p.tax_regime,
        "Задолженность": {
            "Недоимка": p.tax_debt,
            "Пени": p.penalties,
            "Штрафы": p.fines,
        },
    }


@app.get("/rmsp/{inn}")
async def rmsp(inn: str) -> dict:
    """Реестр МСП: категория и среднесписочная численность."""
    p = _profile(inn)
    if p.msp_category is None:
        raise HTTPException(status_code=404, detail="Нет в реестре МСП")
    return {"ИНН": p.inn, "Категория": p.msp_category, "ССЧР": p.headcount}


@app.get("/fssp/{inn}")
async def fssp(inn: str) -> dict:
    """Исполнительные производства."""
    p = _profile(inn)
    return {
        "result": [
            {
                "exe_production": pr.number,
                "date_start": pr.opened.isoformat(),
                "subject": pr.subject,
                "amount": pr.amount,
                "debt_remaining": pr.remaining,
                "ip_end": pr.closed.isoformat() if pr.closed else None,
            }
            for pr in p.proceedings
        ]
    }


@app.get("/efrsb/{inn}")
async def efrsb(inn: str) -> dict:
    """Сообщения о банкротстве (Федресурс)."""
    p = _profile(inn)
    return {
        "messages": [
            {
                "type": m.kind,
                "publish_date": m.published.isoformat(),
                "case_number": m.case_number,
                "is_debtor_initiated": m.self_initiated,
            }
            for m in p.bankruptcy
        ]
    }


@app.get("/zsk/{inn}")
async def zsk(inn: str) -> dict:
    """Платформа ЦБ «Знай своего клиента»."""
    p = _profile(inn)
    return {
        "inn": p.inn,
        "zone": p.zsk_zone,
        "zone_name": _ZSK_NAMES[p.zsk_zone],
        "assigned": (p.reg_date + timedelta(days=30)).isoformat(),
        "as_of": _today().isoformat(),
    }


def _schedule(payment: int, day: int, today: date, maturity: date) -> list[dict]:
    rows = []
    month = today.replace(day=1)
    for i in range(12):
        due = add_months(month, i).replace(day=day)
        if due < today or due > maturity:
            continue
        rows.append({"date": due.isoformat(), "amount": payment})
    return rows


@app.get("/bki/{inn}")
async def bki(inn: str) -> dict:
    """Кредитный отчёт: договоры, остатки, просрочки, ближайшие платежи."""
    p = _profile(inn)
    today = _today()
    return {
        "subject": {"inn": p.inn},
        "report_date": today.isoformat(),
        "accounts": [
            {
                "uid": c.deal_uid,
                "creditor": c.lender,
                "type": c.kind,
                "limit": c.limit,
                "currency": "RUB",
                "open_date": c.opened.isoformat(),
                "close_date_plan": c.maturity.isoformat(),
                "close_date_fact": c.closed.isoformat() if c.closed else None,
                "balance": c.outstanding,
                "overdue": c.overdue,
                "max_dpd": c.max_dpd,
                "payment_string": payment_string(c, today),
                "payment_schedule": []
                if c.closed
                else _schedule(c.monthly_payment, c.payment_day, today, c.maturity),
            }
            for c in p.credits
        ],
    }


@app.get("/abs/{inn}/turnovers")
async def abs_turnovers(inn: str) -> dict:
    """АБС банка: счета клиента в нашем банке и обороты/остатки по месяцам."""
    p = _profile(inn)
    if not p.own_bank_client or p.turnovers is None:
        return {
            "inn": p.inn,
            "client": False,
            "bank": OWN_BANK,
            "accounts": [],
            "months": [],
        }
    account = f"{'40802' if p.is_ip else '40702'}810•••••{p.inn[-4:]}"
    return {
        "inn": p.inn,
        "client": True,
        "bank": OWN_BANK,
        "accounts": [
            {
                "number_masked": account,
                "bik": OWN_BANK_BIK,
                "currency": "RUB",
                "opened": max(p.reg_date, date(2015, 1, 1)).isoformat(),
            }
        ],
        "months": [
            {
                "account": account,
                "month": row["month"].strftime("%Y-%m"),
                "credit_turnover": row["inflow"],
                "debit_turnover": row["outflow"],
                "closing_balance": row["closing_balance"],
                "tx_count": row["tx_count"],
                "counterparties": row["counterparties"],
            }
            for row in monthly_turnovers(p, _today())
        ],
    }
