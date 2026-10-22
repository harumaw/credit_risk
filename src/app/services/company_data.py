"""Сбор данных компании из внешних источников: снимок ответа → data_fetches, разбор → таблицы."""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import CompanyRole, DataSource, FetchStatus, MspCategory
from app.integrations.abs import AbsRecord
from app.integrations.base import (
    Fetched,
    SourceClient,
    SourceNotFoundError,
    SourceUnavailableError,
)
from app.integrations.bki import BkiReport
from app.integrations.efrsb import BankruptcyMessage
from app.integrations.egrul import EgrulRecord
from app.integrations.fns import FnsRecord
from app.integrations.fssp import Proceeding
from app.integrations.registry import Sources
from app.integrations.rmsp import RmspRecord
from app.integrations.zsk import ZskRecord
from app.models import (
    BankAccount,
    BankruptcyEvent,
    Company,
    CompanyPerson,
    CreditObligation,
    DataFetch,
    EnforcementProceeding,
    MonthlyTurnover,
    ObligationPayment,
    TaxDebt,
    ZskStatus,
)
from app.repositories import company as companies_repo
from app.repositories import external_data as data_repo

# Разделы ОКВЭД-2 по первым двум цифрам кода (класс → раздел)
_OKVED_SECTIONS = [
    (3, "A"), (9, "B"), (33, "C"), (35, "D"), (39, "E"), (43, "F"), (47, "G"),
    (53, "H"), (56, "I"), (63, "J"), (66, "K"), (68, "L"), (75, "M"), (82, "N"),
    (84, "O"), (85, "P"), (88, "Q"), (93, "R"), (96, "S"), (98, "T"), (99, "U"),
]  # fmt: skip


def okved_section(code: str) -> str:
    division = int(code.split(".")[0])
    return next(section for last, section in _OKVED_SECTIONS if division <= last)


def _now() -> datetime:
    return datetime.now(UTC)


def _sha256(raw: dict[str, Any]) -> str:
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _save_fetch(
    session: AsyncSession,
    company_id,
    source: DataSource,
    status: FetchStatus,
    raw: dict[str, Any] | None = None,
    error: str | None = None,
) -> DataFetch:
    return await data_repo.add_fetch(
        session,
        DataFetch(
            company_id=company_id,
            source=source,
            status=status,
            received_at=_now() if status != FetchStatus.ERROR else None,
            raw_payload=raw,
            payload_sha256=_sha256(raw) if raw is not None else None,
            error=error,
        ),
    )


# --- ЕГРЮЛ: карточка компании ------------------------------------------------


async def save_registry_card(
    session: AsyncSession, fetched: Fetched[EgrulRecord]
) -> Company:
    """Создаёт или обновляет компанию по выписке ЕГРЮЛ/ЕГРИП и сохраняет снимок."""
    r = fetched.data
    company = await companies_repo.get_company_by_inn(session, r.inn)
    if company is None:
        company = await companies_repo.add_company(
            session, Company(inn=r.inn, full_name=r.full_name)
        )
    company.ogrn = r.ogrn
    company.kpp = r.kpp
    company.full_name = r.full_name
    company.short_name = r.short_name
    company.legal_form = r.legal_form
    company.registration_date = r.registration_date
    company.status = r.status
    company.region_code = r.region_code
    company.legal_address = r.address
    company.registry_synced_at = _now()

    okveds = [(r.okved_main, True)] if r.okved_main else []
    okveds += [(o, False) for o in r.okved_extra if o]
    await companies_repo.ensure_okved_codes(
        session, [(code, name, okved_section(code)) for (code, name), _ in okveds]
    )
    await companies_repo.replace_company_okved(
        session, company.id, [(code, is_main) for (code, _), is_main in okveds]
    )

    persons = []
    if r.director is not None and not r.is_ip:
        persons.append(
            CompanyPerson(
                company_id=company.id,
                person_inn=r.director.inn,
                full_name=r.director.full_name,
                role=CompanyRole.DIRECTOR.value,
            )
        )
    persons += [
        CompanyPerson(
            company_id=company.id,
            person_inn=f.inn,
            full_name=f.full_name,
            role=CompanyRole.FOUNDER.value,
            share_pct=f.share_pct,
        )
        for f in r.founders
    ]
    await companies_repo.replace_company_persons(session, company.id, persons)
    await _save_fetch(
        session, company.id, DataSource.FNS_EGRUL, FetchStatus.SUCCESS, fetched.raw
    )
    return company


# --- Остальные источники ----------------------------------------------------


async def _apply_fns(session, company: Company, fetch: DataFetch, r: FnsRecord):
    company.tax_regime = r.tax_regime
    await data_repo.upsert_tax_debt(
        session,
        TaxDebt(
            company_id=company.id,
            as_of_date=r.as_of,
            tax_debt=r.tax_debt,
            penalties=r.penalties,
            fines=r.fines,
            fetch_id=fetch.id,
        ),
    )


async def _apply_rmsp(session, company: Company, fetch: DataFetch, r: RmspRecord):
    company.msp_category = r.category
    company.headcount = r.headcount


