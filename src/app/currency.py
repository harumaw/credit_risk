from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExchangeRate

SUPPORTED_CURRENCIES = ["USD", "EUR", "KZT", "RUB"]
RATES_TTL = timedelta(hours=24)
RATES_URL = "https://open.er-api.com/v6/latest/USD"


async def ensure_fresh_rates(session: AsyncSession) -> None:
    stmt = select(func.max(ExchangeRate.updated_at))
    result = await session.execute(stmt)
    last_updated = result.scalar_one_or_none()

    if last_updated is not None and datetime.now(UTC) - last_updated < RATES_TTL:
        return

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(RATES_URL)
        response.raise_for_status()
        data = response.json()

    rates = data["rates"]

    for code in SUPPORTED_CURRENCIES:
        if code not in rates:
            continue

        stmt = select(ExchangeRate).where(ExchangeRate.currency == code)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            session.add(ExchangeRate(currency=code, rate_to_usd=Decimal(str(rates[code]))))
        else:
            row.rate_to_usd = Decimal(str(rates[code]))

    await session.commit()


async def _get_rates_map(session: AsyncSession) -> dict[str, Decimal]:
    stmt = select(ExchangeRate)
    result = await session.execute(stmt)
    return {row.currency: row.rate_to_usd for row in result.scalars().all()}


async def convert(
    session: AsyncSession, amount: Decimal, from_currency: str, to_currency: str
) -> Decimal:
    if from_currency == to_currency:
        return amount

    await ensure_fresh_rates(session)
    rates = await _get_rates_map(session)

    amount_in_usd = amount / rates[from_currency]
    return (amount_in_usd * rates[to_currency]).quantize(Decimal("0.01"))
