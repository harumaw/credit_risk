"""Данные внешних источников: сырые снимки (data_fetches) и нормализованные таблицы."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import DataSource
from app.models import (
    BankAccount,
    BankruptcyEvent,
    CreditObligation,
    DataFetch,
    EnforcementProceeding,
    MonthlyTurnover,
    ObligationPayment,
    TaxDebt,
    ZskStatus,
)


async def add_fetch(session: AsyncSession, fetch: DataFetch) -> DataFetch:
    session.add(fetch)
    await session.flush()
    return fetch


async def latest_fetches(
    session: AsyncSession, company_id: uuid.UUID
) -> list[DataFetch]:
    """Последний запрос к каждому источнику по компании."""
    stmt = (
        select(DataFetch)
        .where(DataFetch.company_id == company_id)
        .distinct(DataFetch.source)
        .order_by(DataFetch.source, DataFetch.requested_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars())


async def upsert_tax_debt(session: AsyncSession, row: TaxDebt) -> None:
    stmt = insert(TaxDebt).values(
        id=row.id or uuid.uuid4(),
        company_id=row.company_id,
        as_of_date=row.as_of_date,
        tax_debt=row.tax_debt,
        penalties=row.penalties,
        fines=row.fines,
        fetch_id=row.fetch_id,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["company_id", "as_of_date"],
        set_={
            "tax_debt": stmt.excluded.tax_debt,
            "penalties": stmt.excluded.penalties,
            "fines": stmt.excluded.fines,
            "fetch_id": stmt.excluded.fetch_id,
        },
    )
    await session.execute(stmt)


async def latest_tax_debt(
    session: AsyncSession, company_id: uuid.UUID
) -> TaxDebt | None:
    stmt = (
        select(TaxDebt)
        .where(TaxDebt.company_id == company_id)
        .order_by(TaxDebt.as_of_date.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_zsk(session: AsyncSession, row: ZskStatus) -> None:
    stmt = insert(ZskStatus).values(
        id=row.id or uuid.uuid4(),
        company_id=row.company_id,
        zone=row.zone,
        assigned_at=row.assigned_at,
        as_of_date=row.as_of_date,
        fetch_id=row.fetch_id,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["company_id", "as_of_date"],
        set_={
            "zone": stmt.excluded.zone,
            "assigned_at": stmt.excluded.assigned_at,
            "fetch_id": stmt.excluded.fetch_id,
        },
    )
    await session.execute(stmt)


async def latest_zsk(session: AsyncSession, company_id: uuid.UUID) -> ZskStatus | None:
    stmt = (
        select(ZskStatus)
        .where(ZskStatus.company_id == company_id)
        .order_by(ZskStatus.as_of_date.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_enforcements(
    session: AsyncSession, rows: list[EnforcementProceeding]
) -> None:
    for row in rows:
        stmt = insert(EnforcementProceeding).values(
            id=row.id or uuid.uuid4(),
            company_id=row.company_id,
            ip_number=row.ip_number,
            opened_at=row.opened_at,
            closed_at=row.closed_at,
            close_reason=row.close_reason,
            subject=row.subject,
            amount=row.amount,
            remaining_amount=row.remaining_amount,
            fetch_id=row.fetch_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["ip_number"],
            set_={
                "closed_at": stmt.excluded.closed_at,
                "close_reason": stmt.excluded.close_reason,
                "remaining_amount": stmt.excluded.remaining_amount,
                "fetch_id": stmt.excluded.fetch_id,
            },
        )
        await session.execute(stmt)


async def active_enforcements(
    session: AsyncSession, company_id: uuid.UUID, as_of: date | None = None
) -> tuple[int, Decimal]:
    """Сколько производств открыто (на дату as_of, по умолчанию — сейчас) и остаток по ним."""
    if as_of is None:
        is_open = EnforcementProceeding.closed_at.is_(None)
    else:  # point-in-time, как в обучающей выборке
        is_open = (EnforcementProceeding.opened_at <= as_of) & (
            EnforcementProceeding.closed_at.is_(None)
            | (EnforcementProceeding.closed_at > as_of)
        )
    stmt = select(
        func.count(EnforcementProceeding.id),
        func.coalesce(func.sum(EnforcementProceeding.remaining_amount), 0),
    ).where(EnforcementProceeding.company_id == company_id, is_open)
    count, remaining = (await session.execute(stmt)).one()
    return count, Decimal(remaining)


async def replace_bankruptcy_events(
    session: AsyncSession, company_id: uuid.UUID, rows: list[BankruptcyEvent]
) -> None:
    await session.execute(
        delete(BankruptcyEvent).where(BankruptcyEvent.company_id == company_id)
    )
    session.add_all(rows)
    await session.flush()


async def count_bankruptcy_events(session: AsyncSession, company_id: uuid.UUID) -> int:
    stmt = select(func.count(BankruptcyEvent.id)).where(
        BankruptcyEvent.company_id == company_id
    )
    return (await session.execute(stmt)).scalar_one()


async def replace_obligations(
    session: AsyncSession,
    company_id: uuid.UUID,
    source: DataSource,
    obligations: list[tuple[CreditObligation, list[ObligationPayment]]],
) -> None:
    """Свежий отчёт заменяет предыдущий: история остаётся в снимках data_fetches."""
    old_ids = select(CreditObligation.id).where(
        CreditObligation.company_id == company_id, CreditObligation.source == source
    )
    await session.execute(
        delete(ObligationPayment).where(ObligationPayment.obligation_id.in_(old_ids))
    )
    await session.execute(
        delete(CreditObligation).where(
            CreditObligation.company_id == company_id,
            CreditObligation.source == source,
        )
    )
    for obligation, payments in obligations:
        session.add(obligation)
        await session.flush()
        for payment in payments:
            payment.obligation_id = obligation.id
        session.add_all(payments)
    await session.flush()


@dataclass(frozen=True)
class OpenObligation:
    id: uuid.UUID
    company_id: uuid.UUID
    lender: str | None
    product_type: str | None
    outstanding: Decimal
    overdue: Decimal
    max_dpd: int
    next_payment_date: date | None
    next_payment: Decimal


async def open_obligations(
    session: AsyncSession, company_ids: list[uuid.UUID], today: date
) -> list[OpenObligation]:
    """Действующие договоры с ближайшим плановым платежом."""
    next_due = (
        select(
            ObligationPayment.obligation_id,
            func.min(ObligationPayment.due_date).label("due_date"),
        )
        .where(ObligationPayment.due_date >= today)
        .group_by(ObligationPayment.obligation_id)
        .subquery()
    )
    stmt = (
        select(
            CreditObligation,
            next_due.c.due_date,
            ObligationPayment.amount_due,
        )
        .outerjoin(next_due, next_due.c.obligation_id == CreditObligation.id)
        .outerjoin(
            ObligationPayment,
            (ObligationPayment.obligation_id == CreditObligation.id)
            & (ObligationPayment.due_date == next_due.c.due_date),
        )
        .where(
            CreditObligation.company_id.in_(company_ids),
            CreditObligation.closed_at.is_(None),
        )
        .order_by(next_due.c.due_date.nulls_last(), CreditObligation.lender_name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        OpenObligation(
            id=o.id,
            company_id=o.company_id,
            lender=o.lender_name,
            product_type=o.product_type.value if o.product_type else None,
            outstanding=o.outstanding or Decimal(0),
            overdue=o.overdue_amount or Decimal(0),
            max_dpd=o.max_dpd or 0,
            next_payment_date=due_date,
            next_payment=amount or Decimal(0),
        )
        for o, due_date, amount in rows
    ]


async def open_obligation_schedules(
    session: AsyncSession, company_id: uuid.UUID
) -> list[tuple[CreditObligation, list[tuple[date, Decimal]]]]:
    """Действующие договоры с графиком платежей (дата, сумма) по возрастанию."""
    obligations = (
        await session.scalars(
            select(CreditObligation).where(
                CreditObligation.company_id == company_id,
                CreditObligation.closed_at.is_(None),
            )
        )
    ).all()
    if not obligations:
        return []
    rows = (
        await session.execute(
            select(
                ObligationPayment.obligation_id,
                ObligationPayment.due_date,
                ObligationPayment.amount_due,
            )
            .where(ObligationPayment.obligation_id.in_([o.id for o in obligations]))
            .order_by(ObligationPayment.due_date)
        )
    ).all()
    schedules: dict[uuid.UUID, list[tuple[date, Decimal]]] = {}
    for obligation_id, due_date, amount in rows:
        schedules.setdefault(obligation_id, []).append((due_date, amount))
    return [(o, schedules.get(o.id, [])) for o in obligations]


async def worst_past_dpd(session: AsyncSession, company_id: uuid.UUID) -> int:
    """Максимальная просрочка в днях по всем договорам, включая закрытые."""
    stmt = select(func.coalesce(func.max(CreditObligation.max_dpd), 0)).where(
        CreditObligation.company_id == company_id
    )
    return (await session.execute(stmt)).scalar_one()


async def get_or_create_account(
    session: AsyncSession, company_id: uuid.UUID, account: BankAccount
) -> BankAccount:
    stmt = select(BankAccount).where(
        BankAccount.company_id == company_id,
        BankAccount.account_masked == account.account_masked,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    session.add(account)
    await session.flush()
    return account


async def upsert_turnovers(session: AsyncSession, rows: list[MonthlyTurnover]) -> None:
    if not rows:
        return
    stmt = insert(MonthlyTurnover).values(
        [
            {
                "account_id": r.account_id,
                "month": r.month,
                "inflow": r.inflow,
                "outflow": r.outflow,
                "closing_balance": r.closing_balance,
                "tx_count": r.tx_count,
                "counterparties_cnt": r.counterparties_cnt,
                "source": r.source,
            }
            for r in rows
        ]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id", "month"],
        set_={
            "inflow": stmt.excluded.inflow,
            "outflow": stmt.excluded.outflow,
            "closing_balance": stmt.excluded.closing_balance,
            "tx_count": stmt.excluded.tx_count,
            "counterparties_cnt": stmt.excluded.counterparties_cnt,
        },
    )
    await session.execute(stmt)


@dataclass(frozen=True)
class MonthTotals:
    company_id: uuid.UUID
    month: date
    inflow: Decimal
    outflow: Decimal
    closing_balance: Decimal


async def monthly_totals(
    session: AsyncSession, company_ids: list[uuid.UUID]
) -> list[MonthTotals]:
    """Обороты и остатки по месяцам, сложенные по всем счетам компании."""
    stmt = (
        select(
            BankAccount.company_id,
            MonthlyTurnover.month,
            func.sum(MonthlyTurnover.inflow),
            func.sum(MonthlyTurnover.outflow),
            func.sum(MonthlyTurnover.closing_balance),
        )
        .join(BankAccount, BankAccount.id == MonthlyTurnover.account_id)
        .where(BankAccount.company_id.in_(company_ids))
        .group_by(BankAccount.company_id, MonthlyTurnover.month)
        .order_by(BankAccount.company_id, MonthlyTurnover.month)
    )
    rows = (await session.execute(stmt)).all()
    return [MonthTotals(*row) for row in rows]


async def company_obligations(
    session: AsyncSession, company_id: uuid.UUID
) -> list[CreditObligation]:
    """Все договоры компании из КИ, включая закрытые, — для признаков скоринга."""
    stmt = (
        select(CreditObligation)
        .where(CreditObligation.company_id == company_id)
        .order_by(CreditObligation.opened_at)
    )
    return list((await session.execute(stmt)).scalars())


async def has_own_bank_account(session: AsyncSession, company_id: uuid.UUID) -> bool:
    stmt = select(func.count(BankAccount.id)).where(
        BankAccount.company_id == company_id, BankAccount.is_own_bank.is_(True)
    )
    return (await session.execute(stmt)).scalar_one() > 0
