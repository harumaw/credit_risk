"""Цикл воркера: `python -m app.worker`. Healthcheck compose смотрит свежесть heartbeat-файла."""

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.database import AsyncSessionLocal
from app.dependencies import get_sources
from app.repositories import task as tasks_repo
from app.settings import settings
from app.worker import log, run_once


def _beat() -> None:
    Path(settings.WORKER_HEARTBEAT_FILE).write_text(str(time.time()))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    sources = get_sources()
    log.info("воркер запущен")
    while True:
        async with AsyncSessionLocal() as session:
            stale = datetime.now(UTC) - timedelta(seconds=settings.WORKER_STALE_SECONDS)
            if await tasks_repo.requeue_stale(session, stale):
                log.warning("вернул в очередь задачи упавшего воркера")
            await session.commit()
            busy = await run_once(session, sources)
        _beat()
        if not busy:
            await asyncio.sleep(settings.WORKER_POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
