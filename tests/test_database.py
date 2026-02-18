from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.db_init import init_db, wait_for_db
from app.models.database import _normalize_database_url


def test_normalize_database_url_postgres_scheme():
    assert (
        _normalize_database_url("postgres://user:pass@localhost:5432/app")
        == "postgresql+psycopg://user:pass@localhost:5432/app"
    )


def test_normalize_database_url_postgresql_scheme_without_driver():
    assert (
        _normalize_database_url("postgresql://user:pass@localhost:5432/app")
        == "postgresql+psycopg://user:pass@localhost:5432/app"
    )


def test_normalize_database_url_postgresql_with_driver_unchanged():
    assert (
        _normalize_database_url("postgresql+psycopg://user:pass@localhost:5432/app")
        == "postgresql+psycopg://user:pass@localhost:5432/app"
    )


def test_wait_for_db_retries_until_success(monkeypatch):
    connect_mock = MagicMock()
    connect_mock.side_effect = [
        OperationalError("stmt", {}, Exception("first failure")),
        OperationalError("stmt", {}, Exception("second failure")),
        MagicMock(),
    ]

    engine_mock = MagicMock()
    engine_mock.connect = connect_mock

    monkeypatch.setattr("app.db_init.engine", engine_mock)

    wait_for_db(retries=3, retry_delay_seconds=0)

    assert connect_mock.call_count == 3


def test_wait_for_db_raises_after_exhausted_retries(monkeypatch):
    connect_mock = MagicMock(
        side_effect=OperationalError("stmt", {}, Exception("persistent failure"))
    )
    engine_mock = MagicMock()
    engine_mock.connect = connect_mock

    monkeypatch.setattr("app.db_init.engine", engine_mock)

    with pytest.raises(RuntimeError, match="Database is unreachable"):
        wait_for_db(retries=2, retry_delay_seconds=0)

    assert connect_mock.call_count == 2


def test_init_db_skips_alembic_for_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    wait_mock = MagicMock()
    create_all_mock = MagicMock()
    run_migrations_mock = MagicMock()

    monkeypatch.setattr("app.db_init.wait_for_db", wait_mock)
    monkeypatch.setattr("app.db_init.Base.metadata.create_all", create_all_mock)
    monkeypatch.setattr("app.db_init.run_migrations", run_migrations_mock)

    init_db()

    wait_mock.assert_called_once()
    create_all_mock.assert_called_once()
    run_migrations_mock.assert_not_called()


def test_init_db_runs_alembic_for_non_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/app")

    wait_mock = MagicMock()
    create_all_mock = MagicMock()
    run_migrations_mock = MagicMock()

    monkeypatch.setattr("app.db_init.wait_for_db", wait_mock)
    monkeypatch.setattr("app.db_init.Base.metadata.create_all", create_all_mock)
    monkeypatch.setattr("app.db_init.run_migrations", run_migrations_mock)

    init_db()

    wait_mock.assert_called_once()
    run_migrations_mock.assert_called_once()
    create_all_mock.assert_called_once()
