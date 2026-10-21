"""Синтетический датасет МСБ для скоринга: КИ из соревнования scoring_maps + сгенерированный бизнес-профиль.

Что берём из исходника (папка scoring_maps/data_for_competition):
  * кредитную историю: строки `rn` одного `id` → обязательства компании в БКИ,
    помесячные статусы `enc_paym_0..24` → строка платёжной дисциплины (0 — самый свежий месяц);
  * таргет `flag` (дефолт по новому кредиту) — как есть;
  * порядок заявок: `id` растёт со временем → дата заявки (as_of_date), нужна для OOT-проверки.

Что генерируем (детерминированно, seed): компанию-заёмщика (ИНН/ОГРН, ОПФ, ОКВЭД, регион,
возраст, категория МСП, численность, режим налогообложения), обороты по счёту за 12 мес.,
налоговую задолженность, исполнительные производства ФССП, зону ЗСК, банкротство.
Бизнес-признаки зависят от скрытого риска r = BETA·flag + N(0,1): у дефолтных компаний они
в среднем хуже, но распределения сильно перекрываются — как в жизни.

Запуск (из корня проекта):
    python ml/synth/build_dataset.py --source ../scoring_maps/data_for_competition --out ml/data/synthetic_v1

Без pyarrow parquet читается встроенным `parquet_lite`.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

try:  # pragma: no cover - зависит от окружения
    import pyarrow  # noqa: F401

    def read_parquet(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
        return pd.read_parquet(path, columns=columns)

except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from parquet_lite import read_parquet  # type: ignore[no-redef]

DATASET_CODE = "synthetic_v1"
SEED = 2026
N_COMPANIES = 40_000
BAD_SHARE = 0.05  # у МСБ дефолтность выше, чем у розницы (3,5% в исходнике) — добираем дефолтных
BETA = 1.15  # сила связи бизнес-признаков с дефолтом
FIRST_DATE = date(2023, 1, 1)  # самая ранняя заявка
LAST_DATE = date(
    2025, 9, 30
)  # самая поздняя: 12 мес. окна наблюдения дефолта до сегодня
MAX_SOURCE_ID = 3_000_000
PAYM_COLS = [f"enc_paym_{i}" for i in range(25)]
SHIFTED_PAYM = (11, 20, 24)  # в этих колонках коды сдвинуты на +1 (1..4 вместо 0..3)
STATUS_CHARS = np.array(
    ["0", "1", "2", "-"]
)  # 0 — без просрочки, 1 — до 30 дн., 2 — 30+, - нет данных

OWN_BANK = "Наш банк"
OWN_BANK_BIK = "049999001"
OTHER_BANKS = [
    ("Банк «Пример»", "044525901"),
    ("Банк «Образец»", "044525902"),
    ("Банк «Северный»", "044030903"),
    ("Банк «Волга»", "042202904"),
]
LENDERS = [
    OWN_BANK,
    "Банк «Пример»",
    "Банк «Образец»",
    "Банк «Северный»",
    "ООО «Лизинг-Пример»",
    "МФО «Быстрые деньги»",
]

# Секции ОКВЭД: (код, название, доля в выборке, множитель риска, амплитуда сезонности)
OKVED = [
    ("46.90", "G", "Торговля оптовая неспециализированная", 0.16, 1.05, 0.10),
    (
        "47.19",
        "G",
        "Торговля розничная прочая в неспециализированных магазинах",
        0.12,
        1.20,
        0.18,
    ),
    ("47.91", "G", "Торговля розничная через Интернет", 0.07, 1.10, 0.20),
    (
        "56.10",
        "I",
        "Деятельность ресторанов и услуги по доставке продуктов питания",
        0.07,
        1.45,
        0.15,
    ),
    ("41.20", "F", "Строительство жилых и нежилых зданий", 0.08, 1.60, 0.25),
    ("43.21", "F", "Производство электромонтажных работ", 0.05, 1.35, 0.20),
    (
        "49.41",
        "H",
        "Деятельность автомобильного грузового транспорта",
        0.09,
        1.15,
        0.08,
    ),
    (
        "52.29",
        "H",
        "Деятельность вспомогательная, связанная с перевозками",
        0.04,
        1.00,
        0.08,
    ),
    (
        "62.01",
        "J",
        "Разработка компьютерного программного обеспечения",
        0.07,
        0.65,
        0.05,
    ),
    ("68.20", "L", "Аренда и управление недвижимым имуществом", 0.07, 0.70, 0.03),
    ("73.11", "M", "Деятельность рекламных агентств", 0.04, 1.05, 0.10),
    (
        "10.71",
        "C",
        "Производство хлеба и мучных кондитерских изделий",
        0.05,
        0.90,
        0.06,
    ),
    (
        "45.20",
        "G",
        "Техническое обслуживание и ремонт автотранспортных средств",
        0.05,
        0.95,
        0.12,
    ),
    (
        "96.02",
        "S",
        "Предоставление услуг парикмахерскими и салонами красоты",
        0.04,
        1.10,
        0.06,
    ),
]
OKVED_SECTION_NAMES = {
    "C": "Обрабатывающие производства",
    "F": "Строительство",
    "G": "Торговля и ремонт автотранспорта",
    "H": "Транспортировка и хранение",
    "I": "Гостиницы и общепит",
    "J": "Информация и связь",
    "L": "Операции с недвижимостью",
    "M": "Профессиональная деятельность",
    "S": "Прочие услуги",
}
# Регионы: (код, город для адреса, доля, множитель риска)
REGIONS = [
    ("77", "г. Москва", 0.24, 0.90),
    ("78", "г. Санкт-Петербург", 0.12, 0.90),
    ("50", "Московская обл., г. Химки", 0.11, 1.00),
    ("66", "г. Екатеринбург", 0.07, 1.05),
    ("54", "г. Новосибирск", 0.06, 1.05),
    ("16", "г. Казань", 0.06, 0.95),
    ("23", "г. Краснодар", 0.07, 1.15),
    ("52", "г. Нижний Новгород", 0.05, 1.00),
    ("63", "г. Самара", 0.05, 1.10),
    ("02", "г. Уфа", 0.05, 1.10),
    ("05", "г. Махачкала", 0.04, 1.45),
    ("39", "г. Калининград", 0.04, 1.05),
    ("25", "г. Владивосток", 0.04, 1.20),
]
ORG_WORDS_1 = [
    "Север",
    "Юг",
    "Восток",
    "Альфа",
    "Гранит",
    "Кедр",
    "Орион",
    "Меридиан",
    "Ладога",
    "Вектор",
    "Сфера",
    "Полюс",
    "Импульс",
    "Акцент",
    "Байкал",
    "Волна",
    "Стандарт",
    "Профи",
    "Контур",
    "Мега",
]
ORG_WORDS_2 = [
    "Строй",
    "Трейд",
    "Логистик",
    "Сервис",
    "Пром",
    "Маркет",
    "Групп",
    "Тех",
    "Снаб",
    "Инвест",
    "Авто",
    "Фуд",
    "Софт",
    "Мед",
    "Агро",
    "Дизайн",
    "Транс",
    "Хаус",
    "Лайн",
    "Плюс",
]
SURNAMES_M = [
    "Иванов",
    "Петров",
    "Сидоров",
    "Козлов",
    "Новиков",
    "Морозов",
    "Соколов",
    "Павлов",
    "Фёдоров",
    "Егоров",
    "Орлов",
    "Макаров",
    "Зайцев",
    "Николаев",
    "Белов",
    "Тарасов",
    "Гусев",
    "Титов",
]
FIRST_M = [
    "Алексей",
    "Михаил",
    "Андрей",
    "Николай",
    "Павел",
    "Юрий",
    "Денис",
    "Артём",
    "Олег",
    "Роман",
]
FIRST_F = [
    "Анна",
    "Елена",
    "Мария",
    "Ольга",
    "Ирина",
    "Наталья",
    "Юлия",
    "Татьяна",
    "Светлана",
    "Ксения",
]
PATR = [
    "Александров",
    "Сергеев",
    "Игорев",
    "Олегов",
    "Викторов",
    "Петров",
    "Николаев",
    "Андреев",
]
STREETS = [
    "ул. Ленина",
    "ул. Мира",
    "пр-т Победы",
    "ул. Садовая",
    "ул. Заводская",
    "ул. Центральная",
    "ул. Строителей",
    "ул. Гагарина",
    "наб. Речная",
    "ул. Полевая",
]

FSSP_SUBJECTS = [
    "Налоги и сборы",
    "Задолженность по договору поставки",
    "Штраф ГИБДД",
    "Задолженность по аренде",
    "Взыскание по решению арбитражного суда",
]


# --------------------------------------------------------------------------- utils


def add_months(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    y, m = divmod(idx, 12)
    day = min(
        d.day, [31, 29 if y % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m]
    )
    return date(y, m + 1, day)


def month_start(d: date) -> date:
    return d.replace(day=1)


def inn_ul(region: str, n: int) -> str:
    """10-значный ИНН ЮЛ с контрольной цифрой. 3–4 цифры = 99 — так синтетика не пересекается с персонами."""
    body = f"{region}99{n % 100_000:05d}{(n // 100_000) % 10}"
    w = (2, 4, 10, 3, 5, 9, 4, 6, 8)
    return body + str(sum(int(a) * b for a, b in zip(body, w)) % 11 % 10)


def inn_fl(region: str, n: int) -> str:
    body = f"{region}99{n % 1_000_000:06d}"
    w11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    body += str(sum(int(a) * b for a, b in zip(body, w11)) % 11 % 10)
    w12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    return body + str(sum(int(a) * b for a, b in zip(body, w12)) % 11 % 10)


def ogrn(is_ip: bool, reg: date, region: str, n: int) -> str:
    if is_ip:
        body = f"3{reg:%y}{region}99{n:07d}"  # 14 цифр
        return body + str(int(body) % 13 % 10)
    body = f"1{reg:%y}{region}99{n:05d}"  # 12 цифр
    return body + str(int(body) % 11 % 10)


def annuity(principal: float, rate_year: float, months: int) -> float:
    r = rate_year / 12
    return principal * r / (1 - (1 + r) ** -max(months, 1))


# --------------------------------------------------------------------------- источник


def load_source(
    source: Path, n_companies: int, bad_share: float, seed: int
) -> pd.DataFrame:
    target = pd.read_csv(source / "train_target.csv")
    n_bad = round(n_companies * bad_share)
    bads = target[target.flag == 1].sample(n_bad, random_state=seed)
    goods = target[target.flag == 0].sample(n_companies - n_bad, random_state=seed)
    sample = pd.concat([bads, goods]).sort_values("id")
    ids = set(sample.id)
    parts = []
    files = sorted(
        (source / "train_data").glob("train_data_*.pq"),
        key=lambda f: int(f.stem.rsplit("_", 1)[1]),
    )
    if not files:
        raise FileNotFoundError(f"нет train_data_*.pq в {source / 'train_data'}")
    for f in files:
        part = read_parquet(f)
        part = part[part.id.isin(ids)]
        parts.append(part.astype({c: "int16" for c in part.columns if c != "id"}))
        print(f"  {f.name}: {len(part):,} строк КИ")
    raw = pd.concat(parts, ignore_index=True).merge(sample, on="id")
    for j in SHIFTED_PAYM:
        raw[f"enc_paym_{j}"] -= 1
    return raw.sort_values(["id", "rn"]).reset_index(drop=True)


def decode_order(
    raw: pd.DataFrame, code_col: str, observed_months: np.ndarray
) -> dict[int, int]:
    """Коды pre_since_opened перемешаны: восстанавливаем порядок по наблюдаемой длине истории."""
    means = (
        pd.Series(observed_months).groupby(raw[code_col].values).mean().sort_values()
    )
    return {int(code): rank for rank, code in enumerate(means.index)}


# --------------------------------------------------------------------------- генерация


def build(raw: pd.DataFrame, seed: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    per_id = raw.groupby("id", sort=True).flag.first()
    n = len(per_id)
    ids = per_id.index.to_numpy()
    flag = per_id.to_numpy()
    r = BETA * flag + rng.normal(0, 1, n)  # скрытый бизнес-риск

    # Дата заявки: id упорядочены по времени
    span = (LAST_DATE - FIRST_DATE).days
    as_of = [
        FIRST_DATE.fromordinal(FIRST_DATE.toordinal() + int(i / MAX_SOURCE_ID * span))
        for i in ids
    ]

    # ОПФ, размер
    is_ip = rng.random(n) < 0.42
    msp = np.where(
        is_ip,
        np.where(rng.random(n) < 0.9, "micro", "small"),
        rng.choice(["micro", "small", "medium"], n, p=[0.55, 0.36, 0.09]),
    )
    headcount = np.where(
        msp == "micro",
        rng.integers(1, 16, n),
        np.where(msp == "small", rng.integers(16, 101, n), rng.integers(101, 251, n)),
    )
    # Возраст бизнеса: у рискованных моложе
    age_months = (
        np.clip(np.exp(rng.normal(math.log(52), 0.8, n) - 0.30 * r), 6, 300)
        .round()
        .astype(int)
    )
    # ~17% — молодой бизнес (2–18 мес.): среди дефолтных таких больше
    startup = rng.random(n) < 1 / (1 + np.exp(-(-1.75 + 0.45 * r)))
    age_months = np.where(startup, rng.integers(2, 19, n), age_months)
    # Драйверы риска различаются по типу бизнеса — поэтому сегментные модели имеют смысл:
    # молодой — волатильность и подушка остатков, а резкий рост оборотов там скорее риск;
    # ИП/микро — налоги, ФССП, волатильность; малые/средние ЮЛ — маржа, падение оборотов, нагрузка.
    group = np.where(age_months < 12, 0, np.where(is_ip | (msp == "micro"), 1, 2))
    coef = {  # new_business, ip_micro, sme  (+ — признак растёт с риском, − — падает)
        "cv": np.array([0.85, 0.55, 0.0]),
        "trend": np.array(
            [-0.12, 0.0, 0.22]
        ),  # trend = … − coef·r: у молодых рискованных рост выше
        "margin": np.array([0.0, 0.012, 0.065]),
        "bal": np.array([0.55, 0.08, 0.30]),
        "tax": np.array([0.40, 1.40, 0.40]),
        "fssp": np.array([0.30, 1.30, 0.20]),
        "util": np.array([0.0, 0.04, 0.30]),
    }
    eff = {k: v[group] for k, v in coef.items()}
    # ОКВЭД и регион: доля × (множитель риска для дефолтных)
    ok_share = np.array([o[3] for o in OKVED])
    ok_risk = np.array([o[4] for o in OKVED])
    reg_share = np.array([x[2] for x in REGIONS])
    reg_risk = np.array([x[3] for x in REGIONS])

    def pick(share, risk, mult):
        p_good = share / share.sum()
        p_bad = share * risk**2.2
        p_bad /= p_bad.sum()
        out = np.empty(n, dtype=int)
        for f_val, p in ((0, p_good), (1, p_bad)):
            m = mult == f_val
            out[m] = rng.choice(len(share), m.sum(), p=p)
        return out

    ok_idx = pick(ok_share, ok_risk, flag)
    reg_idx = pick(reg_share, reg_risk, flag)

    tax_regime = np.where(
        is_ip,
        np.where(
            flag == 1,  # у проблемных ИП чаще патент: короткий горизонт бизнеса
            rng.choice(
                ["usn_income", "psn", "usn_income_expense", "ausn"],
                n,
                p=[0.35, 0.45, 0.15, 0.05],
            ),
            rng.choice(
                ["usn_income", "psn", "usn_income_expense", "ausn"],
                n,
                p=[0.5, 0.25, 0.2, 0.05],
            ),
        ),
        rng.choice(
            ["usn_income", "usn_income_expense", "osno", "ausn"],
            n,
            p=[0.35, 0.3, 0.32, 0.03],
        ),
    )
    tax_regime = np.where((~is_ip) & (msp == "medium"), "osno", tax_regime)

    # Обороты: средний приход в месяц по размеру, у рискованных ниже и волатильнее
    base_inflow = np.where(
        msp == "micro", 1.6e6, np.where(msp == "small", 9e6, 45e6)
    ) * np.where(is_ip, 0.6, 1.0)
    avg_inflow = base_inflow * np.exp(rng.normal(0, 0.55, n) - 0.12 * r)
    turnover_cv = np.clip(
        0.08 + 0.07 * np.exp(eff["cv"] * r + rng.normal(0, 0.35, n)), 0.04, 0.9
    )
    trend = np.clip(
        rng.normal(0.04, 0.12, n) - eff["trend"] * r, -0.6, 0.6
    )  # рост 2-го полугодия к 1-му
    margin = np.clip(
        rng.normal(0.13, 0.05, n) - eff["margin"] * r, -0.08, 0.4
    )  # чистый поток / приход
    bal_ratio = np.clip(
        np.exp(rng.normal(math.log(0.35), 0.5, n) - eff["bal"] * r), 0.01, 3
    )
    own_bank = rng.random(n) < 0.65

    # Налоги, ФССП, ЗСК, банкротство
    p_tax = 1 / (1 + np.exp(-(-2.8 + eff["tax"] * r)))
    has_tax_debt = rng.random(n) < p_tax
    tax_debt = np.where(
        has_tax_debt, np.round(avg_inflow * np.exp(rng.normal(-3.2, 1.0, n)), -2), 0
    )
    fssp_cnt = rng.poisson(0.12 * np.exp(eff["fssp"] * r))
    zsk = np.where(
        rng.random(n) < 1 / (1 + np.exp(-(-3.6 + 0.8 * r))), "yellow", "green"
    )
    zsk = np.where(rng.random(n) < 0.002 + 0.02 * flag, "red", zsk)
    bankrupt = rng.random(n) < 0.001 + 0.03 * flag * (r > 2)

    companies = []
    okved_rows = []
    fssp_rows = []
    turn_rows = []
    for k in range(n):
        reg_code, city = REGIONS[reg_idx[k]][0], REGIONS[reg_idx[k]][1]
        reg_date = add_months(as_of[k], -int(age_months[k]))
        num = k + 1
        if is_ip[k]:
            female = rng.random() < 0.4
            sur = SURNAMES_M[rng.integers(len(SURNAMES_M))] + ("а" if female else "")
            first = (FIRST_F if female else FIRST_M)[rng.integers(10)]
            patr = PATR[rng.integers(len(PATR))] + ("на" if female else "ич")
            fio = f"{sur} {first} {patr}"
            inn = inn_fl(reg_code, num)
            full_name = f"Индивидуальный предприниматель {fio}"
            short = f"ИП {fio}"
            legal_form = "ИП"
            kpp = None
        else:
            word = ORG_WORDS_1[rng.integers(20)] + ORG_WORDS_2[rng.integers(20)].lower()
            inn = inn_ul(reg_code, num)
            full_name = f"Общество с ограниченной ответственностью «{word}»"
            short = f"ООО «{word}»"
            legal_form = "ООО"
            kpp = f"{inn[:4]}01001"
        code, section = OKVED[ok_idx[k]][0], OKVED[ok_idx[k]][1]
        status = "bankrupt" if bankrupt[k] else "active"
        default_date = (
            add_months(as_of[k], int(rng.integers(2, 13))) if flag[k] else None
        )
        companies.append(
            {
                "company_key": int(ids[k]),
                "inn": inn,
                "ogrn": ogrn(is_ip[k], reg_date, reg_code, num),
                "kpp": kpp,
                "full_name": full_name,
                "short_name": short,
                "legal_form": legal_form,
                "registration_date": reg_date.isoformat(),
                "status": status,
                "region_code": reg_code,
                "legal_address": f"{city}, {STREETS[rng.integers(len(STREETS))]}, д. {rng.integers(1, 150)}",
                "msp_category": msp[k],
                "headcount": int(headcount[k]),
                "tax_regime": tax_regime[k],
                "okved_main": code,
                "okved_section": section,
                "own_bank_client": bool(own_bank[k]),
                "as_of_date": as_of[k].isoformat(),
                "zsk_zone": zsk[k],
                "tax_debt": float(tax_debt[k]),
                "penalties": float(round(tax_debt[k] * rng.uniform(0.05, 0.2), -1)),
                "fines": float(1000 * rng.integers(0, 6) if has_tax_debt[k] else 0),
                "target": int(flag[k]),
                "default_date": default_date.isoformat() if default_date else None,
                "default_trigger": ("bankruptcy" if bankrupt[k] else "dpd_90")
                if flag[k]
                else None,
            }
        )
        okved_rows.append(
            {"company_key": int(ids[k]), "okved_code": code, "is_main": True}
        )
        # ФССП
        for j in range(int(fssp_cnt[k])):
            opened = add_months(as_of[k], -int(rng.integers(1, 36)))
            amount = float(round(avg_inflow[k] * np.exp(rng.normal(-3.5, 1.1)), -2))
            closed = rng.random() < 0.55
            fssp_rows.append(
                {
                    "company_key": int(ids[k]),
                    "ip_number": f"{rng.integers(10000, 99999)}/{opened:%y}/{reg_code}{rng.integers(100, 999)}-ИП-{num}-{j}",
                    "opened_at": opened.isoformat(),
                    "closed_at": add_months(opened, int(rng.integers(1, 8))).isoformat()
                    if closed
                    else None,
                    "subject": FSSP_SUBJECTS[rng.integers(len(FSSP_SUBJECTS))],
                    "amount": amount,
                    "remaining_amount": 0.0 if closed else amount,
                }
            )
        # Обороты за 12 полных месяцев до заявки (не раньше регистрации)
        last = add_months(month_start(as_of[k]), -1)
        season_amp = OKVED[ok_idx[k]][5]
        for i in range(11, -1, -1):
            m = add_months(last, -i)
            if m <= month_start(reg_date):
                continue
            pos = (11 - i) / 11 - 0.5  # -0.5..0.5
            season = 1 + season_amp * math.sin(2 * math.pi * (m.month - 3) / 12)
            inflow = (
                avg_inflow[k]
                * season
                * (1 + trend[k] * pos)
                * math.exp(rng.normal(0, turnover_cv[k]))
            )
            mrg = margin[k] + rng.normal(0, 0.03)
            turn_rows.append(
                {
                    "company_key": int(ids[k]),
                    "month": m.isoformat(),
                    "inflow": round(inflow, 2),
                    "outflow": round(inflow * (1 - mrg), 2),
                    "closing_balance": round(
                        max(
                            avg_inflow[k]
                            * bal_ratio[k]
                            * math.exp(rng.normal(0, 0.25)),
                            0,
                        ),
                        2,
                    ),
                    "tx_count": int(inflow / 30_000) + int(rng.integers(5, 40)),
                    "counterparties_cnt": int(rng.integers(5, 25) + headcount[k] // 3),
                    "is_own_bank": bool(own_bank[k]),
                }
            )
    comp = pd.DataFrame(companies)
    util_level = np.clip(
        rng.normal(0.42 + eff["util"] * r, 0.2), 0.02, 1.0
    )  # утилизация лимитов: у рискованных выше
    # У молодого бизнеса чаще всего ещё нет кредитов на юрлицо: КИ пустая
    no_bki = (age_months < 12) & (rng.random(n) < 0.65)
    obligations = build_obligations(
        raw, comp, base_inflow, age_months, own_bank, util_level, no_bki, rng
    )
    okved_dict = pd.DataFrame(
        [{"code": o[0], "name": o[2], "section": o[1]} for o in OKVED]
    )
    return {
        "companies": comp,
        "company_okved": pd.DataFrame(okved_rows),
        "okved_codes": okved_dict,
        "obligations": obligations,
        "fssp": pd.DataFrame(fssp_rows),
        "turnovers": pd.DataFrame(turn_rows),
    }


def build_obligations(
    raw, comp, base_inflow, age_months, own_bank, util_level, no_bki, rng
) -> pd.DataFrame:
    status = raw[PAYM_COLS].to_numpy()
    observed = (
        np.where(status != 3, np.arange(25), -1).max(axis=1) + 1
    )  # месяцев в истории (≤25)
    since_rank = raw.pre_since_opened.map(
        decode_order(raw, "pre_since_opened", observed)
    ).to_numpy()
    limit_rank = raw.pre_loans_credit_limit.to_numpy()

    key_to_row = {key: i for i, key in enumerate(comp.company_key)}
    rows = []
    for t in range(len(raw)):
        key = int(raw.id.iat[t])
        k = key_to_row[key]
        if no_bki[k]:
            continue
        as_of = date.fromisoformat(comp.as_of_date.iat[k])
        age = int(age_months[k])
        mob = (
            int(observed[t]) if observed[t] < 25 else 25 + int(since_rank[t]) * 2
        )  # месяцев с открытия
        if mob == 0:
            mob = int(since_rank[t] // 4) + 1
        if mob > age:  # кредит старше бизнеса: у молодых компаний истории почти нет
            if rng.random() < 0.85:
                continue
            mob = max(1, age - 1)
        pay = "".join(STATUS_CHARS[status[t, : min(mob, 25)]])
        is_active = bool(raw.fclose_flag.iat[t])
        opened = add_months(as_of, -mob)
        term = int(rng.choice([12, 18, 24, 36, 48, 60]))
        if is_active and mob >= term:
            term = mob + int(rng.integers(6, 25))
        maturity = add_months(opened, term)
        closed = None
        if not is_active:
            closed_m = int(rng.integers(0, max(1, min(mob, 12))))
            closed = add_months(as_of, -closed_m - 1)
            if closed <= opened:
                closed = add_months(opened, 1)
        income = (
            base_inflow[k] * 0.13
        )  # лимит от типичного дохода для размера бизнеса, не от фактического
        limit = round(
            income * (4 + 0.8 * limit_rank[t]) * math.exp(rng.normal(0, 0.45)), -3
        )
        util = min(1.0, max(0.0, util_level[k] * rng.uniform(0.6, 1.4)))
        outstanding = round(limit * util, 2) if is_active else 0.0
        remaining = max(
            1, (maturity.year - as_of.year) * 12 + maturity.month - as_of.month
        )
        monthly = round(annuity(outstanding, 0.2, remaining), 2) if is_active else 0.0
        worst = "2" if "2" in pay else "1" if "1" in pay else "0"
        max_dpd = {
            "0": 0,
            "1": int(rng.integers(1, 30)),
            "2": int(rng.integers(30, 90)),
        }[worst]
        overdue = 0.0
        if is_active and pay[:1] in ("1", "2"):
            overdue = round(monthly * (1 if pay[0] == "1" else 2), 2)
        lender = (
            OWN_BANK
            if own_bank[k] and rng.random() < 0.35
            else LENDERS[1 + int(rng.integers(len(LENDERS) - 1))]
        )
        ctype = int(raw.enc_loans_credit_type.iat[t])
        product = {
            0: "overdraft",
            1: "credit_line",
            2: "credit_line",
            3: "term_loan",
            4: "term_loan",
            5: "bank_guarantee",
        }.get(ctype, "term_loan")
        rows.append(
            {
                "company_key": key,
                "rn": int(raw.rn.iat[t]),
                "deal_uid": f"{key:08x}-{int(raw.rn.iat[t]):04x}-4000-8000-{rng.integers(16**11, 16**12):012x}",
                "lender_name": lender,
                "product_type": product,
                "limit_amount": float(limit),
                "opened_at": opened.isoformat(),
                "maturity_date": maturity.isoformat(),
                "closed_at": closed.isoformat() if closed else None,
                "outstanding": outstanding,
                "monthly_payment": monthly,
                "overdue_amount": overdue,
                "max_dpd": max_dpd,
                "payment_string": pay,
                "report_date": as_of.isoformat(),
                # исходные коды — для исследования (в БД не грузятся)
                "src_credit_type": ctype,
                "src_credit_status": int(raw.enc_loans_credit_status.iat[t]),
                "src_since_opened": int(raw.pre_since_opened.iat[t]),
                "src_limit": int(raw.pre_loans_credit_limit.iat[t]),
                "src_util": int(raw.pre_util.iat[t]),
                "src_cost_rate": int(raw.pre_loans_credit_cost_rate.iat[t]),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="папка data_for_competition из scoring_maps",
    )
    parser.add_argument("--out", type=Path, default=Path("ml/data") / DATASET_CODE)
    parser.add_argument("--companies", type=int, default=N_COMPANIES)
    parser.add_argument("--bad-share", type=float, default=BAD_SHARE)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    print(f"Читаю КИ из {args.source} …")
    raw = load_source(args.source, args.companies, args.bad_share, args.seed)
    print(
        f"  {raw.id.nunique():,} заявок, {len(raw):,} кредитов, дефолт {raw.groupby('id').flag.first().mean():.2%}"
    )
    tables = build(raw, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        path = args.out / f"{name}.csv.gz"
        df.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
        print(f"  {path}: {len(df):,} строк")
    manifest = {
        "dataset_code": DATASET_CODE,
        "seed": args.seed,
        "companies": len(tables["companies"]),
        "bad_share": round(float(tables["companies"].target.mean()), 4),
        "as_of_range": [FIRST_DATE.isoformat(), LAST_DATE.isoformat()],
        "beta": BETA,
        "tables": {k: len(v) for k, v in tables.items()},
        "payment_string": "индекс 0 — последний полный месяц перед заявкой; 0 без просрочки, 1 до 30 дн., 2 30+ дн., - нет данных",
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Готово.")


if __name__ == "__main__":
    main()
