from decimal import Decimal

from pydantic_settings import BaseSettings

SIMULATOR_URL = "http://localhost:8100"


class Settings(BaseSettings):
    POSTGRES_DSN: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    # Внешние источники: сейчас за всеми стоит симулятор, реальный сервис = другой URL + адаптер
    EGRUL_URL: str = SIMULATOR_URL
    FNS_URL: str = SIMULATOR_URL
    RMSP_URL: str = SIMULATOR_URL
    FSSP_URL: str = SIMULATOR_URL
    EFRSB_URL: str = SIMULATOR_URL
    ZSK_URL: str = SIMULATOR_URL
    BKI_URL: str = SIMULATOR_URL
    ABS_URL: str = SIMULATOR_URL
    SOURCE_TIMEOUT_SECONDS: float = 5.0
    SOURCE_RETRIES: int = 3  # попыток после первой неудачи
    SOURCE_BACKOFF_SECONDS: float = 0.5  # пауза удваивается с каждой попыткой

    # Предварительный лимит в кабинете (до заявки и скоринга)
    PRELIMINARY_RATE_PCT: Decimal = Decimal(24)
    PRELIMINARY_TERM_MONTHS: int = 12

    # Воркер конвейера: опрос очереди, повторы задачи, файл-heartbeat для healthcheck
    WORKER_POLL_SECONDS: float = 1.0
    WORKER_MAX_ATTEMPTS: int = 3
    WORKER_RETRY_SECONDS: float = 10.0
    WORKER_STALE_SECONDS: float = 300.0  # running дольше — воркер упал, задачу вернуть
    WORKER_HEARTBEAT_FILE: str = "/tmp/worker-heartbeat"
    EVENTS_POLL_SECONDS: float = 1.0  # SSE: как часто смотреть новые статусы
    EVENTS_MAX_SECONDS: float = (
        600.0  # SSE: потом поток закрывается, клиент переподключается
    )
    # Кабинет администратора /adminuser: суперпользователь создаётся seed'ом, только если задан пароль
    ADMIN_LOGIN: str = "ovv"
    ADMIN_PASSWORD: str | None = None
    ADMIN_EMAIL: str = "ovv@staff.local"
    ADMIN_FULL_NAME: str = "Суперпользователь"

    class Config:
        env_file = "local.env"


settings = Settings()
