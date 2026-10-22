"""Профиль компании/ИП — общий источник для всех эндпоинтов симулятора.

Профиль детерминирован: один и тот же ИНН всегда даёт одни и те же данные
(генератор засеян хэшем ИНН). Персоны из `personas.py` переопределяют генерацию.
"""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

OWN_BANK = "Наш банк"
OWN_BANK_BIK = "049999001"  # синтетический БИК


@dataclass
class Credit:
    deal_uid: str
    lender: str
    kind: str  # Кредит / Кредитная линия / Овердрафт / Лизинг
    limit: int
    outstanding: int
    monthly_payment: int
    opened: date
    maturity: date
    closed: date | None = None
    overdue: int = 0
    max_dpd: int = 0
    payment_day: int = 25  # число месяца, когда списывается платёж


@dataclass
class Proceeding:
    number: str
    opened: date
    subject: str
    amount: int
    remaining: int
    closed: date | None = None


@dataclass
class BankruptcyMessage:
    case_number: str
    kind: str
    published: date
    self_initiated: bool = False


@dataclass
class Turnovers:
    """Как генерировать обороты: средний приход, чистый поток и средний остаток в месяц."""

    avg_inflow: int
    net_income: int
    avg_balance: int


@dataclass
class Profile:
    inn: str
    name: str  # для ИП — ФИО полностью
    reg_date: date
    region: str
    okved_main: tuple[str, str]
    director_fio: str
    director_inn: str
    okved_extra: list[tuple[str, str]] = field(default_factory=list)
    legal_form: str = "ООО"
    status: str = "Действующее"
    address: str = ""
    founders: list[tuple[str, str, float]] = field(default_factory=list)
    tax_regime: str = "УСН доходы"
    tax_debt: int = 0
    penalties: int = 0
    fines: int = 0
    msp_category: str | None = "Малое предприятие"
    headcount: int = 10
    proceedings: list[Proceeding] = field(default_factory=list)
    bankruptcy: list[BankruptcyMessage] = field(default_factory=list)
    zsk_zone: str = "green"
    credits: list[Credit] = field(default_factory=list)
    own_bank_client: bool = True
    turnovers: Turnovers | None = None

    @property
    def is_ip(self) -> bool:
        return len(self.inn) == 12

    @property
    def ogrn(self) -> str:
        prefix = "3" if self.is_ip else "1"
        digits = f"{prefix}{self.reg_date:%y}{self.region}{_seed(self.inn, 'ogrn') % 10**9:09d}"
        size = 14 if self.is_ip else 12
        body = (digits + "0" * size)[:size]
        mod = 13 if self.is_ip else 11
        return body + str(int(body) % mod % 10)

    @property
    def kpp(self) -> str | None:
        return None if self.is_ip else f"{self.inn[:4]}01001"


OKVED = [
    ("46.90", "Торговля оптовая неспециализированная"),
    (
        "47.91",
        "Торговля розничная по почте или по информационно-коммуникационной сети Интернет",
    ),
    ("52.29", "Деятельность вспомогательная прочая, связанная с перевозками"),
    ("56.10", "Деятельность ресторанов и услуги по доставке продуктов питания"),
    ("47.71", "Торговля розничная одеждой в специализированных магазинах"),
    ("47.19", "Торговля розничная прочая в неспециализированных магазинах"),
    ("62.01", "Разработка компьютерного программного обеспечения"),
    ("41.20", "Строительство жилых и нежилых зданий"),
    ("49.41", "Деятельность автомобильного грузового транспорта"),
    ("68.20", "Аренда и управление собственным или арендованным недвижимым имуществом"),
    ("73.11", "Деятельность рекламных агентств"),
    ("96.02", "Предоставление услуг парикмахерскими и салонами красоты"),
    ("43.21", "Производство электромонтажных работ"),
    ("45.20", "Техническое обслуживание и ремонт автотранспортных средств"),
]
OKVED_NAMES = dict(OKVED)

_NAMES = [
    "Альтаир",
    "Меридиан",
    "Горизонт",
    "Сфера",
    "Гранит",
    "Ладога",
    "Полюс",
    "Магистраль",
    "Орион",
    "Кедр",
]
_SURNAMES = [
    "Иванов",
    "Петров",
    "Сидоров",
    "Козлов",
    "Новиков",
    "Морозов",
    "Соколов",
    "Павлов",
]
_FIRST = ["Алексей", "Михаил", "Андрей", "Николай", "Павел", "Юрий"]
_PATRONYMIC = ["Александрович", "Сергеевич", "Игоревич", "Олегович", "Викторович"]
_LENDERS = ["Банк «Пример»", "Банк «Образец»", "ООО «Лизинг-Пример»"]
_REGIMES = ["ОСН", "УСН доходы", "УСН доходы минус расходы", "АУСН"]


