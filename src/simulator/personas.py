"""Фиксированные персоны для демо и тестов (CLAUDE.md §9). Все данные синтетические.

Руководитель персоны совпадает с демо-учёткой из `app/seed.py` (ФИО + ИНН ФЛ) —
только так компанию можно добавить в кабинет.
"""

from datetime import date, timedelta

from simulator.profiles import (
    OKVED_NAMES,
    OWN_BANK,
    BankruptcyMessage,
    Credit,
    Proceeding,
    Profile,
    Turnovers,
    add_months,
)

ANNA = ("Смирнова Анна Викторовна", "500100000015")
IGOR = ("Кузнецов Игорь Петрович", "770700000190")
OLGA = ("Морозова Ольга Сергеевна", "780100000237")
DMITRY = ("Волков Дмитрий Андреевич", "540300000392")
SERGEY = ("Лебедев Сергей Николаевич", "660500000444")


def _okved(code: str) -> tuple[str, str]:
    return code, OKVED_NAMES[code]


def _personas(today: date) -> list[Profile]:
    month = today.replace(day=1)
    return [
        # ООО с высокой нагрузкой: клиент банка, 2 кредита, платежи 100 000/мес → контрпредложение
        Profile(
            inn="7701234560",
            name="«Северный ветер»",
            reg_date=date(2019, 4, 15),
            region="77",
            address="г. Москва, ул. Ветреная, д. 7",
            okved_main=_okved("46.90"),
            okved_extra=[_okved("47.91"), _okved("52.29")],
            director_fio=ANNA[0],
            director_inn=ANNA[1],
            founders=[(ANNA[0], ANNA[1], 100.0)],
            tax_regime="УСН доходы",
            msp_category="Малое предприятие",
            headcount=24,
            credits=[
                Credit(
                    deal_uid="a1b2c3d4-0000-4000-8000-000000000001",
                    lender=OWN_BANK,
                    kind="Кредит",
                    limit=2_000_000,
                    outstanding=1_240_000,
                    monthly_payment=68_400,
                    opened=date(2025, 4, 25),
                    maturity=date(2028, 4, 25),
                    payment_day=25,
                ),
                Credit(
                    deal_uid="a1b2c3d4-0000-4000-8000-000000000002",
                    lender="ООО «Лизинг-Пример»",
                    kind="Лизинг",
                    limit=1_400_000,
                    outstanding=860_000,
                    monthly_payment=31_600,
                    opened=date(2024, 11, 2),
                    maturity=date(2028, 11, 2),
                    payment_day=2,
                ),
            ],
            turnovers=Turnovers(
                avg_inflow=4_050_000, net_income=450_000, avg_balance=1_900_000
            ),
        ),
        # Та же владелица — ИП на патенте, счёт в другом банке → дозапрос выписки
        Profile(
            inn=ANNA[1],
            name=ANNA[0],
            legal_form="ИП",
            reg_date=date(2022, 6, 1),
            region="50",
            address="Московская обл., г. Пример, ул. Садовая, д. 3",
            okved_main=_okved("47.71"),
            okved_extra=[_okved("47.19")],
            director_fio=ANNA[0],
            director_inn=ANNA[1],
            tax_regime="ПСН",
            msp_category="Микропредприятие",
            headcount=2,
            own_bank_client=False,
            turnovers=None,
        ),
        # Ещё одна компания Анны — её добавляют через «Добавить по ИНН»
        Profile(
            inn="7705551232",
            name="«Ромашка»",
            reg_date=date(2021, 3, 10),
            region="77",
            address="г. Москва, пр-т Цветочный, д. 12",
            okved_main=_okved("56.10"),
            director_fio=ANNA[0],
            director_inn=ANNA[1],
            founders=[(ANNA[0], ANNA[1], 100.0)],
            tax_regime="УСН доходы минус расходы",
            msp_category="Микропредприятие",
            headcount=9,
            turnovers=Turnovers(
                avg_inflow=1_300_000, net_income=160_000, avg_balance=420_000
            ),
        ),
        # Идеальный ИП: давно работает, клиент банка, долгов нет → автоодобрение
        Profile(
            inn=IGOR[1],
            name=IGOR[0],
            legal_form="ИП",
            reg_date=date(2018, 2, 20),
            region="77",
            address="г. Москва, ул. Мастеровая, д. 21",
            okved_main=_okved("45.20"),
            okved_extra=[_okved("43.21")],
            director_fio=IGOR[0],
            director_inn=IGOR[1],
            tax_regime="УСН доходы",
            msp_category="Микропредприятие",
            headcount=6,
            turnovers=Turnovers(
                avg_inflow=2_200_000, net_income=380_000, avg_balance=900_000
            ),
        ),
        # Молодой бизнес: 4 месяца → мягкий отказ
        Profile(
            inn="7801002002",
            name="«Новый старт»",
            reg_date=add_months(month, -4) + timedelta(days=4),
            region="78",
            address="г. Санкт-Петербург, ул. Стартовая, д. 1",
            okved_main=_okved("62.01"),
            director_fio=OLGA[0],
            director_inn=OLGA[1],
            founders=[(OLGA[0], OLGA[1], 100.0)],
            tax_regime="УСН доходы",
            msp_category="Микропредприятие",
            headcount=3,
            turnovers=Turnovers(
                avg_inflow=600_000, net_income=90_000, avg_balance=250_000
            ),
        ),
        # Просрочка в прошлом: закрытый кредит с max DPD 45 → ручной разбор
        Profile(
            inn="5403004007",
            name="«Вектор»",
            reg_date=date(2016, 9, 5),
            region="54",
            address="г. Новосибирск, ул. Прямая, д. 40",
            okved_main=_okved("49.41"),
            director_fio=DMITRY[0],
            director_inn=DMITRY[1],
            founders=[(DMITRY[0], DMITRY[1], 100.0)],
            tax_regime="ОСН",
            msp_category="Малое предприятие",
            headcount=31,
            credits=[
                Credit(
                    deal_uid="a1b2c3d4-0000-4000-8000-000000000003",
                    lender="Банк «Образец»",
                    kind="Кредит",
                    limit=3_000_000,
                    outstanding=0,
                    monthly_payment=0,
                    opened=date(2021, 3, 1),
                    maturity=date(2024, 3, 1),
                    closed=date(2024, 2, 20),
                    max_dpd=45,
                )
            ],
            turnovers=Turnovers(
                avg_inflow=5_200_000, net_income=520_000, avg_balance=1_400_000
            ),
        ),
        # Банкротство: процедура наблюдения, приставы, налоговый долг → жёсткий отказ
        Profile(
            inn="6605006009",
            name="«Закат»",
            status="Банкротство",
            reg_date=date(2015, 1, 12),
            region="66",
            address="г. Екатеринбург, ул. Закатная, д. 9",
            okved_main=_okved("41.20"),
            director_fio=SERGEY[0],
            director_inn=SERGEY[1],
            founders=[(SERGEY[0], SERGEY[1], 100.0)],
            tax_regime="ОСН",
            tax_debt=1_850_000,
            penalties=240_000,
            fines=50_000,
            msp_category="Малое предприятие",
            headcount=12,
            proceedings=[
                Proceeding(
                    number="81234/26/66001-ИП",
                    opened=today - timedelta(days=200),
                    subject="Налоги и сборы",
                    amount=1_200_000,
                    remaining=1_200_000,
                )
            ],
            bankruptcy=[
                BankruptcyMessage(
                    case_number="А60-12345/2026",
                    kind="Сообщение о введении наблюдения",
                    published=today - timedelta(days=60),
                )
            ],
            zsk_zone="yellow",
            own_bank_client=False,
            turnovers=None,
        ),
    ]


def find(inn: str, today: date) -> Profile | None:
    return next((p for p in _personas(today) if p.inn == inn), None)
