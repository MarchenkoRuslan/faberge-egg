from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app import db_tasks
from app.db_init import init_db, prepare_database, run_seed, seed_showroom_and_asset, wait_for_db
from app.models.database import _normalize_database_url
from app.models.showroom import Showroom


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


def test_init_db_runs_alembic_for_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    wait_mock = MagicMock()
    run_migrations_mock = MagicMock()

    monkeypatch.setattr("app.db_init.wait_for_db", wait_mock)
    monkeypatch.setattr("app.db_init.run_migrations", run_migrations_mock)

    init_db()

    wait_mock.assert_called_once()
    run_migrations_mock.assert_called_once()


def test_init_db_runs_alembic_for_non_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/app")

    wait_mock = MagicMock()
    run_migrations_mock = MagicMock()

    monkeypatch.setattr("app.db_init.wait_for_db", wait_mock)
    monkeypatch.setattr("app.db_init.run_migrations", run_migrations_mock)

    init_db()

    wait_mock.assert_called_once()
    run_migrations_mock.assert_called_once()


def test_seed_showroom_and_asset_is_idempotent(db):
    assert seed_showroom_and_asset(db) is True
    assert seed_showroom_and_asset(db) is False

    showrooms = db.query(Showroom).filter(Showroom.slug == "latvian-treasure").all()
    assert len(showrooms) == 1


def test_seed_showroom_and_asset_handles_concurrent_insert_conflict():
    db_session = MagicMock()
    filtered_query = db_session.query.return_value.filter.return_value
    filtered_query.first.return_value = None
    db_session.flush.side_effect = IntegrityError("INSERT", {}, Exception("duplicate key"))

    assert seed_showroom_and_asset(db_session) is False
    db_session.rollback.assert_called_once()


def test_prepare_database_runs_wait_migrate_and_seed_in_order(monkeypatch):
    calls = []

    def fake_wait(*, retries, retry_delay_seconds):
        calls.append(("wait", retries, retry_delay_seconds))

    def fake_migrate():
        calls.append(("migrate",))

    def fake_seed(*, require_schema):
        calls.append(("seed", require_schema))
        return True

    monkeypatch.setattr("app.db_init.wait_for_db", fake_wait)
    monkeypatch.setattr("app.db_init.run_migrations", fake_migrate)
    monkeypatch.setattr("app.db_init.run_seed", fake_seed)

    prepare_database()

    assert [entry[0] for entry in calls] == ["wait", "migrate", "seed"]
    assert calls[-1] == ("seed", True)


def test_run_seed_raises_when_schema_missing_and_required(monkeypatch):
    monkeypatch.setattr("app.db_init.assets_table_exists", lambda: False)

    with pytest.raises(RuntimeError, match="Run migrations first"):
        run_seed(require_schema=True)


def test_run_seed_skips_when_schema_missing_and_not_required(monkeypatch):
    monkeypatch.setattr("app.db_init.assets_table_exists", lambda: False)

    assert run_seed(require_schema=False) is False


def test_run_seed_opens_session_and_calls_seed(monkeypatch):
    db_session = MagicMock()
    session_factory = MagicMock(return_value=db_session)
    showroom_seed_mock = MagicMock(return_value=True)

    monkeypatch.setattr("app.db_init.assets_table_exists", lambda: True)
    monkeypatch.setattr("app.db_init._table_exists", lambda t: True)
    monkeypatch.setattr("app.db_init.SessionLocal", session_factory)
    monkeypatch.setattr("app.db_init.seed_showroom_and_asset", showroom_seed_mock)

    assert run_seed(require_schema=True) is True

    session_factory.assert_called_once()
    showroom_seed_mock.assert_called_once_with(db_session)
    db_session.close.assert_called_once()


def test_db_tasks_prepare_command_calls_prepare_database(monkeypatch):
    prepare_mock = MagicMock()
    monkeypatch.setattr(db_tasks, "prepare_database", prepare_mock)

    assert db_tasks.main(["prepare"]) == 0

    prepare_mock.assert_called_once_with(include_seed=True)


def test_db_tasks_migrate_command_runs_wait_and_migrations_only(monkeypatch):
    calls = []

    def fake_wait(*, retries, retry_delay_seconds):
        calls.append("wait")

    def fake_migrate():
        calls.append("migrate")

    def fake_seed(*, require_schema):
        calls.append("seed")
        return True

    monkeypatch.setattr(db_tasks, "wait_for_db", fake_wait)
    monkeypatch.setattr(db_tasks, "run_migrations", fake_migrate)
    monkeypatch.setattr(db_tasks, "run_seed", fake_seed)

    assert db_tasks.main(["migrate"]) == 0
    assert calls == ["wait", "migrate"]


def test_db_tasks_seed_command_returns_error_when_schema_missing(monkeypatch):
    def fake_seed(*, require_schema):
        raise RuntimeError("Cannot seed initial data: 'assets' table is missing. Run migrations first.")

    monkeypatch.setattr(db_tasks, "run_seed", fake_seed)

    assert db_tasks.main(["seed"]) == 1
