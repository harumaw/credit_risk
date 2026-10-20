from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Currency = Literal["USD", "EUR", "KZT", "RUB"]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)

class CategoryRead(BaseModel):
    id: int
    user_id: int
    name: str

    model_config = ConfigDict(from_attributes=True)



class ExpenseCreate(BaseModel):
    categories_id: int
    name: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0)
    currency: Currency = "KZT"
    date: datetime | None = None

class ExpenseUpdate(BaseModel):
    categories_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    amount: Decimal | None = Field(default=None, gt=0)
    currency: Currency | None = None
    date: datetime | None = None

class ExpenseRead(BaseModel):
    id: int
    user_id: int
    categories_id: int
    name: str
    amount: Decimal
    currency: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CategoryBreakdown(BaseModel):
    categories_id: int
    name: str
    sum: Decimal
    count: int
    pct: int


class ExpenseSummary(BaseModel):
    total: Decimal
    count: int
    avg: Decimal
    breakdown: list[CategoryBreakdown]
    currency: str


class TrendPoint(BaseModel):
    year: int
    month: int
    total: Decimal


class TopCategory(BaseModel):
    categories_id: int
    name: str
    sum: Decimal


class ExpenseTrends(BaseModel):
    points: list[TrendPoint]
    top_categories: list[TopCategory]
    currency: str

from pydantic import EmailStr

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    email: str
    base_currency: str

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    base_currency: Currency


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target_amount: Decimal = Field(gt=0)
    months: int = Field(gt=0, le=120)
    currency: Currency = "KZT"


class GoalContributionCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: Currency = "KZT"


class GoalContributionRead(BaseModel):
    id: int
    goal_id: int
    amount: Decimal
    currency: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncomeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0)
    currency: Currency = "KZT"
    date: datetime | None = None


class IncomeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    amount: Decimal | None = Field(default=None, gt=0)
    currency: Currency | None = None
    date: datetime | None = None


class IncomeRead(BaseModel):
    id: int
    user_id: int
    name: str
    amount: Decimal
    currency: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncomeSummary(BaseModel):
    total: Decimal
    count: int
    avg: Decimal
    currency: str


class BalanceSummary(BaseModel):
    income: Decimal
    expenses: Decimal
    goals_monthly: Decimal
    balance: Decimal
    currency: str


class GoalRead(BaseModel):
    id: int
    user_id: int
    name: str
    target_amount: Decimal
    months: int
    monthly_target: Decimal
    saved: Decimal
    pct: int
    created_at: datetime
    status: str
    behind_by: Decimal
    currency: str

    model_config = ConfigDict(from_attributes=True)