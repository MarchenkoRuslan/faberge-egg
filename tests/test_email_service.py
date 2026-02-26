import logging

import pytest

from app.shared import email_service
from app.shared.email_service import (
    VAR_CONFIRM_LINK,
    VAR_RESET_LINK,
    VAR_USER_NAME,
)
from app.shared.email_service import mask_email


def _set_resend_env(monkeypatch, template_verify: str = "tpl_verify", template_reset: str = "tpl_reset"):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Acme <onboarding@resend.dev>")
    monkeypatch.setenv("RESEND_TEMPLATE_VERIFY_EMAIL", template_verify)
    monkeypatch.setenv("RESEND_TEMPLATE_PASSWORD_RESET", template_reset)


def test_get_resend_startup_diagnostics_reports_missing(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    monkeypatch.delenv("RESEND_TEMPLATE_VERIFY_EMAIL", raising=False)
    monkeypatch.delenv("RESEND_TEMPLATE_PASSWORD_RESET", raising=False)

    diagnostics, warnings = email_service.get_resend_startup_diagnostics()

    assert "resend_configured=False" in diagnostics or "missing=" in diagnostics
    assert any("missing" in w.lower() or "Resend" in w for w in warnings)


def test_get_resend_startup_diagnostics_ok_when_configured(monkeypatch):
    _set_resend_env(monkeypatch)

    diagnostics, warnings = email_service.get_resend_startup_diagnostics()

    assert "resend_configured=True" in diagnostics
    assert "template_verify=tpl_verify" in diagnostics
    assert "template_reset=tpl_reset" in diagnostics


def test_send_verify_email_uses_template_and_variables(monkeypatch):
    _set_resend_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com")
    monkeypatch.setenv("EMAIL_VERIFY_PATH", "/verify-email")
    captured: list[dict] = []

    def fake_send(params):
        captured.append(params)
        return type("Result", (), {"id": "msg_123"})()

    monkeypatch.setattr(email_service.resend.Emails, "send", fake_send)

    email_service.send_verify_email(
        to_email="user@example.com",
        display_name="Alice",
        token="verify_token",
    )

    assert len(captured) == 1
    p = captured[0]
    assert p["from"] == "Acme <onboarding@resend.dev>"
    assert p["to"] == ["user@example.com"]
    assert p["template"]["id"] == "tpl_verify"
    assert p["template"]["variables"][VAR_CONFIRM_LINK] == (
        "https://frontend.example.com/verify-email?token=verify_token"
    )
    assert p["template"]["variables"][VAR_USER_NAME] == "Alice"


def test_send_verify_email_uses_there_when_no_display_name(monkeypatch):
    _set_resend_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    monkeypatch.setenv("EMAIL_VERIFY_PATH", "/confirm")
    captured: list[dict] = []

    def fake_send(params):
        captured.append(params)
        return type("Result", (), {"id": "x"})()

    monkeypatch.setattr(email_service.resend.Emails, "send", fake_send)

    email_service.send_verify_email(
        to_email="nobody@example.com",
        display_name=None,
        token="t1",
    )

    assert captured[0]["template"]["variables"][VAR_USER_NAME] == "there"


def test_send_verify_email_raises_when_template_id_missing(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "a@b.com")
    monkeypatch.setenv("RESEND_TEMPLATE_VERIFY_EMAIL", "")
    monkeypatch.setenv("RESEND_TEMPLATE_PASSWORD_RESET", "tpl_reset")

    with pytest.raises(RuntimeError, match="RESEND_TEMPLATE_VERIFY_EMAIL"):
        email_service.send_verify_email(
            to_email="u@e.com",
            display_name=None,
            token="t",
        )


def test_send_password_reset_email_uses_template_and_variables(monkeypatch):
    _set_resend_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com")
    monkeypatch.setenv("PASSWORD_RESET_PATH", "/restore-password")
    captured: list[dict] = []

    def fake_send(params):
        captured.append(params)
        return type("Result", (), {"id": "msg_456"})()

    monkeypatch.setattr(email_service.resend.Emails, "send", fake_send)

    email_service.send_password_reset_email(
        to_email="user@example.com",
        display_name="Bob",
        token="reset_token",
    )

    assert len(captured) == 1
    p = captured[0]
    assert p["to"] == ["user@example.com"]
    assert p["template"]["id"] == "tpl_reset"
    assert p["template"]["variables"][VAR_RESET_LINK] == (
        "https://frontend.example.com/restore-password?token=reset_token"
    )
    assert p["template"]["variables"][VAR_USER_NAME] == "Bob"


def test_send_password_reset_email_raises_when_template_id_missing(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "a@b.com")
    monkeypatch.setenv("RESEND_TEMPLATE_VERIFY_EMAIL", "tpl_v")
    monkeypatch.setenv("RESEND_TEMPLATE_PASSWORD_RESET", "")

    with pytest.raises(RuntimeError, match="RESEND_TEMPLATE_PASSWORD_RESET"):
        email_service.send_password_reset_email(
            to_email="u@e.com",
            display_name=None,
            token="t",
        )


def test_send_verify_email_raises_runtime_error_on_resend_failure(monkeypatch):
    _set_resend_env(monkeypatch)

    def fail_send(params):
        raise ValueError("Invalid from")

    monkeypatch.setattr(email_service.resend.Emails, "send", fail_send)

    with pytest.raises(RuntimeError, match="Resend send failed"):
        email_service.send_verify_email(
            to_email="u@e.com",
            display_name=None,
            token="t",
        )


def test_send_verify_email_raises_when_resend_not_configured(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    monkeypatch.setenv("RESEND_TEMPLATE_VERIFY_EMAIL", "tpl")
    monkeypatch.setenv("RESEND_TEMPLATE_PASSWORD_RESET", "tpl2")

    with pytest.raises(RuntimeError, match="Resend is not configured"):
        email_service.send_verify_email(
            to_email="u@e.com",
            display_name=None,
            token="t",
        )


def test_mask_email_preserves_two_char_local_part():
    assert mask_email("ab@example.com") == "ab***@example.com"
