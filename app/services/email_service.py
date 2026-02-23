import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _build_frontend_link(path: str, token: str) -> str:
    base = f"{settings.FRONTEND_URL.rstrip('/')}/{path.lstrip('/')}"
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["token"] = token
    return urlunparse(parsed._replace(query=urlencode(query)))


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


def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    to_name: str | None = None,
) -> None:
    api_key, secret_key, from_email = _mailjet_required_config()

    recipient: dict[str, str] = {"Email": to_email}
    if to_name:
        recipient["Name"] = to_name

    message: dict[str, object] = {
        "From": {
            "Email": from_email,
            "Name": settings.MAILJET_FROM_NAME,
        },
        "To": [recipient],
        "Subject": subject,
        "TextPart": text_body,
    }
    if html_body is not None:
        message["HTMLPart"] = html_body

    try:
        response = httpx.post(
            settings.MAILJET_API_URL,
            auth=(api_key, secret_key),
            json={"Messages": [message]},
            timeout=settings.MAILJET_TIMEOUT_SECONDS,
        )
    except httpx.RequestError as exc:
        raise RuntimeError("Mailjet send request failed") from exc

    response_json = None
    try:
        response_json = response.json()
    except (ValueError, httpx.DecodingError):
        response_json = None

    if response.status_code >= 400:
        if isinstance(response_json, dict):
            detail = _mailjet_error_detail_from_dict(response_json)
        else:
            try:
                response_text = response.text
            except httpx.DecodingError:
                response_text = ""
            detail = (response_text or "unknown error").strip() or "unknown error"
        logger.warning("Mailjet HTTP error status=%s detail=%s", response.status_code, detail)
        raise RuntimeError(f"Mailjet send failed with HTTP {response.status_code}: {detail}")

    if not isinstance(response_json, dict):
        raise RuntimeError(f"Mailjet send failed: invalid JSON response (HTTP {response.status_code})")

    messages = response_json.get("Messages")
    if not isinstance(messages, list) or not messages or not isinstance(messages[0], dict):
        raise RuntimeError("Mailjet send failed: invalid response payload (missing Messages)")

    first_message = messages[0]
    status = str(first_message.get("Status", "")).lower()
    if status != "success":
        detail = _mailjet_message_error_detail(first_message)
        logger.warning("Mailjet message failure status=%s detail=%s", first_message.get("Status"), detail)
        raise RuntimeError(f"Mailjet send failed: {detail}")


def send_verify_email(to_email: str, display_name: str | None, token: str) -> None:
    link = _build_frontend_link(settings.EMAIL_VERIFY_PATH, token)
    name = display_name or "there"
    text = (
        f"Hi {name},\n\n"
        "Please confirm your email address by opening this link:\n"
        f"{link}\n\n"
        "If you did not create this account, ignore this message."
    )
    html = (
        f"<p>Hi {name},</p>"
        "<p>Please confirm your email address by clicking the link below:</p>"
        f"<p><a href=\"{link}\">Confirm email</a></p>"
        "<p>If you did not create this account, ignore this message.</p>"
    )
    send_email(
        to_email=to_email,
        to_name=display_name,
        subject="Confirm your email",
        text_body=text,
        html_body=html,
    )


def send_password_reset_email(to_email: str, display_name: str | None, token: str) -> None:
    link = _build_frontend_link(settings.PASSWORD_RESET_PATH, token)
    name = display_name or "there"
    text = (
        f"Hi {name},\n\n"
        "You requested a password reset. Open this link to set a new password:\n"
        f"{link}\n\n"
        "If you did not request this, ignore this message."
    )
    html = (
        f"<p>Hi {name},</p>"
        "<p>You requested a password reset. Click the link below to set a new password:</p>"
        f"<p><a href=\"{link}\">Reset password</a></p>"
        "<p>If you did not request this, ignore this message.</p>"
    )
    send_email(
        to_email=to_email,
        to_name=display_name,
        subject="Reset your password",
        text_body=text,
        html_body=html,
    )
