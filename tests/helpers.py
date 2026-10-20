"""Фабрики тестовых данных."""

from app.types import _INN_FL_WEIGHTS_11, _INN_FL_WEIGHTS_12, _inn_check_digit


def make_inn_fl(n: int) -> str:
    """Валидный (по контрольной сумме) синтетический ИНН физлица из числа n."""
    base = [int(c) for c in f"{n:010d}"]
    base.append(_inn_check_digit(base, _INN_FL_WEIGHTS_11))
    base.append(_inn_check_digit(base, _INN_FL_WEIGHTS_12))
    return "".join(map(str, base))


def registration_payload(
    email: str, n: int = 1, **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "email": email,
        "password": "password123",
        "last_name": "Иванов",
        "first_name": "Иван",
        "inn_fl": make_inn_fl(n),
    }
    payload.update(overrides)
    return payload
