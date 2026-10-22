"""Кабинет: компании пользователя — поиск по ИНН, добавление, карточки и сводка по группе.

Форма ответов — контракт фронта (frontend/src/api/cabinet.ts), см. `app/types.py`.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.credit.debt import CreditMonth, Obligation, credit_by_month
from app.credit.forecast import add_months, linear_forecast
from app.credit.limit import dscr, dscr_limit
from app.enums import (
    CompanyRole,
    CompanyStatus,
    DataSource,
    FetchStatus,
    LinkStatus,
    MspCategory,
    ProductType,
    TaxRegime,
    ZskZone,
)
from app.exceptions import AlreadyExistsError, ForbiddenError, NotFoundError
from app.integrations.egrul import EgrulRecord, Person
from app.integrations.registry import Sources
from app.models import Company as CompanyModel
from app.models import DataFetch, User
from app.repositories import company as companies_repo
from app.repositories import external_data as data_repo
from app.repositories import user as users_repo
from app.services import company_data
from app.settings import settings
from app.types import (
    Company,
    CompanyCheck,
    CompanyDetails,
    CompanyLookup,
    GroupSummary,
    Loan,
    MonthFlow,
    NextPayment,
    Okved,
    OurOther,
    SourceStatus,
)

MSK = timezone(timedelta(hours=3))
HISTORY_MONTHS = 12
FORECAST_MONTHS = 3
NEEDS_STATEMENT = "Счёт открыт в другом банке — загрузите выписку за 12 месяцев"

_STATUS_TEXT = {
    CompanyStatus.ACTIVE: "Действует",
    CompanyStatus.REORGANIZING: "Реорганизация",
    CompanyStatus.LIQUIDATING: "Ликвидация",
    CompanyStatus.LIQUIDATED: "Ликвидирована",
    CompanyStatus.BANKRUPT: "Банкротство",
}
_CATEGORY = {
    MspCategory.MICRO: "micro",
    MspCategory.SMALL: "small",
    MspCategory.MEDIUM: "medium",
}
_REGIME = {
    TaxRegime.OSNO: ("ОСН", None),
    TaxRegime.USN_INCOME: ("УСН", "«доходы»"),
    TaxRegime.USN_INCOME_EXPENSE: ("УСН", "«доходы минус расходы»"),
    TaxRegime.ESHN: ("ЕСХН", None),
    TaxRegime.PSN: ("Патент", None),  # пояснение — основной вид деятельности
    TaxRegime.AUSN: ("АУСН", None),
}
_PRODUCT = {
    ProductType.TERM_LOAN: "кредит",
    ProductType.CREDIT_LINE: "кредитная линия",
    ProductType.OVERDRAFT: "овердрафт",
    ProductType.BANK_GUARANTEE: "гарантия",
}
_ZSK_TEXT = {
    ZskZone.GREEN: "Нет",
    ZskZone.YELLOW: "Жёлтая зона",
    ZskZone.RED: "Красная зона",
}
_MONTHS = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]  # fmt: skip
# Порядок и ключи источников — как в шаге «Собираем данные» на фронте
_SOURCE_KEYS = [
    (DataSource.FNS_EGRUL, "egrul", "ЕГРЮЛ"),
    (DataSource.FNS_TAX, "fns", "Налоги (ФНС)"),
    (DataSource.RMSP, "rmsp", "Реестр МСП"),
    (DataSource.FSSP, "fssp", "Приставы (ФССП)"),
    (DataSource.EFRSB, "efrsb", "Банкротства (ЕФРСБ)"),
    (DataSource.CBR_ZSK, "zsk", "Зона риска ЦБ"),
    (DataSource.BKI, "bki", "Кредитная история (БКИ)"),
    (DataSource.BANK_INTERNAL, "turnover", "Обороты по счетам"),
]


def _today() -> date:
    return datetime.now(MSK).date()


def _rub(value: Decimal) -> int:
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _fmt_rub(value: Decimal) -> str:
    return f"{_rub(value):,}".replace(",", " ") + " ₽"


def _kind(company: CompanyModel) -> str:
    return "ip" if len(company.inn) == 12 else "ul"


def _name(company: CompanyModel) -> str:
    return company.short_name or company.full_name


def _norm_fio(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def _user_fio(user: User) -> str:
    return " ".join(p for p in (user.last_name, user.first_name, user.middle_name) if p)


def _director_matches(user: User, record: EgrulRecord) -> bool:
    """Добавить можно только свою компанию: руководитель в ЕГРЮЛ = ФИО + ИНН пользователя."""
    head = record.director
    return (
        head is not None
        and head.inn == user.inn_fl
        and _norm_fio(head.full_name) == _norm_fio(_user_fio(user))
    )


async def _user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await users_repo.get_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError
    return user


async def _fetch_registry(
    session: AsyncSession, sources: Sources, inn: str, user: User
) -> tuple[CompanyModel, EgrulRecord]:
    claimant = Person(full_name=_user_fio(user), inn=user.inn_fl)
    fetched = await sources.egrul.fetch(inn, claimant)  # ошибки источника — в роут
    company = await company_data.save_registry_card(session, fetched)
    return company, fetched.data


async def _own_company(
    session: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID
) -> CompanyModel:
    company = await companies_repo.get_company(session, company_id)
    if (
        company is None
        or await companies_repo.get_link(session, user_id, company_id) is None
    ):
        raise NotFoundError  # чужая компания неотличима от несуществующей
    return company


# --- Поиск и добавление -----------------------------------------------------


async def lookup(
    session: AsyncSession, sources: Sources, user_id: uuid.UUID, inn: str
) -> CompanyLookup:
    user = await _user(session, user_id)
    company, record = await _fetch_registry(session, sources, inn, user)
    link = await companies_repo.get_link(session, user.id, company.id)
    await session.commit()
    reg = record.registration_date
    main = record.okved_main
    return CompanyLookup(
        inn=company.inn,
        kind=_kind(company),
        name=_name(company),
        registered_at=f"{_MONTHS[reg.month - 1]} {reg.year}" if reg else None,
        activity=f"{main[0]} · {main[1]}" if main else None,
        director=record.director.full_name if record.director else None,
        director_matches=_director_matches(user, record),
        already_added_id=company.id if link else None,
    )


async def add(
    session: AsyncSession, sources: Sources, user_id: uuid.UUID, inn: str
) -> CompanyDetails:
    user = await _user(session, user_id)
    company, record = await _fetch_registry(session, sources, inn, user)
    if await companies_repo.get_link(session, user.id, company.id) is not None:
        await session.rollback()
        raise AlreadyExistsError("company")
    if not _director_matches(user, record):
        await session.commit()  # карточку из реестра сохраняем, связь — нет
        raise ForbiddenError(
            "Руководитель в реестре — другой человек. "
            "Добавить компанию может только её руководитель"
        )
    await companies_repo.create_link(
        session,
        user_id=user.id,
        company_id=company.id,
        role=CompanyRole.DIRECTOR,
        status=LinkStatus.CONFIRMED,
    )
    await company_data.collect(session, sources, company)
    await session.commit()
    return await _details(session, await _facts(session, company))


# --- Факты по компании ------------------------------------------------------


@dataclass
class _Facts:
    company: CompanyModel
    months: list[data_repo.MonthTotals]  # до 24 мес по возрастанию
    loans: list[data_repo.OpenObligation]
    fetches: list[DataFetch]

    @property
    def recent(self) -> list[data_repo.MonthTotals]:
        return self.months[-HISTORY_MONTHS:]

    @property
    def income(self) -> Decimal | None:
        """Чистый поток (поступления − списания) в среднем за месяц за последние 12 мес."""
        if not self.recent:
            return None
        total = sum((m.inflow - m.outflow for m in self.recent), Decimal(0))
        return total / len(self.recent)

    @property
    def payments(self) -> Decimal:
        return sum((o.next_payment for o in self.loans), Decimal(0))

    @property
    def fetched(self) -> set[DataSource]:
        return {f.source for f in self.fetches if f.status == FetchStatus.SUCCESS}


async def _facts(session: AsyncSession, company: CompanyModel) -> _Facts:
    return _Facts(
        company=company,
        months=await data_repo.monthly_totals(session, [company.id]),
        loans=await data_repo.open_obligations(session, [company.id], _today()),
        fetches=await data_repo.latest_fetches(session, company.id),
    )


def _limit(income: Decimal, payments: Decimal) -> int:
    amount = dscr_limit(
        income,
        payments,
        settings.PRELIMINARY_RATE_PCT,
        settings.PRELIMINARY_TERM_MONTHS,
    )
    return _rub(amount)


def _product(o: data_repo.OpenObligation) -> str:
    if o.product_type is None:
        return "прочее"  # лизинг и другие договоры без типа в БКИ
    return _PRODUCT[ProductType(o.product_type)]


def _next_payment(loans: list[data_repo.OpenObligation]) -> NextPayment | None:
    upcoming = [o for o in loans if o.next_payment_date is not None]
    nearest = min(upcoming, key=lambda o: o.next_payment_date, default=None)
    if nearest is None:
        return None
    return NextPayment(
        amount=_rub(nearest.next_payment),
        date=nearest.next_payment_date,
        product=_product(nearest),
        company_id=nearest.company_id,
    )


async def _checks(session: AsyncSession, f: _Facts) -> list[CompanyCheck]:
    company = f.company
    no_data = "Нет данных"
    checks = [
        CompanyCheck(
            label="Статус в ЕГРИП" if _kind(company) == "ip" else "Статус в ЕГРЮЛ",
            value=_STATUS_TEXT[company.status],
            ok=company.status == CompanyStatus.ACTIVE,
        )
    ]

    debt = await data_repo.latest_tax_debt(session, company.id)
    total = debt.tax_debt + debt.penalties + debt.fines if debt else None
    if total is None:
        checks.append(CompanyCheck(label="Налоговый долг", value=no_data, ok=False))
    else:
        value = "Нет" if total == 0 else _fmt_rub(total)
        checks.append(CompanyCheck(label="Налоговый долг", value=value, ok=total == 0))

    if DataSource.FSSP in f.fetched:
        count, remaining = await data_repo.active_enforcements(session, company.id)
        value = "Нет производств" if count == 0 else f"{count} на {_fmt_rub(remaining)}"
        checks.append(CompanyCheck(label="ФССП", value=value, ok=count == 0))
    else:
        checks.append(CompanyCheck(label="ФССП", value=no_data, ok=False))

    if DataSource.EFRSB in f.fetched:
        events = await data_repo.count_bankruptcy_events(session, company.id)
        checks.append(
            CompanyCheck(label="Банкротства", value=str(events), ok=events == 0)
        )
    else:
        checks.append(CompanyCheck(label="Банкротства", value=no_data, ok=False))

    zsk = await data_repo.latest_zsk(session, company.id)
    checks.append(
        CompanyCheck(
            label="Зона риска ЦБ",
            value=_ZSK_TEXT[zsk.zone] if zsk else no_data,
            ok=zsk is not None and zsk.zone == ZskZone.GREEN,
        )
    )

    if DataSource.BKI in f.fetched:
        worst = await data_repo.worst_past_dpd(session, company.id)
        overdue = sum((o.overdue for o in f.loans), Decimal(0))
        if overdue > 0:
            value, ok = f"Текущая просрочка {_fmt_rub(overdue)}", False
        elif worst > 0:
            value, ok = f"Была просрочка до {worst} дн.", False
        else:
            value, ok = "Без просрочек", True
        checks.append(CompanyCheck(label="Кредитная история", value=value, ok=ok))
    else:
        checks.append(CompanyCheck(label="Кредитная история", value=no_data, ok=False))
    return checks


def _flow(
    month: date, inflow: Decimal, balance: Decimal, credit: dict[date, CreditMonth]
) -> MonthFlow:
    c = credit.get(month)
    # Выписок из других банков пока нет — всё «наше»
    return MonthFlow(
        month=f"{month:%Y-%m}",
        inflow=OurOther(our=_rub(inflow), other=0),
        balance=OurOther(our=_rub(balance), other=0),
        payments=_rub(c.payments) if c else 0,
        debt=_rub(c.debt) if c else 0,
    )


def _forecast(
    recent: list[data_repo.MonthTotals], credit: dict[date, CreditMonth]
) -> list[MonthFlow]:
    if not recent:
        return []
    last = recent[-1].month
    inflow = linear_forecast([m.inflow for m in recent], last, FORECAST_MONTHS)
    balance = linear_forecast(
        [m.closing_balance for m in recent], last, FORECAST_MONTHS
    )
    return [
        _flow(i.month, i.value, b.value, credit)
        for i, b in zip(inflow, balance, strict=True)
    ]


async def _credit(session: AsyncSession, f: _Facts) -> dict[date, CreditMonth]:
    """Платежи и долг по кредитам на месяцы графика: история и прогноз."""
    if not f.months:
        return {}
    last = f.months[-1].month
    months = [m.month for m in f.months] + [
        add_months(last, h) for h in range(1, FORECAST_MONTHS + 1)
    ]
    rows = await data_repo.open_obligation_schedules(session, f.company.id)
    obligations = [
        Obligation(
            report_date=o.report_date,
            outstanding=o.outstanding or Decimal(0),
            opened=o.opened_at,
            maturity=o.maturity_date,
            limit=o.limit_amount,
            schedule=schedule,
        )
        for o, schedule in rows
    ]
    return {c.month: c for c in credit_by_month(obligations, months)}


def _limit_and_note(f: _Facts) -> tuple[int | None, str | None]:
    status = f.company.status
    if status != CompanyStatus.ACTIVE:
        return None, f"Компания не действует: {_STATUS_TEXT[status].lower()}"
    if f.income is None:
        return None, NEEDS_STATEMENT
    return _limit(f.income, f.payments), None


async def _details(session: AsyncSession, f: _Facts) -> CompanyDetails:
    c = f.company
    income, payments = f.income, f.payments
    limit, note = _limit_and_note(f)
    okved = await companies_repo.list_company_okved(session, c.id)
    regime, regime_note = _REGIME[c.tax_regime] if c.tax_regime else (None, None)
    if c.tax_regime == TaxRegime.PSN and okved:
        regime_note = okved[0][1].lower()
    checks = await _checks(session, f)
    ratio = dscr(income, payments) if income is not None else None
    credit = await _credit(session, f)

    return CompanyDetails(
        id=c.id,
        kind=_kind(c),
        name=_name(c),
        inn=c.inn,
        registered_year=c.registration_date.year if c.registration_date else None,
        category=_CATEGORY.get(c.msp_category) if c.msp_category else None,
        tax_regime=regime,
        tax_regime_note=regime_note,
        employees=c.headcount,
        is_bank_client=bool(f.months),
        has_statement=bool(f.months),
        limit=limit,
        limit_note=note,
        debt=_rub(sum((o.outstanding for o in f.loans), Decimal(0))),
        monthly_payment=_rub(payments),
        loans_count=len(f.loans),
        dscr=round(float(ratio), 2) if ratio is not None else None,
        inflow_trend=[_rub(m.inflow) for m in f.recent],
        next_payment=_next_payment(f.loans),
        checks_ok=sum(ch.ok for ch in checks),
        checks_total=len(checks),
        checks=checks,
        okved=[Okved(code=code, title=title, main=main) for code, title, main in okved],
        loans=[
            Loan(
                id=o.id,
                lender=o.lender or "—",
                product=_product(o),
                balance=_rub(o.outstanding),
                monthly_payment=_rub(o.next_payment),
                next_payment_date=o.next_payment_date,
                overdue=o.overdue > 0,
            )
            for o in f.loans
        ],
        flows=[_flow(m.month, m.inflow, m.closing_balance, credit) for m in f.months],
        forecast=_forecast(f.recent, credit),
    )


# --- Чтение -----------------------------------------------------------------


async def list_companies(session: AsyncSession, user_id: uuid.UUID) -> list[Company]:
    rows = await companies_repo.list_user_companies(session, user_id)
    return [await _details(session, await _facts(session, c)) for c, _ in rows]


async def company_details(
    session: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID
) -> CompanyDetails:
    company = await _own_company(session, user_id, company_id)
    return await _details(session, await _facts(session, company))


async def company_sources(
    session: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID
) -> list[SourceStatus]:
    company = await _own_company(session, user_id, company_id)
    f = await _facts(session, company)
    latest = {fetch.source: fetch for fetch in f.fetches}
    statuses = []
    for source, key, label in _SOURCE_KEYS:
        if source == DataSource.FNS_EGRUL and _kind(company) == "ip":
            label = "ЕГРИП"
        fetch = latest.get(source)
        if fetch is None:
            state = "wait"
        elif fetch.status == FetchStatus.ERROR:
            state = "error"
        elif source == DataSource.BANK_INTERNAL and not f.months:
            state = "error"  # счёта в нашем банке нет — обороты даст только выписка
        else:
            state = "done"
        statuses.append(SourceStatus(key=key, label=label, state=state))
    return statuses


async def group_summary(session: AsyncSession, user_id: uuid.UUID) -> GroupSummary:
    rows = await companies_repo.list_user_companies(session, user_id)
    facts = [await _facts(session, c) for c, _ in rows]
    details = [await _details(session, f) for f in facts]

    active = [f for f in facts if f.company.status == CompanyStatus.ACTIVE]
    incomes = [f.income for f in active if f.income is not None]
    loans = [o for f in facts for o in f.loans]
    payments = sum((o.next_payment for o in loans), Decimal(0))
    missing = [d.name for d in details if not d.has_statement]
    note = f"Доход не учтён: {', '.join(missing)} — нужна выписка" if missing else None

    trend: dict[date, Decimal] = {}
    for f in facts:
        for m in f.recent:
            trend[m.month] = trend.get(m.month, Decimal(0)) + m.inflow
    months = sorted(trend)[-HISTORY_MONTHS:]

    return GroupSummary(
        limit=_limit(sum(incomes, Decimal(0)), payments) if incomes else None,
        limit_note=note,
        debt=_rub(sum((o.outstanding for o in loans), Decimal(0))),
        monthly_payments=_rub(payments),
        loans_count=len(loans),
        next_payment=_next_payment(loans),
        last_month=f"{months[-1]:%Y-%m}" if months else None,
        inflow_trend=[_rub(trend[m]) for m in months],
        checks_ok=sum(d.checks_ok for d in details),
        checks_total=sum(d.checks_total for d in details),
        companies_without_statement=len(missing),
    )
