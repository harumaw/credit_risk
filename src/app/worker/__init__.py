"""Воркер конвейера: берёт задачи из очереди `tasks` и выполняет их (`python -m app.worker`)."""

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.registry import Sources
from app.models import Task
from app.repositories import task as tasks_repo
from app.services import pipeline
from app.services.application import PROCESS_TASK
from app.settings import settings

log = logging.getLogger("worker")

Handler = Callable[[AsyncSession, Sources, Task], Awaitable[None]]


async def _process(session: AsyncSession, sources: Sources, task: Task) -> None:
    assert task.application_id is not None
    await pipeline.process_application(session, sources, task.application_id)


HANDLERS: dict[str, Handler] = {PROCESS_TASK: _process}


async def run_once(session: AsyncSession, sources: Sources) -> bool:
    """Выполняет одну задачу; False — очередь пуста."""
    task = await tasks_repo.claim(session)
    if task is None:
        await session.commit()
        return False
    task_id, kind, application_id = task.id, task.kind, task.application_id
    await session.commit()  # задача помечена running — другие воркеры её не возьмут
    try:
        await HANDLERS[kind](session, sources, task)
    except Exception as exc:
        await session.rollback()
        log.exception("задача %s (%s) упала", task_id, kind)
        task = await tasks_repo.get(session, task_id)
        assert task is not None
        failed = await tasks_repo.retry_or_fail(
            session,
            task,
            f"{type(exc).__name__}: {exc}",
            settings.WORKER_MAX_ATTEMPTS,
            timedelta(seconds=settings.WORKER_RETRY_SECONDS),
        )
        if failed and application_id is not None:
            await pipeline.send_to_manual_review(session, application_id, str(exc))
        await session.commit()
        return True
    task = await tasks_repo.get(session, task_id)
    assert task is not None
    await tasks_repo.finish(session, task)
    await session.commit()
    return True
