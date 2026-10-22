"""Автомат статусов заявки. Переходы делает только бэкенд, недопустимый — ошибка (API: 409).

Короткий путь (решение владельца, новых статусов в БД нет):
submitted → scoring → approved | declined | manual_review → offer_accepted → contract_signed
→ issued; контрпредложение — approved с суммой/сроком меньше запроса; cancelled — отмена клиентом.
"""

from app.enums import ApplicationStatus as S

ALLOWED: dict[S, frozenset[S]] = {
    S.SUBMITTED: frozenset({S.SCORING, S.CANCELLED}),
    S.SCORING: frozenset({S.APPROVED, S.DECLINED, S.MANUAL_REVIEW, S.CANCELLED}),
    S.MANUAL_REVIEW: frozenset({S.APPROVED, S.DECLINED, S.CANCELLED}),
    S.APPROVED: frozenset({S.OFFER_ACCEPTED, S.CANCELLED}),
    S.OFFER_ACCEPTED: frozenset({S.CONTRACT_SIGNED, S.CANCELLED}),
    S.CONTRACT_SIGNED: frozenset({S.ISSUED}),
}
FINAL = frozenset({S.ISSUED, S.DECLINED, S.CANCELLED})


class TransitionError(Exception):
    """Переход из текущего статуса в запрошенный не разрешён."""

    def __init__(self, current: S, target: S):
        super().__init__(f"{current.value} → {target.value}")
        self.current = current
        self.target = target


def check_transition(current: S, target: S) -> None:
    if target not in ALLOWED.get(current, frozenset()):
        raise TransitionError(current, target)
