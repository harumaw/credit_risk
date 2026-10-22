"""Признаки скоринга МСБ — чистые функции. Один код и для обучения (ml/research.ipynb), и для конвейера.

Вход — то, что приложение уже собирает из источников: карточка компании (ЕГРЮЛ/РМСП),
обязательства из БКИ со строкой платёжной дисциплины, обороты по счетам, налоги, ФССП, ЗСК.
Каталог признаков с описаниями — `FEATURE_CATALOG` (грузится в `feature_definitions`).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

# Строка платёжной дисциплины: индекс 0 — последний полный месяц перед датой расчёта.
# 0 — платёж без просрочки, 1 — просрочка до 30 дн., 2 — 30+ дн., «-» — нет данных.
OK, DPD_LT30, DPD_30P, NO_DATA = "0", "1", "2", "-"

# Веса просрочек выведены из матрицы переходов (ml/research.ipynb, раздел 3):
# тяжесть состояния = P(дойти до 30+ за 12 мес. из состояния) / P(то же из «до 30»),
# затухание = во сколько раз за месяц слабеет связь давней просрочки с дефолтом (лог-лифт).
SEVERITY = {OK: 0.0, DPD_LT30: 1.0, DPD_30P: 8.0, NO_DATA: 0.0}
RECENCY_DECAY = 0.9
NO_EVENT_MONTHS = 99  # «просрочек не было»


@dataclass(frozen=True)
class Obligation:
    limit_amount: float | None
    outstanding: float | None
    monthly_payment: float | None
    opened_at: date | None
    closed_at: date | None
    payment_string: str = ""


@dataclass(frozen=True)
class TurnoverMonth:
    month: date
    inflow: float
    outflow: float
    closing_balance: float


@dataclass(frozen=True)
class CompanyFacts:
    as_of_date: date
    legal_form: str  # ИП / ООО ...
    registration_date: date | None
    msp_category: str | None  # micro / small / medium
    okved_main: str | None
    region_code: str | None
    tax_regime: str | None
    zsk_zone: str | None = "green"
    tax_debt: float = 0.0
    fssp_active_cnt: int = 0
    fssp_active_amount: float = 0.0
    own_bank_client: bool = False
    obligations: Sequence[Obligation] = field(default_factory=tuple)
    turnovers: Sequence[TurnoverMonth] = field(default_factory=tuple)


def months_between(start: date, end: date) -> int:
    return (
        (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day)
    )


def okved_section(code: str | None) -> str | None:
    if not code:
        return None
    sections = [
        (1, 3, "A"), (5, 9, "B"), (10, 33, "C"), (35, 35, "D"), (36, 39, "E"), (41, 43, "F"),
        (45, 47, "G"), (49, 53, "H"), (55, 56, "I"), (58, 63, "J"), (64, 66, "K"), (68, 68, "L"),
        (69, 75, "M"), (77, 82, "N"), (84, 84, "O"), (85, 85, "P"), (86, 88, "Q"), (90, 93, "R"),
        (94, 96, "S"),
    ]  # fmt: skip
    try:
        division = int(code.split(".")[0])
    except ValueError:
        return None
    return next((s for lo, hi, s in sections if lo <= division <= hi), None)


def delinquency_index(strings: Iterable[str], months: int = 24) -> float:
    """Взвешенная сумма просрочек: тяжесть статуса × затухание по давности."""
    total = 0.0
    for s in strings:
        for k, ch in enumerate(s[:months]):
            total += SEVERITY.get(ch, 0.0) * RECENCY_DECAY**k
    return round(total, 4)


def bki_features(
    obligations: Sequence[Obligation], as_of: date
) -> dict[str, float | int]:
    strings = [o.payment_string or "" for o in obligations]
    active = [o for o in obligations if o.closed_at is None or o.closed_at > as_of]
    dpd_12 = sum(ch in (DPD_LT30, DPD_30P) for s in strings for ch in s[:12])
    dpd30_24 = sum(ch == DPD_30P for s in strings for ch in s[:24])
    last_dpd = min(
        (k for s in strings for k, ch in enumerate(s) if ch in (DPD_LT30, DPD_30P)),
        default=NO_EVENT_MONTHS,
    )
    worst_3m = max(
        (int(ch) for s in strings for ch in s[:3] if ch in (OK, DPD_LT30, DPD_30P)),
        default=0,
    )
    history = max(
        (months_between(o.opened_at, as_of) for o in obligations if o.opened_at),
        default=0,
    )
    new_6m = sum(
        1 for o in obligations if o.opened_at and months_between(o.opened_at, as_of) < 6
    )
    limit = sum(o.limit_amount or 0 for o in active)
    outstanding = sum(o.outstanding or 0 for o in active)
    return {
        "bki_loans_cnt": len(obligations),
        "bki_active_cnt": len(active),
        "bki_history_months": history,
        "bki_new_loans_6m": new_6m,
        "bki_dpd_months_12m": dpd_12,
        "bki_dpd30_months_24m": dpd30_24,
        "bki_months_since_dpd": last_dpd,
        "bki_worst_status_3m": worst_3m,
        "bki_delinquency_index": delinquency_index(strings),
        "bki_utilization": round(outstanding / limit, 4) if limit > 0 else 0.0,
    }


def turnover_features(
    turnovers: Sequence[TurnoverMonth],
) -> dict[str, float | int | None]:
    rows = sorted(turnovers, key=lambda t: t.month)[-12:]
    if not rows:
        return {
            "turnover_months": 0,
            "revenue_12m": None,
            "turnover_cv": None,
            "turnover_trend": None,
            "net_margin": None,
            "balance_to_inflow": None,
        }
    inflows = [t.inflow for t in rows]
    total = sum(inflows)
    mean = total / len(inflows)
    var = sum((x - mean) ** 2 for x in inflows) / len(inflows)
    half = len(rows) // 2
    first, second = inflows[:half], inflows[half:]
    trend = (
        (sum(second) / len(second)) / (sum(first) / len(first)) - 1
        if half and sum(first) > 0
        else None
    )
    return {
        "turnover_months": len(rows),
        "revenue_12m": round(total * 12 / len(rows), 2),  # годовой оборот (приведённый)
        "turnover_cv": round(var**0.5 / mean, 4) if mean > 0 else None,
        "turnover_trend": round(trend, 4) if trend is not None else None,
        "net_margin": round(sum(t.inflow - t.outflow for t in rows) / total, 4)
        if total > 0
        else None,
        "balance_to_inflow": round(
            sum(t.closing_balance for t in rows) / len(rows) / mean, 4
        )
        if mean > 0
        else None,
    }


def company_features(facts: CompanyFacts) -> dict[str, float | int | str | None]:
    """Полный вектор признаков компании на дату `as_of_date`."""
    as_of = facts.as_of_date
    obligations = [
        o for o in facts.obligations if o.opened_at is None or o.opened_at <= as_of
    ]
    feats: dict[str, float | int | str | None] = {
        "company_age_months": months_between(facts.registration_date, as_of)
        if facts.registration_date
        else None,
        "legal_form": "ИП" if facts.legal_form == "ИП" else "ЮЛ",
        "msp_category": facts.msp_category or "micro",
        "okved_section": okved_section(facts.okved_main),
        "region_code": facts.region_code,
        "tax_regime": facts.tax_regime,
        "zsk_zone": facts.zsk_zone or "green",
        "own_bank_client": int(facts.own_bank_client),
        "fssp_active_cnt": facts.fssp_active_cnt,
    }
    feats.update(bki_features(obligations, as_of))
    feats.update(turnover_features(facts.turnovers))
    monthly_inflow = (feats["revenue_12m"] or 0) / 12  # type: ignore[operator]
    payments = sum(
        o.monthly_payment or 0
        for o in obligations
        if o.closed_at is None or o.closed_at > as_of
    )
    feats["debt_burden"] = (
        round(payments / monthly_inflow, 4) if monthly_inflow > 0 else None
    )
    feats["tax_debt_ratio"] = (
        round(facts.tax_debt / monthly_inflow, 4) if monthly_inflow > 0 else None
    )
    feats["fssp_amount_ratio"] = (
        round(facts.fssp_active_amount / monthly_inflow, 4)
        if monthly_inflow > 0
        else None
    )
    return feats


# code: (название, тип, источник, как считается)
FEATURE_CATALOG: dict[str, tuple[str, str, str, str]] = {
    "company_age_months": (
        "Возраст бизнеса, мес.",
        "numeric",
        "fns_egrul",
        "as_of − дата регистрации",
    ),
    "legal_form": ("ОПФ (ИП / ЮЛ)", "categorical", "fns_egrul", "ИП или ЮЛ"),
    "msp_category": ("Категория МСП", "categorical", "rmsp", "micro / small / medium"),
    "okved_section": (
        "Раздел ОКВЭД основного вида деятельности",
        "categorical",
        "fns_egrul",
        "буква раздела по классу ОКВЭД-2",
    ),
    "region_code": (
        "Регион регистрации",
        "categorical",
        "fns_egrul",
        "2 цифры кода региона",
    ),
    "tax_regime": (
        "Режим налогообложения",
        "categorical",
        "fns_tax",
        "osno / usn_* / psn / ausn / eshn",
    ),
    "zsk_zone": ("Зона ЗСК ЦБ", "categorical", "cbr_zsk", "green / yellow / red"),
    "own_bank_client": (
        "Клиент нашего банка (РКО)",
        "boolean",
        "bank_internal",
        "есть счёт в банке",
    ),
    "fssp_active_cnt": (
        "Открытых исп. производств",
        "numeric",
        "fssp",
        "число незакрытых ИП ФССП",
    ),
    "fssp_amount_ratio": (
        "Долг ФССП к месячному обороту",
        "numeric",
        "fssp",
        "остаток по ИП / средний приход в месяц",
    ),
    "tax_debt_ratio": (
        "Налоговый долг к месячному обороту",
        "numeric",
        "fns_tax",
        "недоимка / средний приход в месяц",
    ),
    "bki_loans_cnt": (
        "Кредитов в истории",
        "numeric",
        "bki",
        "число обязательств в КИ",
    ),
    "bki_active_cnt": (
        "Действующих кредитов",
        "numeric",
        "bki",
        "не закрыты на дату расчёта",
    ),
    "bki_history_months": (
        "Длина кредитной истории, мес.",
        "numeric",
        "bki",
        "с открытия самого старого кредита",
    ),
    "bki_new_loans_6m": (
        "Новых кредитов за 6 мес.",
        "numeric",
        "bki",
        "открыты < 6 мес. назад",
    ),
    "bki_dpd_months_12m": (
        "Месяцев с просрочкой за 12 мес.",
        "numeric",
        "bki",
        "статусы 1/2 в первых 12 позициях строки, по всем кредитам",
    ),
    "bki_dpd30_months_24m": (
        "Месяцев с просрочкой 30+ за 24 мес.",
        "numeric",
        "bki",
        "статусы 2 в первых 24 позициях",
    ),
    "bki_months_since_dpd": (
        "Месяцев с последней просрочки",
        "numeric",
        "bki",
        "индекс первой 1/2 в строке; 99 — не было",
    ),
    "bki_worst_status_3m": (
        "Худший статус за 3 мес.",
        "numeric",
        "bki",
        "max статуса в первых 3 позициях",
    ),
    "bki_delinquency_index": (
        "Индекс просрочек (матрица переходов)",
        "numeric",
        "bki",
        "Σ тяжесть(статус)·0,9^мес; тяжесть 0/1/8",
    ),
    "bki_utilization": (
        "Утилизация лимитов",
        "numeric",
        "bki",
        "Σ остаток / Σ лимит по действующим",
    ),
    "debt_burden": (
        "Долговая нагрузка",
        "numeric",
        "bki",
        "Σ ежемес. платежей / средний приход в месяц",
    ),
    "turnover_months": (
        "Месяцев с оборотами",
        "numeric",
        "bank_internal",
        "за последние 12 мес.",
    ),
    "revenue_12m": (
        "Оборот за 12 мес., ₽",
        "numeric",
        "bank_internal",
        "Σ поступлений, приведённая к году",
    ),
    "turnover_cv": (
        "Волатильность оборотов",
        "numeric",
        "bank_internal",
        "σ/μ месячных поступлений",
    ),
    "turnover_trend": (
        "Тренд оборотов",
        "numeric",
        "bank_internal",
        "среднее 2-го полугодия / 1-го − 1",
    ),
    "net_margin": (
        "Чистый денежный поток к обороту",
        "numeric",
        "bank_internal",
        "Σ(приход − расход) / Σ приход",
    ),
    "balance_to_inflow": (
        "Остаток к месячному обороту",
        "numeric",
        "bank_internal",
        "средний остаток / средний приход",
    ),
}