def _seed(inn: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{inn}:{salt}".encode()).digest()[:8], "big")


def rng_for(inn: str, salt: str = "profile") -> random.Random:
    return random.Random(_seed(inn, salt))


def _person_inn(rnd: random.Random) -> str:
    w11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    w12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    d = [rnd.randint(0, 9) for _ in range(10)]
    d[0], d[1] = 7, 7
    d.append(sum(a * b for a, b in zip(d, w11)) % 11 % 10)
    d.append(sum(a * b for a, b in zip(d, w12)) % 11 % 10)
    return "".join(map(str, d))


def generate(inn: str, today: date) -> Profile:
    """Обычная компания без особенностей: генерируется по ИНН."""
    rnd = rng_for(inn)
    fio = f"{rnd.choice(_SURNAMES)} {rnd.choice(_FIRST)} {rnd.choice(_PATRONYMIC)}"
    director_inn = inn if len(inn) == 12 else _person_inn(rnd)
    okved = rnd.sample(OKVED, 3)
    reg_date = today - timedelta(days=rnd.randint(2 * 365, 12 * 365))
    avg_inflow = rnd.randrange(800_000, 9_000_000, 10_000)
    is_ip = len(inn) == 12
    credits = []
    if rnd.random() < 0.6:
        limit = rnd.randrange(500_000, 5_000_000, 50_000)
        outstanding = int(limit * rnd.uniform(0.3, 0.9))
        credits.append(
            Credit(
                deal_uid=f"{_seed(inn, 'deal'):032x}"[:32],
                lender=rnd.choice([OWN_BANK, *_LENDERS]),
                kind="Кредит",
                limit=limit,
                outstanding=outstanding,
                monthly_payment=int(limit / 24 * 1.12),
                opened=today - timedelta(days=rnd.randint(90, 700)),
                maturity=today + timedelta(days=rnd.randint(180, 900)),
                payment_day=rnd.randint(1, 28),
            )
        )
    return Profile(
        inn=inn,
        name=fio if is_ip else f"«{rnd.choice(_NAMES)}»",
        legal_form="ИП" if is_ip else "ООО",
        reg_date=reg_date,
        region=inn[:2],
        address=f"г. Москва, ул. Примерная, д. {rnd.randint(1, 120)}",
        okved_main=okved[0],
        okved_extra=okved[1:],
        director_fio=fio,
        director_inn=director_inn,
        founders=[] if is_ip else [(fio, director_inn, 100.0)],
        tax_regime="ПСН" if is_ip and rnd.random() < 0.3 else rnd.choice(_REGIMES),
        msp_category=rnd.choice(["Микропредприятие", "Малое предприятие"]),
        headcount=rnd.randint(1, 15) if is_ip else rnd.randint(5, 90),
        credits=credits,
        own_bank_client=rnd.random() < 0.7,
        turnovers=Turnovers(
            avg_inflow=avg_inflow,
            net_income=int(avg_inflow * rnd.uniform(0.06, 0.18)),
            avg_balance=int(avg_inflow * rnd.uniform(0.2, 0.6)),
        ),
    )


def add_months(month: date, n: int) -> date:
    index = month.year * 12 + month.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


PAYMENT_STRING_MONTHS = 48


def payment_string(credit: Credit, today: date) -> str:
    """Строка платёжной дисциплины КИ: индекс 0 — последний полный месяц.

    0 — без просрочки, 1 — просрочка до 30 дн., 2 — 30+ дн., «-» — договор закрыт.
    Строка кончается на месяце выдачи. Просрочка из max_dpd ставится в середину
    видимого срока жизни договора (детерминированно); текущая — в индекс 0.
    """
    last = add_months(today.replace(day=1), -1)
    opened = credit.opened.replace(day=1)
    closed = credit.closed.replace(day=1) if credit.closed else None
    chars = []
    for k in range(PAYMENT_STRING_MONTHS):
        month = add_months(last, -k)
        if month < opened:
            break
        chars.append("-" if closed is not None and month > closed else "0")
    active = [k for k, ch in enumerate(chars) if ch == "0"]
    if credit.max_dpd > 0 and active:
        status = "2" if credit.max_dpd >= 30 else "1"
        k = 0 if credit.overdue > 0 else active[len(active) // 2]
        chars[k] = status
        if status == "2" and k + 1 < len(chars) and chars[k + 1] == "0":
            chars[k + 1] = "1"  # до 30+ дней просрочка доходит через «до 30»
    return "".join(chars)


def monthly_turnovers(profile: Profile, today: date, months: int = 24) -> list[dict]:
    """Обороты за последние полные месяцы (не раньше регистрации). Детерминированы по ИНН и месяцу."""
    if profile.turnovers is None:
        return []
    t = profile.turnovers
    last = add_months(today.replace(day=1), -1)
    first_allowed = add_months(profile.reg_date.replace(day=1), 1)
    rows = []
    for i in range(months - 1, -1, -1):
        month = add_months(last, -i)
        if month < first_allowed:
            continue
        rnd = rng_for(profile.inn, f"month:{month:%Y-%m}")
        season = 1 + 0.15 * (
            1 if month.month in (11, 12, 3, 4) else -1 if month.month in (1, 7) else 0
        )
        growth = 1 + 0.01 * (months - 1 - i - months / 2)  # плавный рост ~1% в месяц
        inflow = t.avg_inflow * season * growth * rnd.uniform(0.92, 1.08)
        # чистый поток колеблется ±5% по чётности месяца — за любые 12 мес в среднем ровно net_income
        net = t.net_income * (1.05 if month.month % 2 == 0 else 0.95)
        rows.append(
            {
                "month": month,
                "inflow": round(inflow, 2),
                "outflow": round(inflow - net, 2),
                "closing_balance": round(t.avg_balance * rnd.uniform(0.75, 1.25), 2),
                "tx_count": int(inflow / 25_000) + rnd.randint(5, 40),
                "counterparties": rnd.randint(8, 60),
            }
        )
    return rows
