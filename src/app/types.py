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

from app.enums import (
    CompanyStatus,
    DataSource,
    FetchStatus,
    MspCategory,
    ProductType,
    TaxRegime,
    UserStatus,
)

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


class InnRequest(BaseModel):
    inn: str

    @field_validator("inn")
    @classmethod
    def _check_inn(cls, value: str) -> str:
        return validate_company_inn(value)


class Okved(BaseModel):
    code: str
    name: str
    is_main: bool


class CompanyBrief(BaseModel):
    """Строка переключателя компаний."""

    id: uuid.UUID
    inn: str
    name: str
    kind: CompanyKind
    msp_category: MspCategory | None
    needs_statement: bool  # оборотов в нашем банке нет — нужна выписка


class CompanyLookup(BaseModel):
    """Найденная по ИНН компания: показываем перед добавлением."""

    company_id: uuid.UUID
    inn: str
    name: str
    kind: CompanyKind
    status: CompanyStatus
    registration_date: date | None
    okved_main: Okved | None
    director_name: str | None
    can_add: bool
    reason: str | None  # почему нельзя добавить
    already_added: bool


class SourceStatus(BaseModel):
    source: DataSource
    label: str
    status: FetchStatus
    received_at: datetime | None
    error: str | None


class CompanyAdded(BaseModel):
    company: CompanyBrief
    sources: list[SourceStatus]


class CompanyCard(BaseModel):
    id: uuid.UUID
    inn: str
    ogrn: str | None
    kpp: str | None
    name: str
    full_name: str
    legal_form: str | None
    kind: CompanyKind
    status: CompanyStatus
    registration_date: date | None
    region_code: str | None
    address: str | None
    msp_category: MspCategory | None
    headcount: int | None
    tax_regime: TaxRegime | None
    is_bank_client: bool


class Check(BaseModel):
    code: str
    label: str
    value: str
    ok: bool | None  # None — справочная строка, не проверка


class MonthPoint(BaseModel):
    month: date
    inflow: int
    outflow: int
    closing_balance: int


class ForecastPoint(BaseModel):
    month: date
    inflow: int
    inflow_lower: int
    inflow_upper: int
    closing_balance: int


class Loan(BaseModel):
    lender: str | None
    product_type: ProductType | None
    outstanding: int
    monthly_payment: int
    next_payment_date: date | None
    overdue: int


class CreditLimit(BaseModel):
    amount: int | None  # None — посчитать нельзя (см. reason)
    term_months: int
    rate_pct: float
    needs_statement: bool
    reason: str | None


class Metrics(BaseModel):
    inflow_12m: int | None
    inflow_12m_change_pct: float | None  # к предыдущим 12 мес
    inflow_last_month: int | None
    inflow_last_month_change_pct: float | None  # к предыдущему месяцу
    avg_balance: int | None
    monthly_income: (
        int | None
    )  # чистый поток (поступления − списания) в среднем за месяц
    monthly_payments: int
    dscr: float | None  # доход / платежи по кредитам


class CompanySummary(BaseModel):
    company: CompanyCard
    okved: list[Okved]
    checks: list[Check]
    turnovers: list[MonthPoint]  # последние 12 мес
    forecast: list[ForecastPoint]  # следующие 3 мес
    metrics: Metrics
    loans: list[Loan]
    limit: CreditLimit
    sources: list[SourceStatus]


class GroupCompany(BaseModel):
    id: uuid.UUID
    inn: str
    name: str
    kind: CompanyKind
    msp_category: MspCategory | None
    inflow_last_month: int | None
    debt: int
    monthly_payment: int
    needs_statement: bool


class NextPayment(BaseModel):
    date: date
    amount: int
    company_id: uuid.UUID
    lender: str | None


class GroupSummary(BaseModel):
    companies: list[GroupCompany]
    total_debt: int
    loans_count: int
    monthly_payments: int
    next_payment: NextPayment | None
    inflow_last_month: int | None  # по компаниям, где есть обороты
    limit: CreditLimit
