import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.enums import UserStatus


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
    id: uuid.UUID
    email: str | None
    last_name: str | None
    first_name: str | None
    middle_name: str | None
    status: UserStatus

    model_config = ConfigDict(from_attributes=True)
