"""Песочница: тестовые компании, которые может добавить любой зарегистрированный пользователь.

Для ИНН из `SANDBOX` руководитель в ЕГРЮЛ — тот, кто спрашивает (`claimant_*` в запросе
`/egrul/{inn}`), остальные данные — копия профиля персоны (README, «Демо-учётки»), поэтому решение
по заявке такое же, как у персоны. Реальный реестр параметры claimant_* игнорирует — это
упрощение симулятора, описано в README. Все ООО: ИП — это сам человек (ИНН ИП = его ИНН ФЛ),
чужой ИП заявителю принадлежать не может.
"""

from dataclasses import replace
from datetime import date

from simulator import personas
from simulator.profiles import Profile

DEFAULT_DIRECTOR = ("Тестов Тест Тестович", "770000000156")

# ИНН (префикс 99, валидная контрольная сумма) → (ИНН персоны-образца, сценарий)
SANDBOX: dict[str, tuple[str, str]] = {
    "9900000017": ("770700000190", "одобрение"),  # как идеальный ИП Игоря
    "9900000024": ("7701234560", "контрпредложение"),  # «Северный ветер»
    "9900000031": ("7801002002", "мягкий отказ"),  # бизнесу 4 месяца
    "9900000049": ("5403004007", "ручной разбор"),  # просрочка в прошлом
    "9900000056": ("6605006009", "банкротство"),  # «Закат»
    "9900000063": ("500100000015", "нужна выписка"),  # обороты в другом банке
}


def find(
    inn: str, today: date, claimant: tuple[str, str] | None = None
) -> Profile | None:
    entry = SANDBOX.get(inn)
    if entry is None:
        return None
    source_inn, scenario = entry
    base = personas.find(source_inn, today)
    assert base is not None, source_inn
    fio, fl_inn = claimant or DEFAULT_DIRECTOR
    return replace(
        base,
        inn=inn,
        name=f"«Тест — {scenario}»",
        legal_form="ООО",
        director_fio=fio,
        director_inn=fl_inn,
        founders=[(fio, fl_inn, 100.0)],
        # номера сделок и производств уникальны в реестрах — у копии свои
        credits=[replace(c, deal_uid=f"{c.deal_uid[:-10]}{inn}") for c in base.credits],
        proceedings=[replace(p, number=f"{p.number}-{inn}") for p in base.proceedings],
        bankruptcy=[
            replace(b, case_number=f"{b.case_number}-{inn[-2:]}")
            for b in base.bankruptcy
        ],
    )
