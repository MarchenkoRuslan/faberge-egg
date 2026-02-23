import html
import logging
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.config import settings
from app.utils.redaction import mask_email

logger = logging.getLogger(__name__)

_MAILJET_SEND_API_URL = "https://api.mailjet.com/v3.1/send"
_DEFAULT_MAILJET_HOST = "api.mailjet.com"
_MAILJET_RETRYABLE_HTTP_STATUS_CODES = {429, 409}
_MAILJET_MAX_RETRIES = 1
_MAILJET_RETRY_DELAY_SECONDS = 0.25


def _build_frontend_link(path: str, token: str) -> str:
    base = f"{settings.FRONTEND_URL.rstrip('/')}/{path.lstrip('/')}"
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["token"] = token
    return urlunparse(parsed._replace(query=urlencode(query)))


def _html_escape_text(text: str) -> str:
    """Escape text for safe use inside HTML body (e.g. display name)."""
    return html.escape(str(text), quote=False)


def _html_escape_attr(value: str) -> str:
    """Escape value for safe use in an HTML attribute (e.g. href)."""
    return html.escape(str(value), quote=True)


def _wrap_html_body(body_fragment: str) -> str:
    """Wrap HTML fragment in a minimal valid document for email clients."""
    return (
        "<!DOCTYPE html>"
        "<html lang=\"en\">"
        "<head>"
        "<meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "</head>"
        "<body>"
        f"{body_fragment}"
        "</body>"
        "</html>"
    )


def _mailjet_required_config() -> tuple[str, str, str]:
    api_key = settings.MAILJET_API_KEY
    secret_key = settings.MAILJET_SECRET_KEY
    from_email = settings.MAILJET_FROM_EMAIL

    missing = []
    if not api_key:
        missing.append("MAILJET_API_KEY")
    if not secret_key:
        missing.append("MAILJET_SECRET_KEY")
    if not from_email:
        missing.append("MAILJET_FROM_EMAIL")
    if missing:
        required = "MAILJET_API_KEY, MAILJET_SECRET_KEY, MAILJET_FROM_EMAIL"
        raise RuntimeError(
            f"Mailjet is not configured ({required} are required). Missing: {', '.join(missing)}."
        )
    return api_key, secret_key, from_email


def _mailjet_error_detail_from_dict(data: dict) -> str:
    for key in ("ErrorMessage", "ErrorInfo", "ErrorCode", "ErrorIdentifier"):
        value = data.get(key)
        if value:
            return f"{key}={value}"
    return "unknown error"


def _mailjet_message_error_detail(message: dict) -> str:
    errors = message.get("Errors")
    if isinstance(errors, list) and errors:
        first_error = errors[0]
        if isinstance(first_error, dict):
            parts = []
            for key in ("ErrorMessage", "ErrorCode", "ErrorIdentifier", "StatusCode"):
                value = first_error.get(key)
                if value not in (None, ""):
                    parts.append(f"{key}={value}")
            if parts:
                return ", ".join(parts)
    return _mailjet_error_detail_from_dict(message)


def _mailjet_send_url() -> str:
    """Return Send API URL, normalized (no trailing slash) per Mailjet docs."""
    raw = (settings.MAILJET_API_URL or _MAILJET_SEND_API_URL).strip()
    return raw.rstrip("/") or _MAILJET_SEND_API_URL


def _mailjet_endpoint_host() -> str:
    return urlparse(_mailjet_send_url()).hostname or "<missing>"


def get_mailjet_startup_diagnostics() -> tuple[str, list[str]]:
    warnings: list[str] = []
    api_host = _mailjet_endpoint_host()

    required_presence = {
        "MAILJET_API_KEY": bool(settings.MAILJET_API_KEY.strip()),
        "MAILJET_SECRET_KEY": bool(settings.MAILJET_SECRET_KEY.strip()),
        "MAILJET_FROM_EMAIL": bool(settings.MAILJET_FROM_EMAIL.strip()),
    }
    missing = [name for name, present in required_presence.items() if not present]

    from_email = settings.MAILJET_FROM_EMAIL.strip()
    from_domain = from_email.split("@", 1)[1] if "@" in from_email else "<missing>"

    if api_host != _DEFAULT_MAILJET_HOST:
        warnings.append(
            "MAILJET_API_URL host differs from default "
            f"(host={api_host}, expected={_DEFAULT_MAILJET_HOST})."
        )
    if missing:
        warnings.append(
            "Mailjet required variables are missing for email delivery: " + ", ".join(missing)
        )
    if from_email and "@" not in from_email:
        warnings.append("MAILJET_FROM_EMAIL does not look like a valid email address.")

    diagnostics = (
        f"host={api_host}, timeout_seconds={settings.MAILJET_TIMEOUT_SECONDS}, "
        f"required_config_present={len(missing) == 0}, missing={','.join(missing) or '<none>'}, "
        f"from_email_domain={from_domain}"
    )
    return diagnostics, warnings


