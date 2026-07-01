"""CLI entrypoint and dependency wiring."""

from __future__ import annotations

import argparse
import sys

from backupfather.config import Settings, load_settings
from backupfather.destinations.registry import build_destinations
from backupfather.errors import EXIT_CONFIG, EXIT_OK, EXIT_RUNTIME, BackupError, ConfigError
from backupfather.health import HealthState
from backupfather.notifiers.registry import build_notifiers
from backupfather.runner import BackupRunner
from backupfather.utils.logger import configure_logging, get_logger

log = get_logger("backupfather")

_BANNER = "backupfather — an offer your database can't refuse"


def _build_runner(settings: Settings) -> BackupRunner:
    return BackupRunner(
        settings=settings,
        destinations=build_destinations(settings),
        notifiers=build_notifiers(settings),
        health_state=HealthState(),
    )


def _cmd_run(settings: Settings) -> int:
    runner = _build_runner(settings)
    results = runner.run_all()
    ok = all(r.ok for r in results)
    for r in results:
        status = "OK" if r.ok else f"FAILED ({r.failed_step.value if r.failed_step else '?'})"
        log.info("%s: %s in %.1fs", r.db_name, status, r.duration_seconds)
    return EXIT_OK if ok else EXIT_RUNTIME


def _cmd_serve(settings: Settings) -> int:
    # Imported lazily so `run --once` has no APScheduler dependency at import time.
    from backupfather.scheduler import serve

    return serve(settings, _build_runner(settings))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backupfather", description=_BANNER)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a backup")
    run.add_argument("--once", action="store_true", help="run one backup and exit")

    sub.add_parser("serve", help="run the internal cron scheduler")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        # Logging may not be configured yet; print to stderr and use config exit code.
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    configure_logging(level=settings.log_level, fmt=settings.log_format)
    log.info(_BANNER)

    try:
        if args.command == "run":
            return _cmd_run(settings)
        if args.command == "serve":
            if not settings.scheduler_enabled:
                log.error("SCHEDULER_ENABLED=false; refusing to serve. Use 'run --once'.")
                return EXIT_CONFIG
            return _cmd_serve(settings)
    except BackupError as exc:
        log.error("fatal: %s", exc)
        return exc.exit_code
    except KeyboardInterrupt:
        log.info("interrupted; shutting down")
        return EXIT_OK

    return EXIT_RUNTIME


if __name__ == "__main__":
    raise SystemExit(main())
