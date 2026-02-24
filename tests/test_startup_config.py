import pytest

from app.main import (
    _db_url_diagnostics,
    _validate_database_url_for_runtime,
    _validate_required_env_for_runtime,
)
from app.services.email_service import get_resend_startup_diagnostics


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


def test_resend_env_diagnostics_reports_missing_required_config(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    monkeypatch.delenv("RESEND_TEMPLATE_VERIFY_EMAIL", raising=False)
    monkeypatch.delenv("RESEND_TEMPLATE_PASSWORD_RESET", raising=False)

    diagnostics, warnings = get_resend_startup_diagnostics()

    assert "missing=" in diagnostics or "resend_configured" in diagnostics
    assert any("missing" in warning.lower() or "Resend" in warning for warning in warnings)


def test_resend_env_diagnostics_ok_when_configured(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_xxx")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("RESEND_TEMPLATE_VERIFY_EMAIL", "tpl_verify")
    monkeypatch.setenv("RESEND_TEMPLATE_PASSWORD_RESET", "tpl_reset")

    diagnostics, warnings = get_resend_startup_diagnostics()

    assert "resend_configured=True" in diagnostics
    assert "template_verify=tpl_verify" in diagnostics
