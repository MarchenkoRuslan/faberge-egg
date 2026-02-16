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
