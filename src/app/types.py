import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)
from pydantic.alias_generators import to_camel

from app.enums import UserStatus

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]

_INN_FL_WEIGHTS_11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN_FL_WEIGHTS_12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _inn_check_digit(digits: list[int], weights: tuple[int, ...]) -> int:
    return sum(d * w for d, w in zip(digits, weights, strict=False)) % 11 % 10


def validate_inn_fl(value: str) -> str:
    """ИНН физлица: 12 цифр, две контрольные цифры (алгоритм ФНС)."""
    value = value.strip()
    if not re.fullmatch(r"\d{12}", value):
        raise ValueError("ИНН физлица — 12 цифр")
    digits = [int(c) for c in value]
    if (
        _inn_check_digit(digits[:10], _INN_FL_WEIGHTS_11) != digits[10]
        or _inn_check_digit(digits[:11], _INN_FL_WEIGHTS_12) != digits[11]
    ):
        raise ValueError("Неверный ИНН: не сходится контрольная сумма")
    return value


def normalize_phone(value: str) -> str:
    """Приводит российский номер к виду +7XXXXXXXXXX."""
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    raise ValueError("Телефон в формате +7XXXXXXXXXX")


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    last_name: Name
    first_name: Name
    middle_name: Name | None = None
    inn_fl: str
    phone: str | None = None

    @field_validator("middle_name", "phone", mode="before")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        # Пустое поле формы = «не указано»
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("inn_fl")
    @classmethod
    def _check_inn(cls, value: str) -> str:
        return validate_inn_fl(value)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        return None if value is None else normalize_phone(value)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: uuid.UUID
    email: str | None
    last_name: str
    first_name: str
    middle_name: str | None
    inn_fl: str | None
    phone: str | None
    status: UserStatus

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Кабинет: компании
# ---------------------------------------------------------------------------

_INN_UL_WEIGHTS = (2, 4, 10, 3, 5, 9, 4, 6, 8)


def validate_company_inn(value: str) -> str:
    """ИНН компании (10 цифр) или ИП (12 цифр) с контрольными цифрами."""
    value = value.strip()
    if re.fullmatch(r"\d{12}", value):
        return validate_inn_fl(value)
    if not re.fullmatch(r"\d{10}", value):
        raise ValueError("ИНН — 10 цифр у компании или 12 у ИП")
    digits = [int(c) for c in value]
    if _inn_check_digit(digits[:9], _INN_UL_WEIGHTS) != digits[9]:
        raise ValueError("Неверный ИНН: не сходится контрольная сумма")
    return value


CompanyKind = Literal["ul", "ip"]
SmeCategory = Literal["micro", "small", "medium"]
SourceState = Literal["done", "work", "wait", "error"]


class InnRequest(BaseModel):
    inn: str

    @field_validator("inn")
    @classmethod
    def _check_inn(cls, value: str) -> str:
        return validate_company_inn(value)


