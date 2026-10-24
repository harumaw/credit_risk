"""Рекомендация по грейду для разбора без заявки (синтетика, пересчёт в кабинете администратора).

Та же матрица, что в конвейере (`credit/decision.py::decide`), но без продукта и DSCR:
A–B → одобрение, C → ручной разбор, D–E → отказ; жёсткий стоп-фактор → отказ без скоринга.
Контрпредложение появляется только в заявке, когда сумма выше лимита DSCR.
"""

from app.credit.stop_factors import BY_CODE
from app.enums import DecisionType, StopSeverity

GRADE_DECISION: dict[str, DecisionType] = {
    "A": DecisionType.APPROVE,
    "B": DecisionType.APPROVE,
    "C": DecisionType.MANUAL_REVIEW,
    "D": DecisionType.DECLINE,
    "E": DecisionType.DECLINE,
}

DECISION_LABEL: dict[DecisionType, str] = {
    DecisionType.APPROVE: "Одобрено",
    DecisionType.COUNTER_OFFER: "Контрпредложение",
    DecisionType.MANUAL_REVIEW: "Ручной разбор",
    DecisionType.DECLINE: "Отказ",
}


def recommend(grade: str | None, has_hard_stop: bool) -> DecisionType | None:
    if has_hard_stop:
        return DecisionType.DECLINE
    if grade is None:
        return None
    return GRADE_DECISION.get(grade)


def hard_stops(features: dict) -> list[str]:
    """Жёсткие стоп-факторы (коды `credit/stop_factors.py`), видные по признакам синтетики."""
    codes = []
    status = features.get("company_status")
    if status == "bankrupt":
        codes.append("BANKRUPTCY")
    elif status not in (None, "active"):
        codes.append("COMPANY_INACTIVE")
    if features.get("zsk_zone") == "red":
        codes.append("ZSK_RED")
    return codes


def hard_codes(codes: list[str]) -> list[str]:
    """Жёсткие из сработавших стоп-факторов."""
    return [c for c in codes if BY_CODE[c].severity == StopSeverity.HARD]


def recommend_checks(grade: str | None, triggered: list[str]) -> DecisionType | None:
    """Как в конвейере: жёсткий или мягкий-отказной стоп → отказ, мягкий-разборный → ручной разбор."""
    if hard_codes(triggered) or any(BY_CODE[c].action == "decline" for c in triggered):
        return DecisionType.DECLINE
    if triggered:
        return DecisionType.MANUAL_REVIEW
    return recommend(grade, False)
