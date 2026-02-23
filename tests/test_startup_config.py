import pytest

from app.main import (
    _db_url_diagnostics,
    _validate_database_url_for_runtime,
    _validate_required_env_for_runtime,
)
from app.services.email_service import get_mailjet_startup_diagnostics


def test_validate_database_url_allows_localhost_outside_railway(monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    monkeypatch.delenv("RAILWAY_SERVICE_ID", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)

    _validate_database_url_for_runtime("postgresql://user:pass@localhost:5432/app")


def test_validate_database_url_rejects_localhost_on_railway(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj_test")

    with pytest.raises(RuntimeError, match="Invalid DATABASE_URL for Railway runtime"):
        _validate_database_url_for_runtime("postgresql://user:pass@127.0.0.1:5432/app")


def test_validate_database_url_allows_sqlite_for_tests():
    _validate_database_url_for_runtime("sqlite:///:memory:")


def test_validate_database_url_requires_scheme():
    with pytest.raises(RuntimeError, match="missing URL scheme"):
        _validate_database_url_for_runtime("://db:5432/app")


def test_validate_database_url_requires_host():
    with pytest.raises(RuntimeError, match="missing host"):
        _validate_database_url_for_runtime("postgresql:///app")


def test_validate_database_url_requires_database_name():
    with pytest.raises(RuntimeError, match="missing database name"):
        _validate_database_url_for_runtime("postgresql://user:pass@db:5432/")


def test_db_url_diagnostics_contains_actionable_tips():
    diagnostics = _db_url_diagnostics("postgresql://user:pass@127.0.0.1:5432/app")
    assert "host=127.0.0.1" in diagnostics
    assert "localhost" in diagnostics
    assert "sslmode" in diagnostics


def test_validate_required_env_accepts_local_defaults_outside_railway(monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    monkeypatch.setenv("JWT_SECRET", "local-secret")
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")

    _validate_required_env_for_runtime()


def test_validate_required_env_rejects_insecure_jwt_on_railway(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj_test")
    monkeypatch.setenv("JWT_SECRET", "change-me-in-production")
    monkeypatch.setenv("BASE_URL", "https://example.up.railway.app")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")

    with pytest.raises(RuntimeError, match="JWT_SECRET uses insecure default value"):
        _validate_required_env_for_runtime()


def test_validate_required_env_rejects_invalid_base_url(monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("BASE_URL", "localhost:8000")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")

    with pytest.raises(RuntimeError, match="BASE_URL must be an absolute http\\(s\\) URL"):
        _validate_required_env_for_runtime()


def test_validate_required_env_accepts_bare_domains_on_railway(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj_test")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("BASE_URL", "web-production-f966.up.railway.app")
    monkeypatch.setenv("CORS_ORIGINS", "web-production-f966.up.railway.app")

    _validate_required_env_for_runtime()


def test_mailjet_env_diagnostics_reports_missing_required_config(monkeypatch):
    monkeypatch.delenv("MAILJET_API_KEY", raising=False)
    monkeypatch.delenv("MAILJET_SECRET_KEY", raising=False)
    monkeypatch.delenv("MAILJET_FROM_EMAIL", raising=False)
    monkeypatch.setenv("MAILJET_API_URL", "https://api.mailjet.com/v3.1/send")

    diagnostics, warnings = get_mailjet_startup_diagnostics()

    assert "required_config_present=False" in diagnostics
    assert "MAILJET_API_KEY" in diagnostics
    assert any("missing" in warning.lower() for warning in warnings)


def test_mailjet_env_diagnostics_warns_on_non_default_host(monkeypatch):
    monkeypatch.setenv("MAILJET_API_KEY", "x")
    monkeypatch.setenv("MAILJET_SECRET_KEY", "y")
    monkeypatch.setenv("MAILJET_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("MAILJET_API_URL", "https://proxy.internal.example/send")

    diagnostics, warnings = get_mailjet_startup_diagnostics()

    assert "host=proxy.internal.example" in diagnostics
    assert any("host differs from default" in warning for warning in warnings)
