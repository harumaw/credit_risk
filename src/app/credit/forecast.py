"""Прогноз оборотов и остатков на несколько месяцев вперёд — линейный тренд по истории."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import pstdev

Z_80 = 1.28  # ширина коридора: ~80% наблюдений при нормальных остатках


@dataclass(frozen=True)
class ForecastPoint:
    month: date
    value: Decimal
    lower: Decimal
    upper: Decimal


def add_months(month: date, n: int) -> date:
    index = month.year * 12 + month.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def linear_forecast(
    history: list[Decimal], last_month: date, horizon: int = 3
) -> list[ForecastPoint]:
    """МНК-прямая по истории, продолжена на horizon месяцев; значения не ниже нуля."""
    n = len(history)
    if n == 0:
        return []
    ys = [float(v) for v in history]
    if n == 1:
        slope, intercept = 0.0, ys[0]
    else:
        x_mean = (n - 1) / 2
        y_mean = sum(ys) / n
        sxx = sum((x - x_mean) ** 2 for x in range(n))
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(range(n), ys)) / sxx
        intercept = y_mean - slope * x_mean
    residuals = [y - (intercept + slope * x) for x, y in enumerate(ys)]
    band = Z_80 * pstdev(residuals) if n > 1 else 0.0

    points = []
    for h in range(1, horizon + 1):
        value = max(intercept + slope * (n - 1 + h), 0.0)
        points.append(
            ForecastPoint(
                month=add_months(last_month, h),
                value=_money(value),
                lower=_money(max(value - band, 0.0)),
                upper=_money(value + band),
            )
        )
    return points


def _money(value: float) -> Decimal:
    return Decimal(round(value))