class CamelModel(BaseModel):
    """Ответы кабинета в camelCase — так их описывает фронт (frontend/src/api/cabinet.ts)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NextPayment(CamelModel):
    amount: int
    date: date
    product: str
    company_id: uuid.UUID


class Company(CamelModel):
    """Карточка компании в списке и переключателе."""

    id: uuid.UUID
    kind: CompanyKind
    name: str
    inn: str
    registered_year: int | None
    category: SmeCategory | None  # None — не субъект МСП
    tax_regime: str | None
    tax_regime_note: str | None
    employees: int | None
    is_bank_client: bool
    has_statement: bool  # есть обороты (наш счёт или выписка)
    limit: int | None  # предварительный лимит; None — посчитать пока нельзя
    limit_note: str | None  # почему лимита нет / что учтено
    debt: int
    monthly_payment: int
    loans_count: int
    dscr: float | None  # доход / платежи по кредитам
    inflow_trend: list[int]  # поступления за последние 12 мес по возрастанию
    next_payment: NextPayment | None
    checks_ok: int
    checks_total: int


class CompanyCheck(CamelModel):
    label: str
    value: str
    ok: bool


class Okved(CamelModel):
    code: str
    title: str
    main: bool


class Loan(CamelModel):
    id: uuid.UUID
    lender: str
    product: str
    balance: int
    monthly_payment: int
    next_payment_date: date | None
    overdue: bool


class OurOther(CamelModel):
    our: int  # наш банк
    other: int  # другие банки (по выписке)


class MonthFlow(CamelModel):
    month: str  # "2026-09"
    inflow: OurOther
    balance: OurOther
    payments: int  # плановые платежи по кредитам за месяц (до отчёта КИ — оценка)
    debt: int  # долг по кредитам на конец месяца (до отчёта КИ — оценка)


class CompanyDetails(Company):
    checks: list[CompanyCheck]
    okved: list[Okved]
    loans: list[Loan]
    flows: list[MonthFlow]  # до 24 последних полных месяцев по возрастанию
    forecast: list[MonthFlow]  # 3 месяца вперёд


class GroupSummary(CamelModel):
    limit: int | None  # лимит по DSCR с учётом долгов всех компаний
    limit_note: str | None
    debt: int
    monthly_payments: int
    loans_count: int
    next_payment: NextPayment | None
    last_month: str | None  # последний месяц в inflow_trend
    inflow_trend: list[int]
    checks_ok: int
    checks_total: int
    companies_without_statement: int


class CompanyLookup(CamelModel):
    inn: str
    kind: CompanyKind
    name: str
    registered_at: str | None  # «март 2021»
    activity: str | None  # «56.10 · Деятельность ресторанов…»
    director: str | None
    director_matches: bool  # руководитель = ФИО + ИНН пользователя → можно добавить
    already_added_id: uuid.UUID | None


class SourceStatus(CamelModel):
    key: str
    label: str
    state: SourceState


# ---------------------------------------------------------------------------
# Кабинет: заявки
# ---------------------------------------------------------------------------

ProductKind = Literal["term_loan", "credit_line", "overdraft", "bank_guarantee"]
# Статусы для клиента (frontend/src/api/cabinet.ts → ApplicationStatus)
ClientApplicationStatus = Literal[
    "draft",
    "submitted",
    "checking",
    "docs_requested",
    "counter_offer",
    "approved",
    "signing",
    "issued",
    "rejected",
    "cancelled",
]


class CreditProductRead(CamelModel):
    code: str
    name: str
    kind: ProductKind
    min_amount: int
    max_amount: int
    min_term_months: int
    max_term_months: int
    rate: float  # % годовых — для расчёта примерного платежа


class ApplicationCreate(CamelModel):
    """Анкета заявки. Диапазоны суммы и срока проверяет сервис — они зависят от продукта."""

    company_id: uuid.UUID
    product_code: str
    amount: int = Field(gt=0)
    term_months: int = Field(gt=0)
    purpose: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)
    ]
    consent_personal_data: bool
    consent_bki: bool

    @field_validator("consent_personal_data", "consent_bki")
    @classmethod
    def _must_agree(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Без этого согласия заявку не рассмотреть")
        return value


class ApplicationEvent(CamelModel):
    status: ClientApplicationStatus
    label: str
    at: datetime
    comment: str | None


class Application(CamelModel):
    id: uuid.UUID
    number: str
    company_id: uuid.UUID
    company_name: str
    created_at: date
    product: str
    product_code: str
    amount: int | None
    term_months: int | None
    purpose: str | None
    status: ClientApplicationStatus
    note: str  # что происходит / что нужно от клиента


DecisionOutcome = Literal["approved", "counter_offer", "declined", "manual_review"]


class DecisionReason(CamelModel):
    code: str
    text: str


class Alternative(CamelModel):
    """Другой продукт или срок на тех же данных — проходит DSCR и грейд."""

    product_code: str
    product_name: str
    amount: int
    term_months: int
    rate: float
    monthly_payment: int


class Offer(CamelModel):
    """Вариант, который клиент может принять по этой заявке."""

    amount: int
    term_months: int
    rate: float
    monthly_payment: int


class Decision(CamelModel):
    outcome: DecisionOutcome
    # верхний уровень = выбранный вариант (до выбора — offers[0]); null при отказе / разборе
    amount: int | None
    term_months: int | None
    rate: float | None
    monthly_payment: int | None
    offers: list[Offer]  # 1–2 варианта для approved / counter_offer
    accepted_offer_index: int | None
    grade: str | None
    score: float | None
    reasons: list[DecisionReason]
    alternatives: list[Alternative]  # только при отказе — для новой заявки
    hints: list[str]
    decided_at: datetime


class ApplicationDetails(Application):
    history: list[ApplicationEvent]
    decision: Decision | None = None


class AcceptRequest(CamelModel):
    offer_index: int = Field(default=0, ge=0)


class SignCode(CamelModel):
    """Имитация SMS: код приходит прямо в ответе."""

    code: str
    expires_at: datetime


class SignRequest(CamelModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{6}$")]