def _mailjet_http_error_detail(response: httpx.Response, response_json: object) -> str:
    if isinstance(response_json, dict):
        messages = response_json.get("Messages")
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            msg_detail = _mailjet_message_error_detail(messages[0])
            if msg_detail and msg_detail != "unknown error":
                return msg_detail
        return _mailjet_error_detail_from_dict(response_json)
    try:
        response_text = response.text
    except httpx.DecodingError:
        response_text = ""
    return (response_text or "unknown error").strip() or "unknown error"


def _should_retry_mailjet_http_status(status_code: int) -> bool:
    return status_code in _MAILJET_RETRYABLE_HTTP_STATUS_CODES or status_code >= 500


def _log_mailjet_failure(
    *,
    outcome: str,
    endpoint_host: str,
    to_email: str,
    subject: str,
    detail: str,
    attempt: int,
    max_attempts: int,
    http_status: int | None = None,
    retryable: bool = False,
) -> None:
    logger.warning(
        "Mailjet send failure outcome=%s host=%s http_status=%s to_email=%s subject=%s "
        "attempt=%s/%s retryable=%s detail=%s",
        outcome,
        endpoint_host,
        http_status if http_status is not None else "<none>",
        mask_email(to_email),
        subject,
        attempt,
        max_attempts,
        retryable,
        detail,
    )


def _log_mailjet_retry(
    *,
    endpoint_host: str,
    to_email: str,
    subject: str,
    next_attempt: int,
    max_attempts: int,
    reason: str,
) -> None:
    logger.info(
        "Mailjet retry scheduled host=%s to_email=%s subject=%s next_attempt=%s/%s delay_seconds=%s reason=%s",
        endpoint_host,
        mask_email(to_email),
        subject,
        next_attempt,
        max_attempts,
        _MAILJET_RETRY_DELAY_SECONDS,
        reason,
    )


def _build_mailjet_message(
    *,
    from_email: str,
    to_email: str,
    to_name: str | None,
    subject: str,
    text_body: str,
    html_body: str | None,
) -> dict[str, object]:
    """Build one message object per Send API v3.1: From, To, Subject, TextPart, HTMLPart."""
    to_entry: dict[str, str] = {"Email": to_email}
    if to_name:
        to_entry["Name"] = to_name
    message: dict[str, object] = {
        "From": {
            "Email": from_email,
            "Name": settings.MAILJET_FROM_NAME or "Mailjet",
        },
        "To": [to_entry],
        "Subject": subject,
        "TextPart": text_body,
    }
    if html_body is not None and html_body.strip():
        message["HTMLPart"] = html_body.strip()
    return message


def _send_mailjet_request(
    api_key: str,
    secret_key: str,
    message: dict[str, object],
) -> httpx.Response:
    """POST to Mailjet Send API v3.1 with Basic Auth and JSON body per official docs."""
    url = _mailjet_send_url()
    body = {"Messages": [message]}
    return httpx.post(
        url,
        auth=(api_key, secret_key),
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=settings.MAILJET_TIMEOUT_SECONDS,
    )


def _response_json_or_none(response: httpx.Response) -> object | None:
    try:
        return response.json()
    except (ValueError, httpx.DecodingError):
        return None


def _raise_for_mailjet_success_payload(
    *,
    response: httpx.Response,
    response_json: object,
    endpoint_host: str,
    to_email: str,
    subject: str,
    attempt: int,
    max_attempts: int,
) -> dict:
    if not isinstance(response_json, dict):
        _log_mailjet_failure(
            outcome="invalid_response",
            endpoint_host=endpoint_host,
            to_email=to_email,
            subject=subject,
            detail="invalid JSON response",
            attempt=attempt,
            max_attempts=max_attempts,
            http_status=response.status_code,
        )
        raise RuntimeError(f"Mailjet send failed: invalid JSON response (HTTP {response.status_code})")

    messages = response_json.get("Messages")
    if not isinstance(messages, list) or not messages or not isinstance(messages[0], dict):
        _log_mailjet_failure(
            outcome="invalid_response",
            endpoint_host=endpoint_host,
            to_email=to_email,
            subject=subject,
            detail="missing Messages",
            attempt=attempt,
            max_attempts=max_attempts,
            http_status=response.status_code,
        )
        raise RuntimeError("Mailjet send failed: invalid response payload (missing Messages)")

    first_message = messages[0]
    status = str(first_message.get("Status", "")).lower()
    if status != "success":
        detail = _mailjet_message_error_detail(first_message)
        _log_mailjet_failure(
            outcome="message_error",
            endpoint_host=endpoint_host,
            to_email=to_email,
            subject=subject,
            detail=detail,
            attempt=attempt,
            max_attempts=max_attempts,
            http_status=response.status_code,
        )
        raise RuntimeError(f"Mailjet send failed: {detail}")
    return first_message


def _extract_mailjet_response_ids(first_message: dict) -> tuple[object | None, object | None]:
    message_id = None
    message_uuid = None
    response_recipients = first_message.get("To")
    if isinstance(response_recipients, list) and response_recipients:
        first_recipient = response_recipients[0]
        if isinstance(first_recipient, dict):
            message_id = first_recipient.get("MessageID")
            message_uuid = first_recipient.get("MessageUUID")
    return message_id, message_uuid


