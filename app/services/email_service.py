import smtplib
from email.message import EmailMessage
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.config import settings


def _build_frontend_link(path: str, token: str) -> str:
    base = f"{settings.FRONTEND_URL.rstrip('/')}/{path.lstrip('/')}"
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["token"] = token
    return urlunparse(parsed._replace(query=urlencode(query)))


def _send_email(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        raise RuntimeError("SMTP is not configured (SMTP_HOST and SMTP_FROM_EMAIL are required).")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        smtp.ehlo()
        if settings.SMTP_USE_TLS:
            smtp.starttls()
            smtp.ehlo()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)


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
    _send_email(to_email=to_email, subject="Confirm your email", text_body=text, html_body=html)


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
    _send_email(to_email=to_email, subject="Reset your password", text_body=text, html_body=html)
