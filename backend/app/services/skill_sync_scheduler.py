from __future__ import annotations

import logging
import threading
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.services.clawhub_sync import sync_clawhub_skills

LOGGER = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_sync_lock = threading.Lock()


def _run_sync_job() -> None:
    if not _sync_lock.acquire(blocking=False):
        LOGGER.info("Skip ClawHub sync job because another run is still in progress")
        return

    try:
        settings = get_settings()
        with get_session_factory()() as db:
            result = sync_clawhub_skills(db, settings=settings, full_refresh=False)
        LOGGER.info(
            "ClawHub sync finished: seen=%s created=%s updated=%s archived=%s detail_requests=%s",
            result.total_seen,
            result.created,
            result.updated,
            result.archived,
            result.detail_requests,
        )
    except Exception:
        LOGGER.exception("ClawHub sync job failed")
    finally:
        _sync_lock.release()


def start_skill_sync_scheduler() -> None:
    global _scheduler

    settings = get_settings()
    if not settings.clawhub_sync_enabled:
        return
    if _scheduler is not None and _scheduler.running:
        return

    timezone = ZoneInfo(settings.clawhub_sync_timezone)
    trigger = CronTrigger.from_crontab(settings.clawhub_sync_cron, timezone=timezone)
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        _run_sync_job,
        trigger=trigger,
        id="clawhub-skill-sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler

    if settings.clawhub_sync_on_startup:
        thread = threading.Thread(target=_run_sync_job, name="clawhub-sync-startup", daemon=True)
        thread.start()


def stop_skill_sync_scheduler() -> None:
    global _scheduler

    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
