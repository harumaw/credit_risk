"""Стоп-факторы — чистые функции. Справочник `STOP_FACTORS` грузит seed в `stop_factors`.

Жёсткий фактор — отказ без вариантов. Мягкий — по действию: `decline` (мягкий отказ с
подсказкой, когда вернуться) или `review` (заявка передаётся на ручную проверку банка).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.enums import StopSeverity

MIN_AGE_MONTHS = 6
TAX_DEBT_LIMIT = Decimal(50_000)
FSSP_LIMIT = Decimal(100_000)
PAST_DPD_DAYS = 30


@dataclass(frozen=True)
class StopFactorDef:
    code: str
    name: str
    severity: StopSeverity
    action: str  # decline / review
    rule: str  # человекочитаемое правило — в stop_factors.rule_expression


STOP_FACTORS = [
    StopFactorDef("COMPANY_INACTIVE", "Компания не действует", StopSeverity.HARD, "decline",
                  "статус в ЕГРЮЛ/ЕГРИП ≠ действующая"),
    StopFactorDef("BANKRUPTCY", "Сообщения о банкротстве", StopSeverity.HARD, "decline",
                  "есть сообщения в ЕФРСБ"),
    StopFactorDef("ZSK_RED", "Красная зона ЗСК ЦБ", StopSeverity.HARD, "decline",
                  "zsk_zone = red"),
    StopFactorDef("AGE_LT_6M", "Бизнесу меньше 6 месяцев", StopSeverity.SOFT, "decline",
                  f"возраст < {MIN_AGE_MONTHS} мес."),
    StopFactorDef("TAX_DEBT", "Налоговый долг", StopSeverity.SOFT, "review",
                  f"недоимка + пени + штрафы > {TAX_DEBT_LIMIT} ₽"),
    StopFactorDef("FSSP_DEBT", "Долг у приставов", StopSeverity.SOFT, "review",
                  f"остаток по открытым ИП ФССП > {FSSP_LIMIT} ₽"),
    StopFactorDef("CURRENT_DPD", "Текущая просрочка", StopSeverity.SOFT, "review",
                  "просроченная задолженность по КИ > 0"),
    StopFactorDef("PAST_DPD_30", "Просрочка 30+ дней в прошлом", StopSeverity.SOFT, "review",
                  f"max DPD по любому договору ≥ {PAST_DPD_DAYS}"),
]  # fmt: skip
BY_CODE = {f.code: f for f in STOP_FACTORS}


@dataclass(frozen=True)
class StopFacts:
    company_active: bool
    bankruptcy_messages: int
    zsk_zone: str | None
    age_months: int | None
    tax_debt: Decimal
    fssp_remaining: Decimal
    current_overdue: Decimal
    worst_dpd: int
    eligible_from: date | None = None  # с этой даты бизнесу 6 месяцев


@dataclass(frozen=True)
class StopCheck:
    code: str
    triggered: bool
    details: dict


def evaluate(f: StopFacts) -> list[StopCheck]:
    """Все факторы справочника с результатом — сохраняются целиком (stop_factor_results)."""
    rules = {
        "COMPANY_INACTIVE": (not f.company_active, {}),
        "BANKRUPTCY": (f.bankruptcy_messages > 0, {"messages": f.bankruptcy_messages}),
        "ZSK_RED": (f.zsk_zone == "red", {"zone": f.zsk_zone}),
        "AGE_LT_6M": (
            f.age_months is not None and f.age_months < MIN_AGE_MONTHS,
            {
                "age_months": f.age_months,
                "eligible_from": f.eligible_from.isoformat()
                if f.eligible_from
                else None,
            },
        ),
        "TAX_DEBT": (f.tax_debt > TAX_DEBT_LIMIT, {"amount": float(f.tax_debt)}),
        "FSSP_DEBT": (
            f.fssp_remaining > FSSP_LIMIT,
            {"amount": float(f.fssp_remaining)},
        ),
        "CURRENT_DPD": (
            f.current_overdue > 0,
            {"overdue": float(f.current_overdue)},
        ),
        "PAST_DPD_30": (f.worst_dpd >= PAST_DPD_DAYS, {"max_dpd": f.worst_dpd}),
    }
    return [
        StopCheck(d.code, triggered, details)
        for d in STOP_FACTORS
        for triggered, details in [rules[d.code]]
    ]
