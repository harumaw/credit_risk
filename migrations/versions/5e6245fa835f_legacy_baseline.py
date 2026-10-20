"""legacy baseline: конец старой цепочки миграций

Пустая миграция с ID последней миграции старой схемы проекта. Старые миграции
удалены, но базы, где они уже применены (сервер, локальные БД), хранят в
alembic_version именно этот ID — без файла Alembic не нашёл бы текущую версию.
Старые таблицы удаляет следующая миграция (0001_credit_schema).

Revision ID: 5e6245fa835f
Revises:
Create Date: 2026-10-20

"""

from collections.abc import Sequence

revision: str = "5e6245fa835f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
