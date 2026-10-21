"""scoring segments: правила выбора модели, обучающая выборка, строка платёжной дисциплины

- scoring_segments — когда какую модель применять (условия на признаки компании, приоритет);
  model_versions.segment_code → scoring_segments.code, model_versions.params — шкала баллов
  и калибровка PD;
- ml_dataset_samples — обучающая/валидационная/OOT-выборка (признаки на дату заявки + таргет);
- credit_obligations.payment_string — помесячные статусы платежей из КИ (0 — свежий месяц).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scoring_segments",
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column(
            "conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_scoring_segments")),
    )
    op.create_table(
        "ml_dataset_samples",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_code", sa.String(length=40), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("source_ref", sa.BigInteger(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("segment_code", sa.String(length=30), nullable=True),
        sa.Column("sample", sa.String(length=10), nullable=False),
        sa.Column("target", sa.SmallInteger(), nullable=True),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_ml_dataset_samples_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["segment_code"],
            ["scoring_segments.code"],
            name=op.f("fk_ml_dataset_samples_segment_code_scoring_segments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ml_dataset_samples")),
        sa.UniqueConstraint(
            "dataset_code",
            "company_id",
            name=op.f("uq_ml_dataset_samples_dataset_code_company_id"),
        ),
    )
    op.add_column(
        "model_versions",
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Если в model_versions уже есть segment_code, FK не должен уронить миграцию (и старт app):
    # заводим под них выключенные сегменты-заглушки с условием «всем».
    op.execute(
        """
        INSERT INTO scoring_segments (code, name, priority, conditions, is_active)
        SELECT DISTINCT segment_code, segment_code, 1000, '{}'::jsonb, false
        FROM model_versions WHERE segment_code IS NOT NULL
        """
    )
    op.create_foreign_key(
        op.f("fk_model_versions_segment_code_scoring_segments"),
        "model_versions",
        "scoring_segments",
        ["segment_code"],
        ["code"],
    )
    op.add_column(
        "credit_obligations",
        sa.Column("payment_string", sa.String(length=48), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credit_obligations", "payment_string")
    op.drop_constraint(
        op.f("fk_model_versions_segment_code_scoring_segments"),
        "model_versions",
        type_="foreignkey",
    )
    op.drop_column("model_versions", "params")
    op.drop_table("ml_dataset_samples")
    op.drop_table("scoring_segments")
