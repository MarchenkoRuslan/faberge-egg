from unittest.mock import patch

import httpx
import pytest

from app.services import email_service


def _set_mailjet_env(monkeypatch):
    monkeypatch.setenv("MAILJET_API_KEY", "test_api_key")
    monkeypatch.setenv("MAILJET_SECRET_KEY", "test_secret_key")
    monkeypatch.setenv("MAILJET_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("MAILJET_FROM_NAME", "Marketplace API")
    monkeypatch.setenv("MAILJET_API_URL", "https://api.mailjet.com/v3.1/send")
    monkeypatch.setenv("MAILJET_TIMEOUT_SECONDS", "10")


def test_send_email_success_posts_mailjet_payload(monkeypatch):
    _set_mailjet_env(monkeypatch)

    with patch("app.services.email_service.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "Messages": [{"Status": "success"}]
        }

        email_service.send_email(
            to_email="user@example.com",
            to_name="User Name",
            subject="Test subject",
            text_body="Plain text",
            html_body="<p>HTML</p>",
        )

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args.args[0] == "https://api.mailjet.com/v3.1/send"
    assert call_args.kwargs["auth"] == ("test_api_key", "test_secret_key")
    assert call_args.kwargs["timeout"] == 10

    payload = call_args.kwargs["json"]
    assert "Messages" in payload
    message = payload["Messages"][0]
    assert message["From"]["Email"] == "noreply@example.com"
    assert message["From"]["Name"] == "Marketplace API"
    assert message["To"] == [{"Email": "user@example.com", "Name": "User Name"}]
    assert message["Subject"] == "Test subject"
    assert message["TextPart"] == "Plain text"
    assert message["HTMLPart"] == "<p>HTML</p>"


def test_send_email_omits_html_part_when_not_provided(monkeypatch):
    _set_mailjet_env(monkeypatch)

    with patch("app.services.email_service.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "Messages": [{"Status": "success"}]
        }

        email_service.send_email(
            to_email="user@example.com",
            subject="Test subject",
            text_body="Plain text",
        )

    payload = mock_post.call_args.kwargs["json"]
    message = payload["Messages"][0]
    assert "HTMLPart" not in message
    assert message["To"] == [{"Email": "user@example.com"}]


def test_send_email_requires_mailjet_config(monkeypatch):
    monkeypatch.delenv("MAILJET_API_KEY", raising=False)
    monkeypatch.delenv("MAILJET_SECRET_KEY", raising=False)
    monkeypatch.delenv("MAILJET_FROM_EMAIL", raising=False)

    with pytest.raises(RuntimeError, match="Mailjet is not configured"):
        email_service.send_email(
            to_email="user@example.com",
            subject="Test",
            text_body="Body",
        )


def test_send_email_raises_on_http_error(monkeypatch):
    _set_mailjet_env(monkeypatch)

    with patch("app.services.email_service.httpx.post") as mock_post:
        mock_post.return_value.status_code = 400
        mock_post.return_value.text = "Bad Request"
        mock_post.return_value.json.return_value = {
            "ErrorMessage": "sender is not verified"
        }

        with pytest.raises(RuntimeError, match="HTTP 400"):
            email_service.send_email(
                to_email="user@example.com",
                subject="Test",
                text_body="Body",
            )


def test_send_email_http_error_with_decoding_error_is_handled(monkeypatch):
    _set_mailjet_env(monkeypatch)

    class FakeResponse:
        status_code = 400

        @property
        def text(self):
            raise httpx.DecodingError("invalid encoding")

        def json(self):
            raise httpx.DecodingError("invalid encoding")

    with patch(
        "app.services.email_service.httpx.post",
        return_value=FakeResponse(),
    ):
        with pytest.raises(RuntimeError, match="HTTP 400"):
            email_service.send_email(
                to_email="user@example.com",
                subject="Test",
                text_body="Body",
            )


def test_send_email_raises_when_mailjet_message_status_is_not_success(monkeypatch):
    _set_mailjet_env(monkeypatch)

    with patch("app.services.email_service.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "Messages": [
                {
                    "Status": "error",
                    "Errors": [
                        {
                            "ErrorMessage": "rejected",
                            "ErrorCode": "MJ001",
                            "StatusCode": 400,
                        }
                    ],
                }
            ]
        }

        with pytest.raises(RuntimeError, match="rejected"):
            email_service.send_email(
                to_email="user@example.com",
                subject="Test",
                text_body="Body",
            )


def test_send_verify_email_builds_link_and_subject(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com")
    monkeypatch.setenv("EMAIL_VERIFY_PATH", "/verify-email")

    with patch("app.services.email_service.send_email") as mock_send:
        email_service.send_verify_email(
            to_email="user@example.com",
            display_name="Alice",
            token="verify_token",
        )

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to_email"] == "user@example.com"
    assert kwargs["to_name"] == "Alice"
    assert kwargs["subject"] == "Confirm your email"
    assert "token=verify_token" in kwargs["text_body"]
    assert "token=verify_token" in kwargs["html_body"]
    assert "https://frontend.example.com/verify-email" in kwargs["text_body"]


def test_send_password_reset_email_builds_link_and_subject(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com")
    monkeypatch.setenv("PASSWORD_RESET_PATH", "/restore-password")

    with patch("app.services.email_service.send_email") as mock_send:
        email_service.send_password_reset_email(
            to_email="user@example.com",
            display_name="Alice",
            token="reset_token",
        )

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to_email"] == "user@example.com"
    assert kwargs["to_name"] == "Alice"
    assert kwargs["subject"] == "Reset your password"
    assert "token=reset_token" in kwargs["text_body"]
    assert "token=reset_token" in kwargs["html_body"]
    assert "https://frontend.example.com/restore-password" in kwargs["text_body"]
