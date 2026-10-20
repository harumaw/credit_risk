"""ORM-модели. Источник схемы — docs/schema.dbml (MVP скоринга МСП, PostgreSQL).

Группы таблиц совпадают с TableGroup схемы. Postgres-специфичные типы (jsonb, text[], inet)
объявлены с вариантом для SQLite, чтобы unit/API-тесты поднимали схему через create_all.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.enums import (
    ApplicationStatus,
    AuthProvider,
    ChannelType,
    CheckResult,
    CompanyRole,
    CompanyStatus,
    ConsentType,
    DataSource,
    DecisionType,
    DefaultTrigger,
    EventPlatform,
    FetchStatus,
    FraudLabelKind,
    LinkStatus,
    LoanStatus,
    LoanTxnType,
    ModelStatus,
    MspCategory,
    ProductType,
    ProvisionStage,
    StaffRole,
    StopSeverity,
    TaxRegime,
    UserStatus,
    ZskZone,
)

TextArray = JSON().with_variant(ARRAY(Text()), "postgresql")
InetType = String(45).with_variant(INET(), "postgresql")
BigIntType = BigInteger().with_variant(
    Integer(), "sqlite"
)  # SQLite автоинкрементит только INTEGER PK

UuidPK = Annotated[uuid.UUID, mapped_column(primary_key=True, default=uuid.uuid4)]
BigSerialPK = Annotated[
    int, mapped_column(BigIntType, primary_key=True, autoincrement=True)
]
SerialPK = Annotated[int, mapped_column(Integer, primary_key=True, autoincrement=True)]
CreatedAt = Annotated[datetime, mapped_column(server_default=func.now())]
UpdatedAt = Annotated[
    datetime, mapped_column(server_default=func.now(), onupdate=func.now())
]


def _pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    # В БД хранится value ("draft"), а не имя члена (DRAFT)
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


UserStatusType = _pg_enum(UserStatus, "user_status")
AuthProviderType = _pg_enum(AuthProvider, "auth_provider")
StaffRoleType = _pg_enum(StaffRole, "staff_role")
CompanyRoleType = _pg_enum(CompanyRole, "company_role")
LinkStatusType = _pg_enum(LinkStatus, "link_status")
CompanyStatusType = _pg_enum(CompanyStatus, "company_status")
MspCategoryType = _pg_enum(MspCategory, "msp_category")
TaxRegimeType = _pg_enum(TaxRegime, "tax_regime")
ZskZoneType = _pg_enum(ZskZone, "zsk_zone")
DataSourceType = _pg_enum(DataSource, "data_source")
FetchStatusType = _pg_enum(FetchStatus, "fetch_status")
ProductTypeType = _pg_enum(ProductType, "product_type")
ApplicationStatusType = _pg_enum(ApplicationStatus, "application_status")
ChannelTypeType = _pg_enum(ChannelType, "channel_type")
EventPlatformType = _pg_enum(EventPlatform, "event_platform")
LoanTxnTypeType = _pg_enum(LoanTxnType, "loan_txn_type")
ProvisionStageType = _pg_enum(ProvisionStage, "provision_stage")
ConsentTypeType = _pg_enum(ConsentType, "consent_type")
DecisionTypeType = _pg_enum(DecisionType, "decision_type")
LoanStatusType = _pg_enum(LoanStatus, "loan_status")
DefaultTriggerType = _pg_enum(DefaultTrigger, "default_trigger")
CheckResultType = _pg_enum(CheckResult, "check_result")
FraudLabelType = _pg_enum(FraudLabelKind, "fraud_label")
ModelStatusType = _pg_enum(ModelStatus, "model_status")
StopSeverityType = _pg_enum(StopSeverity, "stop_severity")


# ---------------------------------------------------------------------------
# 1. Идентификация и доступ
# ---------------------------------------------------------------------------


class User(Base):
    """Физлица — представители бизнеса (директор, бухгалтер)."""

    __tablename__ = "users"

    id: Mapped[UuidPK]
    esia_oid: Mapped[str | None] = mapped_column(
        String(64), unique=True
    )  # ID пользователя в ЕСИА
    inn_fl: Mapped[str | None] = mapped_column(String(12))
    # В схеме NOT NULL, но регистрация пока по email+паролю — ФИО заполняется позже
    last_name: Mapped[str | None] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    # Нет в схеме уникальности и пароля — добавлено для текущего входа по email
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[UserStatus] = mapped_column(
        UserStatusType,
        default=UserStatus.PENDING_VERIFICATION,
        server_default=UserStatus.PENDING_VERIFICATION.value,
    )
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "external_subject"),)

    id: Mapped[UuidPK]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[AuthProvider] = mapped_column(AuthProviderType)
    external_subject: Mapped[str] = mapped_column(
        String(255)
    )  # oid ЕСИА / id в банке-партнёре / thumbprint
    trust_level: Mapped[int | None] = mapped_column(SmallInteger)  # уровень учётки ЕСИА
    raw_claims: Mapped[dict[str, Any] | None]
    verified_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]


class UkepCertificate(Base):
    """Квалифицированные сертификаты (УКЭП) руководителей."""

    __tablename__ = "ukep_certificates"

    id: Mapped[UuidPK]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    thumbprint: Mapped[str] = mapped_column(String(64), unique=True)
    serial_number: Mapped[str] = mapped_column(String(64))
    issuer_cn: Mapped[str] = mapped_column(String(255))
    owner_inn_fl: Mapped[str | None] = mapped_column(String(12))
    owner_inn_ul: Mapped[str | None] = mapped_column(String(10))
    owner_ogrn: Mapped[str | None] = mapped_column(String(15))
    valid_from: Mapped[datetime]
    valid_to: Mapped[datetime]
    is_revoked: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[CreatedAt]


class Signature(Base):
    __tablename__ = "signatures"
    __table_args__ = (Index(None, "object_type", "object_id"),)

    id: Mapped[UuidPK]
    certificate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ukep_certificates.id")
    )
    object_type: Mapped[str] = mapped_column(
        String(50)
    )  # consent / application / company_link / document
    object_id: Mapped[uuid.UUID]
    payload_sha256: Mapped[str] = mapped_column(CHAR(64))
    signature_cms: Mapped[bytes] = mapped_column(
        LargeBinary
    )  # откреплённая подпись CAdES
    is_valid: Mapped[bool]
    signed_at: Mapped[datetime]


class UserSession(Base):
    """Сырьё для антифрода: устройство, IP, гео."""

    __tablename__ = "user_sessions"

    id: Mapped[UuidPK]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    auth_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auth_identities.id")
    )
    ip: Mapped[str | None] = mapped_column(InetType)
    user_agent: Mapped[str | None] = mapped_column(Text)
    device_fingerprint: Mapped[str | None] = mapped_column(String(128))
    geo: Mapped[dict[str, Any] | None]
    session_risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[CreatedAt]
    expires_at: Mapped[datetime]


class StaffUser(Base):
    """Сотрудники банка: андеррайтеры, риск-аналитики, асессоры."""

    __tablename__ = "staff_users"

    id: Mapped[UuidPK]
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[StaffRole] = mapped_column(StaffRoleType)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_at: Mapped[CreatedAt]


# ---------------------------------------------------------------------------
# 2. Компании и связи
# ---------------------------------------------------------------------------


class Company(Base):
    """Карточка юрлица/ИП (текущий срез из ЕГРЮЛ, РМСП)."""

    __tablename__ = "companies"

    id: Mapped[UuidPK]
    inn: Mapped[str] = mapped_column(String(12), unique=True)
    ogrn: Mapped[str | None] = mapped_column(String(15), unique=True)
    kpp: Mapped[str | None] = mapped_column(String(9))
    full_name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(String(500))
    legal_form: Mapped[str | None] = mapped_column(String(100))  # ООО, АО, ИП ...
    registration_date: Mapped[date | None]
    status: Mapped[CompanyStatus] = mapped_column(
        CompanyStatusType,
        default=CompanyStatus.ACTIVE,
        server_default=CompanyStatus.ACTIVE.value,
    )
    region_code: Mapped[str | None] = mapped_column(CHAR(2))
    legal_address: Mapped[str | None] = mapped_column(Text)
    msp_category: Mapped[MspCategory | None] = mapped_column(MspCategoryType)
    headcount: Mapped[int | None]  # среднесписочная численность
    tax_regime: Mapped[TaxRegime | None] = mapped_column(TaxRegimeType)
    registry_synced_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class UserCompanyLink(Base):
    """M:N директор ↔ компания."""

    __tablename__ = "user_company_links"
    __table_args__ = (UniqueConstraint("user_id", "company_id", "role"),)

    id: Mapped[UuidPK]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    role: Mapped[CompanyRole] = mapped_column(CompanyRoleType)
    status: Mapped[LinkStatus] = mapped_column(
        LinkStatusType,
        default=LinkStatus.PENDING,
        server_default=LinkStatus.PENDING.value,
    )
    # подтверждение УКЭП компании
    confirmed_signature_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signatures.id")
    )
    poa_number: Mapped[str | None] = mapped_column(
        String(100)
    )  # № машиночитаемой доверенности (МЧД)
    valid_from: Mapped[date | None]
    valid_to: Mapped[date | None]
    created_at: Mapped[CreatedAt]


class OkvedCode(Base):
    """Справочник ОКВЭД-2."""

    __tablename__ = "okved_codes"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    section: Mapped[str] = mapped_column(CHAR(1))
    parent_code: Mapped[str | None] = mapped_column(ForeignKey("okved_codes.code"))


class CompanyOkved(Base):
    """Массив ОКВЭД в нормализованном виде."""

    __tablename__ = "company_okved"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), primary_key=True
    )
    okved_code: Mapped[str] = mapped_column(
        ForeignKey("okved_codes.code"), primary_key=True
    )
    is_main: Mapped[bool] = mapped_column(default=False, server_default=false())


class CompanyPerson(Base):
    """Связанные лица из ЕГРЮЛ — для графовых признаков."""

    __tablename__ = "company_persons"

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    person_inn: Mapped[str | None] = mapped_column(String(12))
    full_name: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(30))  # director / founder / beneficiary
    share_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    date_from: Mapped[date | None]
    date_to: Mapped[date | None]
    is_mass_flag: Mapped[bool | None]  # массовый директор/учредитель


# ---------------------------------------------------------------------------
# 3. Внешние данные (point-in-time)
# ---------------------------------------------------------------------------


class DataFetch(Base):
    """Сырой слой: каждый ответ внешнего API хранится для воспроизводимости скоринга."""

    __tablename__ = "data_fetches"
    __table_args__ = (Index(None, "company_id", "source", "requested_at"),)

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    source: Mapped[DataSource] = mapped_column(DataSourceType)
    status: Mapped[FetchStatus] = mapped_column(FetchStatusType)
    requested_at: Mapped[CreatedAt]
    received_at: Mapped[datetime | None]
    raw_payload: Mapped[dict[str, Any] | None]
    payload_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    cost_rub: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2)
    )  # стоимость запроса к источнику
    error: Mapped[str | None] = mapped_column(Text)


class TaxDebt(Base):
    """Временной ряд налоговых долгов (для графика)."""

    __tablename__ = "tax_debts"
    __table_args__ = (UniqueConstraint("company_id", "as_of_date"),)

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    as_of_date: Mapped[date]
    tax_debt: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, server_default="0"
    )
    penalties: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, server_default="0"
    )
    fines: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, server_default="0"
    )
    fetch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_fetches.id"))


class RiskIndex(Base):
    __tablename__ = "risk_indices"
    __table_args__ = (
        UniqueConstraint("company_id", "provider", "index_code", "as_of_date"),
    )

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    provider: Mapped[str] = mapped_column(String(50))  # внутренний / внешний агрегатор
    index_code: Mapped[str] = mapped_column(String(50))
    value: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    as_of_date: Mapped[date]
    fetch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_fetches.id"))


class ZskStatus(Base):
    """Платформа ЦБ «Знай своего клиента»."""

    __tablename__ = "zsk_statuses"
    __table_args__ = (UniqueConstraint("company_id", "as_of_date"),)

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    zone: Mapped[ZskZone] = mapped_column(ZskZoneType)
    assigned_at: Mapped[date | None]
    as_of_date: Mapped[date]
    fetch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_fetches.id"))


class EnforcementProceeding(Base):
    """ФССП: флаг да/нет = EXISTS активных."""

    __tablename__ = "enforcement_proceedings"

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    ip_number: Mapped[str] = mapped_column(
        String(50), unique=True
    )  # № исполнительного производства
    opened_at: Mapped[date]
    closed_at: Mapped[date | None]
    close_reason: Mapped[str | None] = mapped_column(String(100))
    subject: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    remaining_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    fetch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_fetches.id"))


class BankruptcyEvent(Base):
    """ЕФРСБ / Федресурс."""

    __tablename__ = "bankruptcy_events"

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    case_number: Mapped[str | None] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(
        String(80)
    )  # намерение / наблюдение / конкурсное ...
    event_date: Mapped[date]
    is_self_initiated: Mapped[bool | None]
    fetch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_fetches.id"))


class ArbitrationCase(Base):
    __tablename__ = "arbitration_cases"
    __table_args__ = (UniqueConstraint("company_id", "case_number", "party_role"),)

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    case_number: Mapped[str] = mapped_column(String(50))
    party_role: Mapped[str] = mapped_column(
        String(20)
    )  # plaintiff / defendant / third_party
    category: Mapped[str | None] = mapped_column(String(100))
    claim_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    filed_at: Mapped[date | None]
    status: Mapped[str | None] = mapped_column(String(50))
    fetch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_fetches.id"))


# ---------------------------------------------------------------------------
# 4. Финансы, обороты, кредиты
# ---------------------------------------------------------------------------


class FinLine(Base):
    __tablename__ = "fin_line_dictionary"

    line_code: Mapped[str] = mapped_column(
        String(4), primary_key=True
    )  # 1600, 2110, 2400 ...
    name: Mapped[str] = mapped_column(Text)
    form: Mapped[str] = mapped_column(String(20))  # balance / pnl / cashflow
    parent_code: Mapped[str | None] = mapped_column(
        ForeignKey("fin_line_dictionary.line_code")
    )


class FinancialStatement(Base):
    """ГИР БО (годовая БФО)."""

    __tablename__ = "financial_statements"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year", "revision"),)

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    fiscal_year: Mapped[int] = mapped_column(SmallInteger)
    is_simplified: Mapped[bool] = mapped_column(default=False, server_default=false())
    revision: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0"
    )  # номер корректировки
    published_at: Mapped[date | None]
    fetch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_fetches.id"))


class FinancialStatementLine(Base):
    """Строки отчётности (long-формат)."""

    __tablename__ = "financial_statement_lines"

    statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_statements.id"), primary_key=True
    )
    line_code: Mapped[str] = mapped_column(
        ForeignKey("fin_line_dictionary.line_code"), primary_key=True
    )
    value_current: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    value_previous: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    bank_bik: Mapped[str] = mapped_column(String(9))
    account_masked: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(CHAR(3), default="RUB", server_default="RUB")
    is_own_bank: Mapped[bool] = mapped_column(default=False, server_default=false())
    opened_at: Mapped[date | None]
    closed_at: Mapped[date | None]


class MonthlyTurnover(Base):
    """Обороты и остатки по месяцам."""

    __tablename__ = "monthly_turnovers"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bank_accounts.id"), primary_key=True
    )
    month: Mapped[date] = mapped_column(primary_key=True)  # 1-е число месяца
    inflow: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    outflow: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    tx_count: Mapped[int | None]
    counterparties_cnt: Mapped[int | None]
    source: Mapped[DataSource] = mapped_column(DataSourceType)


class TurnoverForecast(Base):
    __tablename__ = "turnover_forecasts"

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    model_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_versions.id"))
    month: Mapped[date]
    inflow_pred: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    balance_pred: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    created_at: Mapped[CreatedAt]


class CreditObligation(Base):
    """Кредиты, задолженность (КИ + внутренние)."""

    __tablename__ = "credit_obligations"

    id: Mapped[UuidPK]
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    source: Mapped[DataSource] = mapped_column(DataSourceType)  # bki / bank_internal
    deal_uid: Mapped[str | None] = mapped_column(String(40))  # УИд сделки из КИ
    lender_name: Mapped[str | None] = mapped_column(String(300))
    product_type: Mapped[ProductType | None] = mapped_column(ProductTypeType)
    limit_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    currency: Mapped[str | None] = mapped_column(
        CHAR(3), default="RUB", server_default="RUB"
    )
    opened_at: Mapped[date | None]
    maturity_date: Mapped[date | None]
    closed_at: Mapped[date | None]
    outstanding: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    overdue_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    max_dpd: Mapped[int | None]
    report_date: Mapped[date]
    fetch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_fetches.id"))


class ObligationPayment(Base):
    __tablename__ = "obligation_payments"

    id: Mapped[BigSerialPK]
    obligation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("credit_obligations.id")
    )
    due_date: Mapped[date]
    paid_date: Mapped[date | None]
    amount_due: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    amount_paid: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    dpd: Mapped[int] = mapped_column(default=0, server_default="0")


# ---------------------------------------------------------------------------
# 5. Заявки (CRM)
# ---------------------------------------------------------------------------


class CreditProduct(Base):
    __tablename__ = "credit_products"

    id: Mapped[SerialPK]
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    product_type: Mapped[ProductType] = mapped_column(ProductTypeType)
    min_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    min_term_months: Mapped[int | None] = mapped_column(SmallInteger)
    max_term_months: Mapped[int | None] = mapped_column(SmallInteger)
    base_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class LoanApplication(Base):
    __tablename__ = "loan_applications"
    __table_args__ = (Index(None, "company_id", "status"),)

    id: Mapped[UuidPK]
    number: Mapped[str] = mapped_column(String(20), unique=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    applicant_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("credit_products.id"))
    requested_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    requested_term_months: Mapped[int | None] = mapped_column(SmallInteger)
    purpose: Mapped[str | None] = mapped_column(Text)
    form_step: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default="1"
    )  # шаг progress-bar
    form_data: Mapped[dict[str, Any] | None]  # черновик формы
    status: Mapped[ApplicationStatus] = mapped_column(
        ApplicationStatusType,
        default=ApplicationStatus.DRAFT,
        server_default=ApplicationStatus.DRAFT.value,
    )
    # last non-direct touch перед созданием заявки
    acquisition_channel_code: Mapped[str | None] = mapped_column(
        ForeignKey("marketing_channels.code")
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("marketing_campaigns.id")
    )
    utm: Mapped[dict[str, Any] | None]
    assigned_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id")
    )
    submitted_at: Mapped[datetime | None]
    decided_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class ApplicationStatusHistory(Base):
    """Таймлайн статусов в ЛК + SLA."""

    __tablename__ = "application_status_history"

    id: Mapped[BigSerialPK]
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    from_status: Mapped[ApplicationStatus | None] = mapped_column(ApplicationStatusType)
    to_status: Mapped[ApplicationStatus] = mapped_column(ApplicationStatusType)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    changed_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[CreatedAt]


class ApplicationDocument(Base):
    __tablename__ = "application_documents"

    id: Mapped[UuidPK]
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    doc_type: Mapped[str] = mapped_column(String(50))
    file_key: Mapped[str] = mapped_column(Text)  # ключ в хранилище файлов
    sha256: Mapped[str] = mapped_column(CHAR(64))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    signature_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signatures.id"))
    uploaded_at: Mapped[CreatedAt]


class Collateral(Base):
    __tablename__ = "collaterals"

    id: Mapped[UuidPK]
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    collateral_type: Mapped[str] = mapped_column(
        String(30)
    )  # real_estate / vehicle / surety / guarantee
    description: Mapped[str | None] = mapped_column(Text)
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    guarantor_inn: Mapped[str | None] = mapped_column(String(12))


class Consent(Base):
    """Согласия: ПДн (152-ФЗ), запрос в БКИ (218-ФЗ), налоговая тайна."""

    __tablename__ = "consents"

    id: Mapped[UuidPK]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    consent_type: Mapped[ConsentType] = mapped_column(ConsentTypeType)
    text_version: Mapped[str] = mapped_column(String(20))
    signature_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signatures.id"))
    signed_at: Mapped[datetime]
    valid_until: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class CreditDecision(Base):
    __tablename__ = "credit_decisions"

    id: Mapped[UuidPK]
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    score_result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("score_results.id")
    )
    decision: Mapped[DecisionType] = mapped_column(DecisionTypeType)
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    approved_term_months: Mapped[int | None] = mapped_column(SmallInteger)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    reason_codes: Mapped[list[str] | None] = mapped_column(TextArray)
    offer_expires_at: Mapped[datetime | None]
    offer_accepted_at: Mapped[datetime | None]
    # NULL = автоматическое решение
    decided_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[CreatedAt]


class StaffWorkLog(Base):
    """Трудоёмкость → себестоимость обработки заявки."""

    __tablename__ = "staff_work_log"
    __table_args__ = (Index(None, "staff_id", "started_at"),)

    id: Mapped[UuidPK]
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_users.id"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    assessor_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessor_tasks.id")
    )
    activity: Mapped[str] = mapped_column(
        String(30)
    )  # review / doc_check / call / fraud_review
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    duration_sec: Mapped[int | None]  # фактическое рабочее время, без ожидания


# ---------------------------------------------------------------------------
# 6. Антифрод и разметка
# ---------------------------------------------------------------------------


class FraudCheck(Base):
    __tablename__ = "fraud_checks"

    id: Mapped[UuidPK]
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_sessions.id"))
    check_code: Mapped[str] = mapped_column(
        String(50)
    )  # device_reuse / mass_director / partner_bank_blacklist ...
    result: Mapped[CheckResult] = mapped_column(CheckResultType)
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    details: Mapped[dict[str, Any] | None]
    checked_at: Mapped[CreatedAt]


class AssessorTask(Base):
    __tablename__ = "assessor_tasks"

    id: Mapped[UuidPK]
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    assigned_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id")
    )
    priority: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    sampling_reason: Mapped[str | None] = mapped_column(
        String(30)
    )  # flagged / random_sample / disputed
    created_at: Mapped[CreatedAt]
    completed_at: Mapped[datetime | None]


class FraudLabel(Base):
    """Асессорская разметка → таргет антифрод-модели."""

    __tablename__ = "fraud_labels"

    id: Mapped[UuidPK]
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessor_tasks.id"))
    label: Mapped[FraudLabelKind] = mapped_column(FraudLabelType)
    fraud_type: Mapped[str | None] = mapped_column(
        String(50)
    )  # nominee / identity_theft / shell ...
    comment: Mapped[str | None] = mapped_column(Text)
    labeled_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_users.id"))
    labeled_at: Mapped[CreatedAt]


# ---------------------------------------------------------------------------
# 7. Скоринг и модели
# ---------------------------------------------------------------------------


class FeatureDefinition(Base):
    """Feature store: каталог признаков."""

    __tablename__ = "feature_definitions"

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(
        String(20)
    )  # numeric / categorical / boolean
    source: Mapped[DataSource] = mapped_column(DataSourceType)
    sql_or_formula: Mapped[str | None] = mapped_column(Text)  # как считается
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_name", "version"),)

    id: Mapped[UuidPK]
    model_name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(20))
    model_type: Mapped[str] = mapped_column(
        String(30)
    )  # scorecard / logreg / gbm / forecast
    segment_code: Mapped[str | None] = mapped_column(
        String(30)
    )  # micro / small / medium / new_company
    status: Mapped[ModelStatus] = mapped_column(
        ModelStatusType,
        default=ModelStatus.DEVELOPMENT,
        server_default=ModelStatus.DEVELOPMENT.value,
    )
    target_definition: Mapped[str] = mapped_column(Text)  # напр. 90+ dpd за 12 мес.
    train_from: Mapped[date | None]
    train_to: Mapped[date | None]
    oot_from: Mapped[date | None]
    oot_to: Mapped[date | None]
    gini_train: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    gini_oot: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    ks_oot: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    cutoff_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    artifact_uri: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_users.id"))
    created_at: Mapped[CreatedAt]


class ModelFeature(Base):
    __tablename__ = "model_features"

    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id"), primary_key=True
    )
    feature_code: Mapped[str] = mapped_column(
        ForeignKey("feature_definitions.code"), primary_key=True
    )
    coefficient: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    information_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))


class ScorecardBin(Base):
    """Бины карты: WoE и баллы."""

    __tablename__ = "scorecard_bins"
    __table_args__ = (
        UniqueConstraint("model_version_id", "feature_code", "bin_order"),
    )

    id: Mapped[UuidPK]
    model_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_versions.id"))
    feature_code: Mapped[str] = mapped_column(ForeignKey("feature_definitions.code"))
    bin_order: Mapped[int] = mapped_column(SmallInteger)
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric)
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric)
    categories: Mapped[list[str] | None] = mapped_column(TextArray)
    is_missing_bin: Mapped[bool] = mapped_column(default=False, server_default=false())
    woe: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    points: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    event_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    population_share: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))


class RatingScale(Base):
    """Мастер-шкала: балл → грейд → PD."""

    __tablename__ = "rating_scale"
    __table_args__ = (UniqueConstraint("model_version_id", "grade"),)

    id: Mapped[SerialPK]
    model_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_versions.id"))
    grade: Mapped[str] = mapped_column(String(5))
    score_from: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    score_to: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    pd_calibrated: Mapped[Decimal] = mapped_column(Numeric(7, 6))


class StopFactor(Base):
    """ZSK_RED, BANKRUPTCY_PROC, FSSP_OVER_X, AGE_LT_6M ..."""

    __tablename__ = "stop_factors"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    severity: Mapped[StopSeverity] = mapped_column(StopSeverityType)
    rule_expression: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class ScoreResult(Base):
    __tablename__ = "score_results"
    __table_args__ = (Index(None, "company_id", "calculated_at"),)

    id: Mapped[UuidPK]
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    model_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_versions.id"))
    as_of_date: Mapped[date]  # дата среза данных
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pd: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    grade: Mapped[str | None] = mapped_column(String(5))
    has_hard_stop: Mapped[bool] = mapped_column(default=False, server_default=false())
    input_sha256: Mapped[str | None] = mapped_column(
        CHAR(64)
    )  # хэш входа для воспроизводимости
    latency_ms: Mapped[int | None]
    calculated_at: Mapped[CreatedAt]


class ScoreFeatureValue(Base):
    """Объяснимость: вклад каждого признака."""

    __tablename__ = "score_feature_values"

    score_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("score_results.id"), primary_key=True
    )
    feature_code: Mapped[str] = mapped_column(
        ForeignKey("feature_definitions.code"), primary_key=True
    )
    value_num: Mapped[Decimal | None] = mapped_column(Numeric)
    value_text: Mapped[str | None] = mapped_column(Text)
    bin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scorecard_bins.id"))
    points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))


class StopFactorResult(Base):
    __tablename__ = "stop_factor_results"

    score_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("score_results.id"), primary_key=True
    )
    stop_factor_code: Mapped[str] = mapped_column(
        ForeignKey("stop_factors.code"), primary_key=True
    )
    triggered: Mapped[bool]
    details: Mapped[dict[str, Any] | None]


class ModelMonitoring(Base):
    __tablename__ = "model_monitoring"
    __table_args__ = (UniqueConstraint("model_version_id", "period_month"),)

    id: Mapped[UuidPK]
    model_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_versions.id"))
    period_month: Mapped[date]
    population_cnt: Mapped[int]
    approval_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    psi: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    gini: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    default_rate_obs: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    pd_avg_pred: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    created_at: Mapped[CreatedAt]


class RiskParameter(Base):
    """LGD/CCF для ожидаемых потерь EL = PD × LGD × EAD."""

    __tablename__ = "risk_parameters"
    __table_args__ = (
        UniqueConstraint("param_code", "segment_code", "product_type", "valid_from"),
    )

    id: Mapped[SerialPK]
    param_code: Mapped[str] = mapped_column(String(30))  # LGD / CCF
    segment_code: Mapped[str] = mapped_column(
        String(30), default="all", server_default="all"
    )
    product_type: Mapped[ProductType | None] = mapped_column(ProductTypeType)
    value: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    valid_from: Mapped[date]
    valid_to: Mapped[date | None]
    comment: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# 8. Портфель и дефолты
# ---------------------------------------------------------------------------


class Loan(Base):
    """Выданные кредиты (для сбора таргета)."""

    __tablename__ = "loans"

    id: Mapped[UuidPK]
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loan_applications.id"), unique=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    contract_number: Mapped[str] = mapped_column(String(50), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    term_months: Mapped[int] = mapped_column(SmallInteger)
    issued_at: Mapped[date]
    maturity_date: Mapped[date]
    status: Mapped[LoanStatus] = mapped_column(
        LoanStatusType,
        default=LoanStatus.ACTIVE,
        server_default=LoanStatus.ACTIVE.value,
    )


class LoanMonthlyPerformance(Base):
    """Помесячный срез → матрицы переходов (roll-rate)."""

    __tablename__ = "loan_monthly_performance"

    loan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("loans.id"), primary_key=True)
    report_month: Mapped[date] = mapped_column(primary_key=True)
    mob: Mapped[int] = mapped_column(
        SmallInteger
    )  # month on book — для винтажей/когорт
    outstanding: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    dpd: Mapped[int] = mapped_column(default=0, server_default="0")
    dpd_bucket: Mapped[str] = mapped_column(String(8))  # 0 / 1-30 / 31-60 / 61-90 / 90+
    is_restructured: Mapped[bool] = mapped_column(default=False, server_default=false())


class DefaultEvent(Base):
    """Единое определение дефолта (таргет)."""

    __tablename__ = "default_events"

    id: Mapped[UuidPK]
    loan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("loans.id"))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    trigger: Mapped[DefaultTrigger] = mapped_column(DefaultTriggerType)
    default_date: Mapped[date]
    cured_at: Mapped[date | None]


# ---------------------------------------------------------------------------
# 9. Аудит
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """Append-only журнал действий."""

    __tablename__ = "audit_log"
    __table_args__ = (Index(None, "entity_type", "entity_id"),)

    id: Mapped[BigSerialPK]
    actor_type: Mapped[str] = mapped_column(String(10))  # user / staff / system
    actor_id: Mapped[uuid.UUID | None]
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None]
    diff: Mapped[dict[str, Any] | None]
    ip: Mapped[str | None] = mapped_column(InetType)
    created_at: Mapped[CreatedAt]


# ---------------------------------------------------------------------------
# 10. Продуктовая аналитика и маркетинг
# ---------------------------------------------------------------------------


class MarketingChannel(Base):
    """Справочник каналов привлечения."""

    __tablename__ = "marketing_channels"

    code: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # yandex_direct / seo / partner_bank_x / referral
    name: Mapped[str] = mapped_column(String(200))
    channel_type: Mapped[ChannelType] = mapped_column(ChannelTypeType)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"
    __table_args__ = (UniqueConstraint("channel_code", "utm_campaign"),)

    id: Mapped[UuidPK]
    channel_code: Mapped[str] = mapped_column(ForeignKey("marketing_channels.code"))
    utm_campaign: Mapped[str] = mapped_column(String(200))
    name: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[date | None]
    ended_at: Mapped[date | None]


class MarketingSpend(Base):
    """Расходы по дням → CAC / CPA."""

    __tablename__ = "marketing_spend"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("marketing_campaigns.id"), primary_key=True
    )
    spend_date: Mapped[date] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    clicks: Mapped[int | None] = mapped_column(BigInteger)


class Partner(Base):
    __tablename__ = "partners"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    partner_type: Mapped[str] = mapped_column(String(30))  # bank / marketplace / agent
    commission_model: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class PartnerReferral(Base):
    __tablename__ = "partner_referrals"

    id: Mapped[UuidPK]
    partner_code: Mapped[str] = mapped_column(ForeignKey("partners.code"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    external_ref: Mapped[str | None] = mapped_column(String(100))
    referred_at: Mapped[datetime]
    commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    commission_paid_at: Mapped[date | None]


class AnalyticsEvent(Base):
    """Сырые продуктовые события; в Postgres — партиционирование по месяцам."""

    __tablename__ = "analytics_events"
    __table_args__ = (
        Index(None, "event_name", "event_ts"),
        Index(None, "anonymous_id"),
        Index(None, "company_id", "event_ts"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_ts: Mapped[datetime] = mapped_column(primary_key=True)  # время на клиенте
    received_at: Mapped[CreatedAt]
    event_name: Mapped[str] = mapped_column(
        String(80)
    )  # application_start, form_step_completed ...
    anonymous_id: Mapped[str | None] = mapped_column(String(64))  # cookie / device id
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("loan_applications.id")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_sessions.id"))
    platform: Mapped[EventPlatform] = mapped_column(EventPlatformType)
    app_version: Mapped[str | None] = mapped_column(String(20))
    page: Mapped[str | None] = mapped_column(Text)
    referrer: Mapped[str | None] = mapped_column(Text)
    utm_source: Mapped[str | None] = mapped_column(String(200))
    utm_medium: Mapped[str | None] = mapped_column(String(200))
    utm_campaign: Mapped[str | None] = mapped_column(String(200))
    utm_content: Mapped[str | None] = mapped_column(String(200))
    utm_term: Mapped[str | None] = mapped_column(String(200))
    properties: Mapped[
        dict[str, Any] | None
    ]  # шаг формы, блок дашборда, поле автозаполнения ...


class IdentityLink(Base):
    """Склейка anonymous_id → user_id при входе."""

    __tablename__ = "identity_links"

    anonymous_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    first_seen_at: Mapped[datetime]
    linked_at: Mapped[CreatedAt]


class CompanyAttribution(Base):
    """First-touch канал компании (по самому раннему касанию любого её пользователя)."""

    __tablename__ = "company_attribution"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), primary_key=True
    )
    first_touch_channel_code: Mapped[str | None] = mapped_column(
        ForeignKey("marketing_channels.code")
    )
    first_touch_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("marketing_campaigns.id")
    )
    first_touch_at: Mapped[datetime | None]
    first_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    attributed_at: Mapped[CreatedAt]


# ---------------------------------------------------------------------------
# 11. Деньги, резервы, план
# ---------------------------------------------------------------------------


class LoanSchedule(Base):
    """График платежей → точный FPD и DPD."""

    __tablename__ = "loan_schedule"

    loan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("loans.id"), primary_key=True)
    installment_no: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    due_date: Mapped[date]
    principal_due: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    interest_due: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class LoanTransaction(Base):
    """Фактические денежные потоки по кредиту."""

    __tablename__ = "loan_transactions"
    __table_args__ = (Index(None, "loan_id", "txn_date"),)

    id: Mapped[BigSerialPK]
    loan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("loans.id"))
    txn_type: Mapped[LoanTxnType] = mapped_column(LoanTxnTypeType)
    txn_date: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    installment_no: Mapped[int | None] = mapped_column(SmallInteger)
    external_ref: Mapped[str | None] = mapped_column(String(100))  # id проводки в АБС
    created_at: Mapped[CreatedAt]


class FundingRate(Base):
    __tablename__ = "funding_rates"
    __table_args__ = (
        UniqueConstraint("term_months_from", "term_months_to", "valid_from"),
    )

    id: Mapped[SerialPK]
    term_months_from: Mapped[int] = mapped_column(SmallInteger)
    term_months_to: Mapped[int] = mapped_column(SmallInteger)
    rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 3)
    )  # % годовых, трансфертная ставка (FTP)
    valid_from: Mapped[date]
    valid_to: Mapped[date | None]


class LoanProvision(Base):
    """Резервы на конец месяца → cost of risk."""

    __tablename__ = "loan_provisions"

    loan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("loans.id"), primary_key=True)
    report_month: Mapped[date] = mapped_column(primary_key=True)
    stage: Mapped[ProvisionStage] = mapped_column(ProvisionStageType)
    provision_rate: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    provision_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class PlanTarget(Base):
    """План для плиток «план/факт»."""

    __tablename__ = "plan_targets"
    __table_args__ = (UniqueConstraint("metric_code", "period_month", "segment"),)

    id: Mapped[SerialPK]
    metric_code: Mapped[str] = mapped_column(
        String(80)
    )  # issued_amount / approval_rate / cac ...
    period_month: Mapped[date]
    segment: Mapped[str] = mapped_column(
        String(50), default="all", server_default="all"
    )
    target_value: Mapped[Decimal] = mapped_column(Numeric(20, 4))
