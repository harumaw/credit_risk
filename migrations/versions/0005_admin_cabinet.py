"""admin cabinet: вход сотрудников и снимок входов скоринга

- staff_users: login, password_hash, last_login_at — вход в /adminuser;
- индексы obligation_payments.obligation_id и company_id у credit_obligations, bank_accounts,
  enforcement_proceedings, ml_dataset_samples — FK-проверки при удалении и выборки по компании;
- score_results: segment_code (сегмент по правилам), features (вектор признаков на дату),
  reason_codes, recommended_decision (решение по матрице грейдов).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECISION_TYPE = postgresql.ENUM(name="decision_type", create_type=False)
# Индексы под FK-проверки при удалении компании и выборки по компании
INDEXED_BY_COMPANY = (
    "credit_obligations",
    "bank_accounts",
    "enforcement_proceedings",
    "ml_dataset_samples",
)


def upgrade() -> None:
    op.add_column(
        "staff_users", sa.Column("login", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "staff_users", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "staff_users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(op.f("uq_staff_users_login"), "staff_users", ["login"])

    op.add_column(
        "score_results", sa.Column("segment_code", sa.String(length=30), nullable=True)
    )
    op.add_column(
        "score_results",
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "score_results",
        sa.Column("reason_codes", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "score_results",
        sa.Column("recommended_decision", DECISION_TYPE, nullable=True),
    )
    op.create_index(
        op.f("ix_obligation_payments_obligation_id"),
        "obligation_payments",
        ["obligation_id"],
    )
    for table in INDEXED_BY_COMPANY:
        op.create_index(op.f(f"ix_{table}_company_id"), table, ["company_id"])
    op.create_foreign_key(
        op.f("fk_score_results_segment_code_scoring_segments"),
        "score_results",
        "scoring_segments",
        ["segment_code"],
        ["code"],
    )


def downgrade() -> None:
    for table in INDEXED_BY_COMPANY:
        op.drop_index(op.f(f"ix_{table}_company_id"), table_name=table)
    op.drop_index(
        op.f("ix_obligation_payments_obligation_id"), table_name="obligation_payments"
    )
    op.drop_constraint(
        op.f("fk_score_results_segment_code_scoring_segments"),
        "score_results",
        type_="foreignkey",
    )
    for column in ("recommended_decision", "reason_codes", "features", "segment_code"):
        op.drop_column("score_results", column)
    op.drop_constraint(op.f("uq_staff_users_login"), "staff_users", type_="unique")
    for column in ("last_login_at", "password_hash", "login"):
        op.drop_column("staff_users", column)
