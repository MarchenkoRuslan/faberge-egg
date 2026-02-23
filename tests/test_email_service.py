import logging

import httpx
import pytest

from app.services import email_service
from app.utils.redaction import mask_email


class FakeHttpxResponse:
    def __init__(
        self,
        status_code: int,
        json_data: dict | None = None,
        text_data: str = "",
        json_error: Exception | None = None,
        text_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self._text_data = text_data
        self._json_error = json_error
        self._text_error = text_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data

    @property
    def text(self) -> str:
        if self._text_error is not None:
            raise self._text_error
        return self._text_data


def _set_mailjet_env(monkeypatch):
    monkeypatch.setenv("MAILJET_API_KEY", "test_api_key")
    monkeypatch.setenv("MAILJET_SECRET_KEY", "test_secret_key")
    monkeypatch.setenv("MAILJET_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("MAILJET_FROM_NAME", "Marketplace API")
    monkeypatch.setenv("MAILJET_API_URL", "https://api.mailjet.com/v3.1/send")
    monkeypatch.setenv("MAILJET_TIMEOUT_SECONDS", "10")


def _mailjet_success_body(
    *,
    message_id: int | None = None,
    message_uuid: str | None = None,
) -> dict:
    message: dict[str, object] = {"Status": "success"}
    if message_id is not None or message_uuid is not None:
        recipient: dict[str, object] = {}
        if message_id is not None:
            recipient["MessageID"] = message_id
        if message_uuid is not None:
            recipient["MessageUUID"] = message_uuid
        message["To"] = [recipient]
    return {"Messages": [message]}


def _install_fake_post(monkeypatch, response: FakeHttpxResponse):
    calls: list[dict] = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(email_service.httpx, "post", fake_post)
    return calls


def _install_fake_post_sequence(monkeypatch, responses_or_exceptions: list[object]):
    calls: list[dict] = []
    queue = list(responses_or_exceptions)

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(email_service.httpx, "post", fake_post)
    return calls


def test_send_email_posts_expected_mailjet_payload(monkeypatch):
    _set_mailjet_env(monkeypatch)
    response = FakeHttpxResponse(200, json_data=_mailjet_success_body())
    calls = _install_fake_post(monkeypatch, response)

    email_service.send_email(
        to_email="user@example.com",
        to_name="User Name",
        subject="Test subject",
        text_body="Plain text",
        html_body="<p>HTML</p>",
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "https://api.mailjet.com/v3.1/send"
    assert call["auth"] == ("test_api_key", "test_secret_key")
    assert call["timeout"] == 10

    payload = call["json"]
    assert "Messages" in payload
    message = payload["Messages"][0]
    assert message["From"]["Email"] == "noreply@example.com"
    assert message["From"]["Name"] == "Marketplace API"
    assert message["To"] == [
        {"Email": "user@example.com", "Name": "User Name"}
    ]
    assert message["Subject"] == "Test subject"
    assert message["TextPart"] == "Plain text"
    assert message["HTMLPart"] == "<p>HTML</p>"


def test_send_email_logs_success_with_correlation_ids(monkeypatch, caplog):
    _set_mailjet_env(monkeypatch)
    response = FakeHttpxResponse(
        200,
        json_data=_mailjet_success_body(
            message_id=123456789,
            message_uuid="msg-uuid-1",
        ),
    )
    _install_fake_post(monkeypatch, response)

    with caplog.at_level(logging.INFO, logger="app.services.email_service"):
        email_service.send_email(
            to_email="user@example.com",
            subject="Test subject",
            text_body="Plain text",
        )

    assert "Mailjet send success" in caplog.text
    assert "outcome=success" in caplog.text
    assert "host=api.mailjet.com" in caplog.text
    assert "to_email=us***@example.com" in caplog.text
    assert "message_id=123456789" in caplog.text
    assert "message_uuid=msg-uuid-1" in caplog.text
    assert "test_api_key" not in caplog.text
    assert "test_secret_key" not in caplog.text


def test_send_email_omits_html_part_when_not_provided(monkeypatch):
    _set_mailjet_env(monkeypatch)
    response = FakeHttpxResponse(200, json_data=_mailjet_success_body())
    calls = _install_fake_post(monkeypatch, response)

    email_service.send_email(
        to_email="user@example.com",
        subject="Test subject",
        text_body="Plain text",
    )

    payload = calls[0]["json"]
    message = payload["Messages"][0]
    assert "HTMLPart" not in message
    assert message["To"] == [{"Email": "user@example.com"}]


def test_send_email_warns_on_non_default_mailjet_host(monkeypatch, caplog):
    _set_mailjet_env(monkeypatch)
    monkeypatch.setenv(
        "MAILJET_API_URL",
        "https://proxy.internal.example/send",
    )
    response = FakeHttpxResponse(200, json_data=_mailjet_success_body())
    _install_fake_post(monkeypatch, response)

    with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
        email_service.send_email(
            to_email="user@example.com",
            subject="Test subject",
            text_body="Plain text",
        )

    assert "Mailjet API URL host differs from default" in caplog.text
    assert "host=proxy.internal.example" in caplog.text


def test_mask_email_preserves_two_char_local_part():
    assert mask_email("ab@example.com") == "ab***@example.com"


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
    response = FakeHttpxResponse(
        400,
        json_data={"ErrorMessage": "sender is not verified"},
        text_data="Bad Request",
    )
    _install_fake_post(monkeypatch, response)

    with pytest.raises(RuntimeError, match="HTTP 400"):
        email_service.send_email(
            to_email="user@example.com",
            subject="Test",
            text_body="Body",
        )


def test_send_email_http_error_with_decoding_error_is_handled(monkeypatch):
    _set_mailjet_env(monkeypatch)
    response = FakeHttpxResponse(
        400,
        json_error=httpx.DecodingError("invalid encoding"),
        text_error=httpx.DecodingError("invalid encoding"),
    )
    _install_fake_post(monkeypatch, response)

    with pytest.raises(RuntimeError, match="HTTP 400"):
        email_service.send_email(
            to_email="user@example.com",
            subject="Test",
            text_body="Body",
        )


def test_send_email_retries_once_on_transport_error(monkeypatch, caplog):
    _set_mailjet_env(monkeypatch)
    monkeypatch.setattr(email_service.time, "sleep", lambda _: None)
    calls = _install_fake_post_sequence(
        monkeypatch,
        [
            httpx.RequestError("network down"),
            FakeHttpxResponse(200, json_data=_mailjet_success_body()),
        ],
    )

    with caplog.at_level(logging.INFO, logger="app.services.email_service"):
        email_service.send_email(
            to_email="user@example.com",
            subject="Retry transport",
            text_body="Body",
        )

    assert len(calls) == 2
    assert "outcome=transport_error" in caplog.text
    assert "Mailjet retry scheduled" in caplog.text
    assert "reason=transport_error" in caplog.text
    assert "outcome=success" in caplog.text


def test_send_email_retries_once_on_http_500(monkeypatch, caplog):
    _set_mailjet_env(monkeypatch)
    monkeypatch.setattr(email_service.time, "sleep", lambda _: None)
    calls = _install_fake_post_sequence(
        monkeypatch,
        [
            FakeHttpxResponse(500, json_data={"ErrorMessage": "temporary outage"}),
            FakeHttpxResponse(200, json_data=_mailjet_success_body()),
        ],
    )

    with caplog.at_level(logging.INFO, logger="app.services.email_service"):
        email_service.send_email(
            to_email="user@example.com",
            subject="Retry 500",
            text_body="Body",
        )

    assert len(calls) == 2
    assert "outcome=http_error" in caplog.text
    assert "http_status=500" in caplog.text
    assert "reason=http_500" in caplog.text
    assert "outcome=success" in caplog.text


def test_send_email_retries_once_on_http_429(monkeypatch, caplog):
    _set_mailjet_env(monkeypatch)
    monkeypatch.setattr(email_service.time, "sleep", lambda _: None)
    calls = _install_fake_post_sequence(
        monkeypatch,
        [
            FakeHttpxResponse(429, json_data={"ErrorMessage": "rate limited"}),
            FakeHttpxResponse(200, json_data=_mailjet_success_body()),
        ],
    )

    with caplog.at_level(logging.INFO, logger="app.services.email_service"):
        email_service.send_email(
            to_email="user@example.com",
            subject="Retry 429",
            text_body="Body",
        )

    assert len(calls) == 2
    assert "outcome=http_error" in caplog.text
    assert "http_status=429" in caplog.text
    assert "reason=http_429" in caplog.text
    assert "outcome=success" in caplog.text


def test_send_email_does_not_retry_on_http_400(monkeypatch, caplog):
    _set_mailjet_env(monkeypatch)
    monkeypatch.setattr(email_service.time, "sleep", lambda _: None)
    calls = _install_fake_post_sequence(
        monkeypatch,
        [
            FakeHttpxResponse(400, json_data={"ErrorMessage": "sender is not verified"}),
        ],
    )

    with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
        with pytest.raises(RuntimeError, match="HTTP 400"):
            email_service.send_email(
                to_email="user@example.com",
                subject="No retry 400",
                text_body="Body",
            )

    assert len(calls) == 1
    assert "outcome=http_error" in caplog.text
    assert "retryable=False" in caplog.text


def test_send_email_logs_do_not_include_mailjet_secrets_on_failure(monkeypatch, caplog):
    _set_mailjet_env(monkeypatch)
    response = FakeHttpxResponse(500, json_data={"ErrorMessage": "temporary outage"})
    _install_fake_post(monkeypatch, response)
    monkeypatch.setattr(email_service.time, "sleep", lambda _: None)

    with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
        with pytest.raises(RuntimeError):
            email_service.send_email(
                to_email="user@example.com",
                subject="Failure log sanitization",
                text_body="Body",
            )

    assert "test_api_key" not in caplog.text
    assert "test_secret_key" not in caplog.text
    assert "user@example.com" not in caplog.text
    assert "us***@example.com" in caplog.text


def test_send_email_raises_when_status_is_not_success(monkeypatch):
    _set_mailjet_env(monkeypatch)
    response = FakeHttpxResponse(
        200,
        json_data={
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
        },
    )
    _install_fake_post(monkeypatch, response)

    with pytest.raises(RuntimeError, match="rejected"):
        email_service.send_email(
            to_email="user@example.com",
            subject="Test",
            text_body="Body",
        )


def test_send_verify_email_builds_link_and_subject(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com")
    monkeypatch.setenv("EMAIL_VERIFY_PATH", "/verify-email")

    captured: dict = {}

    def fake_send_email(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(email_service, "send_email", fake_send_email)

    email_service.send_verify_email(
        to_email="user@example.com",
        display_name="Alice",
        token="verify_token",
    )

    assert captured["to_email"] == "user@example.com"
    assert captured["to_name"] == "Alice"
    assert captured["subject"] == "Confirm your email"
    assert "token=verify_token" in captured["text_body"]
    assert "token=verify_token" in captured["html_body"]
    assert "https://frontend.example.com/verify-email" in captured["text_body"]


def test_send_password_reset_email_builds_link_and_subject(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://frontend.example.com")
    monkeypatch.setenv("PASSWORD_RESET_PATH", "/restore-password")

    captured: dict = {}

    def fake_send_email(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(email_service, "send_email", fake_send_email)

    email_service.send_password_reset_email(
        to_email="user@example.com",
        display_name="Alice",
        token="reset_token",
    )

    assert captured["to_email"] == "user@example.com"
    assert captured["to_name"] == "Alice"
    assert captured["subject"] == "Reset your password"
    assert "token=reset_token" in captured["text_body"]
    assert "token=reset_token" in captured["html_body"]
    assert (
        "https://frontend.example.com/restore-password"
        in captured["text_body"]
    )