def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    to_name: str | None = None,
) -> None:
    api_key, secret_key, from_email = _mailjet_required_config()
    endpoint_host = _mailjet_endpoint_host()
    if endpoint_host != _DEFAULT_MAILJET_HOST:
        logger.warning(
            "Mailjet API URL host differs from default host=%s expected=%s",
            endpoint_host,
            _DEFAULT_MAILJET_HOST,
        )

    message = _build_mailjet_message(
        from_email=from_email,
        to_email=to_email,
        to_name=to_name,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )

    max_attempts = _MAILJET_MAX_RETRIES + 1
    for attempt in range(1, max_attempts + 1):
        try:
            response = _send_mailjet_request(api_key, secret_key, message)
        except httpx.RequestError as exc:
            retryable = attempt < max_attempts
            _log_mailjet_failure(
                outcome="transport_error",
                endpoint_host=endpoint_host,
                to_email=to_email,
                subject=subject,
                detail=str(exc) or exc.__class__.__name__,
                attempt=attempt,
                max_attempts=max_attempts,
                retryable=retryable,
            )
            if retryable:
                _log_mailjet_retry(
                    endpoint_host=endpoint_host,
                    to_email=to_email,
                    subject=subject,
                    next_attempt=attempt + 1,
                    max_attempts=max_attempts,
                    reason="transport_error",
                )
                time.sleep(_MAILJET_RETRY_DELAY_SECONDS)
                continue
            raise RuntimeError("Mailjet send request failed") from exc

        response_json = _response_json_or_none(response)

        if response.status_code >= 400:
            detail = _mailjet_http_error_detail(response, response_json)
            retryable = _should_retry_mailjet_http_status(response.status_code) and attempt < max_attempts
            _log_mailjet_failure(
                outcome="http_error",
                endpoint_host=endpoint_host,
                to_email=to_email,
                subject=subject,
                detail=detail,
                attempt=attempt,
                max_attempts=max_attempts,
                http_status=response.status_code,
                retryable=retryable,
            )
            if retryable:
                _log_mailjet_retry(
                    endpoint_host=endpoint_host,
                    to_email=to_email,
                    subject=subject,
                    next_attempt=attempt + 1,
                    max_attempts=max_attempts,
                    reason=f"http_{response.status_code}",
                )
                time.sleep(_MAILJET_RETRY_DELAY_SECONDS)
                continue
            raise RuntimeError(f"Mailjet send failed with HTTP {response.status_code}: {detail}")

        first_message = _raise_for_mailjet_success_payload(
            response=response,
            response_json=response_json,
            endpoint_host=endpoint_host,
            to_email=to_email,
            subject=subject,
            attempt=attempt,
            max_attempts=max_attempts,
        )
        message_id, message_uuid = _extract_mailjet_response_ids(first_message)

        logger.info(
            "Mailjet send success outcome=success host=%s http_status=%s from_email=%s to_email=%s subject=%s "
            "attempt=%s/%s message_id=%s message_uuid=%s",
            endpoint_host,
            response.status_code,
            mask_email(from_email),
            mask_email(to_email),
            subject,
            attempt,
            max_attempts,
            message_id or "<missing>",
            message_uuid or "<missing>",
        )
        return


def send_verify_email(to_email: str, display_name: str | None, token: str) -> None:
    link = _build_frontend_link(settings.EMAIL_VERIFY_PATH, token)
    name = display_name or "there"
    name_safe = _html_escape_text(name)
    link_safe = _html_escape_attr(link)
    text = (
        f"Hi {name},\n\n"
        "Please confirm your email address by opening this link:\n"
        f"{link}\n\n"
        "If you did not create this account, ignore this message."
    )
    html_fragment = (
        f"<p>Hi {name_safe},</p>"
        "<p>Please confirm your email address by clicking the link below:</p>"
        f"<p><a href=\"{link_safe}\">Confirm email</a></p>"
        "<p>If you did not create this account, ignore this message.</p>"
    )
    send_email(
        to_email=to_email,
        to_name=display_name,
        subject="Confirm your email",
        text_body=text,
        html_body=_wrap_html_body(html_fragment),
    )


def send_password_reset_email(to_email: str, display_name: str | None, token: str) -> None:
    link = _build_frontend_link(settings.PASSWORD_RESET_PATH, token)
    name = display_name or "there"
    name_safe = _html_escape_text(name)
    link_safe = _html_escape_attr(link)
    text = (
        f"Hi {name},\n\n"
        "You requested a password reset. Open this link to set a new password:\n"
        f"{link}\n\n"
        "If you did not request this, ignore this message."
    )
    html_fragment = (
        f"<p>Hi {name_safe},</p>"
        "<p>You requested a password reset. Click the link below to set a new password:</p>"
        f"<p><a href=\"{link_safe}\">Reset password</a></p>"
        "<p>If you did not request this, ignore this message.</p>"
    )
    send_email(
        to_email=to_email,
        to_name=display_name,
        subject="Reset your password",
        text_body=text,
        html_body=_wrap_html_body(html_fragment),
    )
