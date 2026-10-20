import re
import uuid
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

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
