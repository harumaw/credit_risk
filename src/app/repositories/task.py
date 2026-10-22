"""Очередь задач конвейера в Postgres: несколько воркеров не возьмут одну задачу (SKIP LOCKED)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


async def enqueue(
    session: AsyncSession, kind: str, application_id: uuid.UUID | None = None
) -> Task:
    task = Task(kind=kind, application_id=application_id, status=QUEUED)
    session.add(task)
    await session.flush()
    return task


async def claim(session: AsyncSession) -> Task | None:
    """Берёт самую старую готовую задачу и помечает running; вызывающий коммитит."""
    stmt = (
        select(Task)
        .where(Task.status == QUEUED, Task.run_after <= func.now())
        .order_by(Task.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = (await session.execute(stmt)).scalar_one_or_none()
    if task is None:
        return None
    task.status = RUNNING
    task.attempts += 1
    task.locked_at = func.now()
    await session.flush()
    return task


async def get(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id)


async def finish(session: AsyncSession, task: Task) -> None:
    task.status = DONE
    task.last_error = None
    await session.flush()


async def retry_or_fail(
    session: AsyncSession, task: Task, error: str, max_attempts: int, delay: timedelta
) -> bool:
    """Ставит задачу на повтор через delay или помечает failed; True — попытки кончились."""
    task.last_error = error[:2000]
    if task.attempts >= max_attempts:
        task.status = FAILED
    else:
        task.status = QUEUED
        task.run_after = func.now() + delay
    await session.flush()
    return task.status == FAILED


async def requeue_stale(session: AsyncSession, older_than: datetime) -> int:
    """Задачи упавшего воркера (running дольше порога) — обратно в очередь."""
    stmt = (
        update(Task)
        .where(Task.status == RUNNING, Task.locked_at < older_than)
        .values(status=QUEUED, locked_at=None)
    )
    result = await session.execute(stmt)
    return result.rowcount or 0
