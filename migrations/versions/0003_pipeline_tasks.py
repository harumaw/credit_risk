"""pipeline: очередь задач воркера, идемпотентная отправка, детали решения, код подписи

- tasks — очередь конвейера (воркер берёт задачу через FOR UPDATE SKIP LOCKED);
- loan_applications.idempotency_key (уникален в паре с автором) — повтор отправки
  отдаёт ту же заявку; sign_code_hash / sign_code_expires_at — имитация кода подписи;
- credit_decisions.details — входы решения, альтернативы и подсказки клиенту.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status", sa.String(length=10), server_default="queued", nullable=False
        ),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "run_after",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["loan_applications.id"],
            name=op.f("fk_tasks_application_id_loan_applications"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_status_run_after"), "tasks", ["status", "run_after"])
    op.add_column(
        "loan_applications",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "loan_applications",
        sa.Column("sign_code_hash", sa.CHAR(length=64), nullable=True),
    )
    op.add_column(
        "loan_applications",
        sa.Column("sign_code_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        op.f("uq_loan_applications_applicant_user_id_idempotency_key"),
        "loan_applications",
        ["applicant_user_id", "idempotency_key"],
    )
    op.add_column(
        "credit_decisions",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credit_decisions", "details")
    op.drop_constraint(
        op.f("uq_loan_applications_applicant_user_id_idempotency_key"),
        "loan_applications",
        type_="unique",
    )
    op.drop_column("loan_applications", "sign_code_expires_at")
    op.drop_column("loan_applications", "sign_code_hash")
    op.drop_column("loan_applications", "idempotency_key")
    op.drop_index(op.f("ix_tasks_status_run_after"), table_name="tasks")
    op.drop_table("tasks")
