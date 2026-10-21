from dataclasses import dataclass

import httpx

from app.integrations.abs import AbsClient
from app.integrations.bki import BkiClient
from app.integrations.efrsb import EfrsbClient
from app.integrations.egrul import EgrulClient
from app.integrations.fns import FnsClient
from app.integrations.fssp import FsspClient
from app.integrations.rmsp import RmspClient
from app.integrations.zsk import ZskClient
from app.settings import settings


@dataclass(frozen=True)
class Sources:
    egrul: EgrulClient
    fns: FnsClient
    rmsp: RmspClient
    fssp: FsspClient
    efrsb: EfrsbClient
    zsk: ZskClient
    bki: BkiClient
    abs: AbsClient


def build_sources(
    transport: httpx.AsyncBaseTransport | None = None,
    *,
    retries: int | None = None,
    backoff: float | None = None,
) -> Sources:
    """Все клиенты по URL из настроек; transport подменяют в тестах."""
    opts = {
        "timeout": settings.SOURCE_TIMEOUT_SECONDS,
        "retries": settings.SOURCE_RETRIES if retries is None else retries,
        "backoff": settings.SOURCE_BACKOFF_SECONDS if backoff is None else backoff,
        "transport": transport,
    }
    return Sources(
        egrul=EgrulClient(settings.EGRUL_URL, **opts),
        fns=FnsClient(settings.FNS_URL, **opts),
        rmsp=RmspClient(settings.RMSP_URL, **opts),
        fssp=FsspClient(settings.FSSP_URL, **opts),
        efrsb=EfrsbClient(settings.EFRSB_URL, **opts),
        zsk=ZskClient(settings.ZSK_URL, **opts),
        bki=BkiClient(settings.BKI_URL, **opts),
        abs=AbsClient(settings.ABS_URL, **opts),
    )