async def _apply_fssp(session, company, fetch: DataFetch, rows: list[Proceeding]):
    await data_repo.upsert_enforcements(
        session,
        [
            EnforcementProceeding(
                company_id=company.id,
                ip_number=p.number,
                opened_at=p.opened_at,
                closed_at=p.closed_at,
                close_reason=p.close_reason,
                subject=p.subject,
                amount=p.amount,
                remaining_amount=p.remaining,
                fetch_id=fetch.id,
            )
            for p in rows
        ],
    )


async def _apply_efrsb(session, company, fetch, rows: list[BankruptcyMessage]):
    await data_repo.replace_bankruptcy_events(
        session,
        company.id,
        [
            BankruptcyEvent(
                company_id=company.id,
                case_number=m.case_number,
                event_type=m.event_type,
                event_date=m.event_date,
                is_self_initiated=m.is_self_initiated,
                fetch_id=fetch.id,
            )
            for m in rows
        ],
    )


async def _apply_zsk(session, company, fetch: DataFetch, r: ZskRecord):
    await data_repo.upsert_zsk(
        session,
        ZskStatus(
            company_id=company.id,
            zone=r.zone,
            assigned_at=r.assigned_at,
            as_of_date=r.as_of,
            fetch_id=fetch.id,
        ),
    )


async def _apply_bki(session, company, fetch: DataFetch, r: BkiReport):
    obligations = [
        (
            CreditObligation(
                company_id=company.id,
                source=DataSource.BKI,
                deal_uid=a.deal_uid,
                lender_name=a.lender,
                product_type=a.product_type,
                limit_amount=a.limit,
                currency=a.currency,
                opened_at=a.opened_at,
                maturity_date=a.maturity_date,
                closed_at=a.closed_at,
                outstanding=a.outstanding,
                overdue_amount=a.overdue,
                max_dpd=a.max_dpd,
                payment_string=a.payment_string or None,
                report_date=r.report_date,
                fetch_id=fetch.id,
            ),
            [
                ObligationPayment(due_date=p.due_date, amount_due=p.amount)
                for p in a.schedule
            ],
        )
        for a in r.accounts
    ]
    await data_repo.replace_obligations(
        session, company.id, DataSource.BKI, obligations
    )


async def _apply_abs(session, company, fetch: DataFetch, r: AbsRecord):
    accounts = {}
    for a in r.accounts:
        accounts[a.account_masked] = await data_repo.get_or_create_account(
            session,
            company.id,
            BankAccount(
                company_id=company.id,
                bank_bik=a.bik,
                account_masked=a.account_masked,
                currency=a.currency,
                is_own_bank=True,
                opened_at=a.opened_at,
            ),
        )
    await data_repo.upsert_turnovers(
        session,
        [
            MonthlyTurnover(
                account_id=accounts[m.account_masked].id,
                month=m.month,
                inflow=m.inflow,
                outflow=m.outflow,
                closing_balance=m.closing_balance,
                tx_count=m.tx_count,
                counterparties_cnt=m.counterparties,
                source=DataSource.BANK_INTERNAL,
            )
            for m in r.months
            if m.account_masked in accounts
        ],
    )


async def _not_msp(session, company: Company) -> None:
    company.msp_category = MspCategory.NOT_MSP


Apply = Callable[[AsyncSession, Company, DataFetch, Any], Awaitable[None]]


def _steps(sources: Sources) -> list[tuple[SourceClient, Apply]]:
    return [
        (sources.fns, _apply_fns),
        (sources.rmsp, _apply_rmsp),
        (sources.fssp, _apply_fssp),
        (sources.efrsb, _apply_efrsb),
        (sources.zsk, _apply_zsk),
        (sources.bki, _apply_bki),
        (sources.abs, _apply_abs),
    ]


async def _safe_fetch(client: SourceClient, inn: str) -> Fetched | Exception:
    try:
        return await client.fetch(inn)  # type: ignore[attr-defined]
    except (SourceNotFoundError, SourceUnavailableError) as exc:
        return exc


async def collect(
    session: AsyncSession, sources: Sources, company: Company
) -> list[DataFetch]:
    """Опрашивает все источники параллельно; сбой одного не мешает остальным."""
    steps = _steps(sources)
    results = await asyncio.gather(
        *(_safe_fetch(client, company.inn) for client, _ in steps)
    )
    fetches = []
    for (client, apply), result in zip(steps, results, strict=True):
        if isinstance(result, SourceNotFoundError):
            fetch = await _save_fetch(
                session, company.id, client.source, FetchStatus.NOT_FOUND
            )
            if client.source == DataSource.RMSP:
                await _not_msp(session, company)
        elif isinstance(result, Exception):
            fetch = await _save_fetch(
                session, company.id, client.source, FetchStatus.ERROR, error=str(result)
            )
        else:
            fetch = await _save_fetch(
                session, company.id, client.source, FetchStatus.SUCCESS, result.raw
            )
            await apply(session, company, fetch, result.data)
        fetches.append(fetch)
    await session.flush()
    return fetches
