"""application number from a sequence; sign code attempts

- loan_application_number_seq — номер заявки (nextval) вместо count()+1001: count под
  одновременной отправкой давал одинаковые номера и 500 на UNIQUE(number). Стартует после
  наибольшего уже выданного номера;
- loan_applications.sign_code_attempts — неверные попытки ввода кода подписи (после 5 код сгорает).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE loan_application_number_seq START 1001")
    # уже выданные номера (на VPS заявки есть) не повторяем: следующий — max + 1
    op.execute(
        "SELECT setval('loan_application_number_seq', max(number::bigint)) "
        "FROM loan_applications WHERE number ~ '^[0-9]+$' "
        "HAVING max(number::bigint) >= 1001"
    )
    op.add_column(
        "loan_applications",
        sa.Column(
            "sign_code_attempts",
            sa.SmallInteger(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("loan_applications", "sign_code_attempts")
    op.execute("DROP SEQUENCE loan_application_number_seq")
