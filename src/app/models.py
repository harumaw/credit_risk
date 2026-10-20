from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, UniqueConstraint, Numeric
from decimal import Decimal



from app.database import Base



class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key =True, index = True)
    email: Mapped[str] = mapped_column(String(255), unique = True, index = True)
    password_hash: Mapped[str] = mapped_column(String(255))
    base_currency: Mapped[str] = mapped_column(String(3), server_default="KZT")

class Category(Base):

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    
    id: Mapped[int] = mapped_column(Integer, primary_key = True, index = True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete = "CASCADE"), index = True)
    name: Mapped[str] = mapped_column(String(255), index=True)


class Expense(Base):

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key = True, index = True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete = "CASCADE"), index = True)
    name: Mapped[str] = mapped_column(String(255))
    categories_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete = "CASCADE"), index =True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10,2))
    currency: Mapped[str] = mapped_column(String(3), server_default="KZT")
    created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
        )


class Income(Base):

    __tablename__ = "incomes"

    id: Mapped[int] = mapped_column(Integer, primary_key = True, index = True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete = "CASCADE"), index = True)
    name: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default="KZT")
    created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
        )


class Goal(Base):

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key = True, index = True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete = "CASCADE"), index = True)
    name: Mapped[str] = mapped_column(String(255))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    months: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), server_default="KZT")
    created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
        )


class GoalContribution(Base):

    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key = True, index = True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete = "CASCADE"), index = True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default="KZT")
    created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
        )


class ExchangeRate(Base):

    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), unique=True, index=True)
    rate_to_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

