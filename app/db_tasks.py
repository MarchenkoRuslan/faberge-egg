import argparse
import logging
import sys
from collections.abc import Sequence

from app.db_init import prepare_database, run_migrations, run_seed, wait_for_db
from app.core.config import settings

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logger = logging.getLogger("app.db_tasks")


def _configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)


def _run_wait() -> None:
    wait_for_db(
        retries=settings.DB_CONNECT_RETRIES,
        retry_delay_seconds=settings.DB_CONNECT_RETRY_DELAY_SECONDS,
    )


def _run_migrate() -> None:
    _run_wait()
    run_migrations()


def _run_seed() -> None:
    run_seed(require_schema=True)


def _run_prepare() -> None:
    prepare_database(include_seed=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.db_tasks",
        description="Database operational tasks (wait, migrate, seed, prepare).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("wait", "migrate", "seed", "prepare"):
        subparsers.add_parser(name)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_logging()
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.command == "wait":
            _run_wait()
        elif args.command == "migrate":
            _run_migrate()
        elif args.command == "seed":
            _run_seed()
        elif args.command == "prepare":
            _run_prepare()
        else:  # pragma: no cover - argparse enforces valid values
            parser.error(f"Unknown command: {args.command}")
    except Exception:
        logger.exception("DB task failed command=%s", args.command)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
