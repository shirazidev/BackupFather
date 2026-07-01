"""Internal cron scheduler (APScheduler) + health server lifecycle.

Optional: when ``SCHEDULER_ENABLED=false`` the container should instead be driven
by an external cron / Kubernetes CronJob calling ``backupfather run --once``.
"""

from __future__ import annotations

import signal
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backupfather.config import Settings
from backupfather.errors import EXIT_CONFIG, EXIT_OK, ConfigError
from backupfather.health import HealthServer
from backupfather.runner import BackupRunner
from backupfather.utils.logger import get_logger

log = get_logger(__name__)


def _make_trigger(cron_expr: str) -> CronTrigger:
    try:
        return CronTrigger.from_crontab(cron_expr)
    except ValueError as exc:
        raise ConfigError(f"invalid BACKUP_CRON {cron_expr!r}: {exc}") from exc


def serve(settings: Settings, runner: BackupRunner) -> int:
    """Run the scheduler until interrupted. Returns a process exit code."""
    trigger = _make_trigger(settings.backup_cron)

    health: HealthServer | None = None
    if settings.healthcheck_enabled and runner.health_state is not None:
        health = HealthServer(runner.health_state, settings.healthcheck_port)
        health.start()

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        runner.run_all,
        trigger=trigger,
        id="backup",
        max_instances=1,  # never let a slow backup overlap its next run
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    log.info("scheduler started with cron %r (UTC)", settings.backup_cron)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        stop.wait()
    finally:
        log.info("shutting down scheduler")
        scheduler.shutdown(wait=True)
        if health is not None:
            health.stop()
    return EXIT_OK


def validate_cron(settings: Settings) -> int:
    """Fail-fast helper so a bad cron is caught before serving."""
    _make_trigger(settings.backup_cron)
    return EXIT_CONFIG  # unused; kept for symmetry
