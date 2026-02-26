"""
Email sending via Resend (https://resend.com).

Uses Resend Python SDK and dashboard templates for:
- Email verification (registration)
- Password reset
- Upsale campaign emails (upsale1, upsale2, upsale3, bonus)

Docs: https://resend.com/docs/send-with-python
Templates: https://resend.com/docs/dashboard/templates/introduction
"""
import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import resend

from app.core.config import settings
from app.shared.utils.redaction import mask_email

logger = logging.getLogger(__name__)

# Template variable names (must match variables defined in your Resend templates)
VAR_CONFIRM_LINK = "CONFIRM_LINK"
VAR_RESET_LINK = "RESET_LINK"
VAR_USER_NAME = "USER_NAME"
VAR_ASSET_NAME = "ASSET_NAME"
VAR_BUY_LINK = "BUY_LINK"


def _get_upsale_template_map() -> dict[str, str]:
    """Build email_type -> Resend template_id mapping from settings.

    Called per-send so newly set env vars are picked up without restart.
    upsale2_reminder reuses the upsale2 template.
    """
    return {
        "upsale1": settings.RESEND_TEMPLATE_UPSALE1,
        "upsale2": settings.RESEND_TEMPLATE_UPSALE2,
        "upsale2_reminder": settings.RESEND_TEMPLATE_UPSALE2,
        "upsale3": settings.RESEND_TEMPLATE_UPSALE3,
        "bonus": settings.RESEND_TEMPLATE_BONUS_UPSALE,
    }


def _build_frontend_link(path: str, token: str) -> str:
    base = f"{settings.FRONTEND_URL.rstrip('/')}/{path.lstrip('/')}"
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["token"] = token
    return urlunparse(parsed._replace(query=urlencode(query)))


def _resend_required_config() -> tuple[str, str]:
    api_key = settings.RESEND_API_KEY
    from_email = settings.RESEND_FROM_EMAIL
    missing = []
    if not api_key:
        missing.append("RESEND_API_KEY")
    if not from_email:
        missing.append("RESEND_FROM_EMAIL")
    if missing:
        raise RuntimeError(
            f"Resend is not configured (RESEND_API_KEY, RESEND_FROM_EMAIL required). "
            f"Missing: {', '.join(missing)}."
        )
    return api_key, from_email


def get_resend_startup_diagnostics() -> tuple[str, list[str]]:
    """Return diagnostics string and list of warnings for Resend config."""
    warnings: list[str] = []
    api_key_set = bool(settings.RESEND_API_KEY)
    from_set = bool(settings.RESEND_FROM_EMAIL)
    template_verify = settings.RESEND_TEMPLATE_VERIFY_EMAIL
    template_reset = settings.RESEND_TEMPLATE_PASSWORD_RESET
    missing = []
    if not api_key_set:
        missing.append("RESEND_API_KEY")
    if not from_set:
        missing.append("RESEND_FROM_EMAIL")
    if not template_verify:
        missing.append("RESEND_TEMPLATE_VERIFY_EMAIL")
    if not template_reset:
        missing.append("RESEND_TEMPLATE_PASSWORD_RESET")
    if missing:
        warnings.append(
            "Resend required for email delivery; missing: " + ", ".join(missing)
        )
    diagnostics = (
        f"resend_configured={api_key_set and from_set}, "
        f"template_verify={template_verify or '<none>'}, "
        f"template_reset={template_reset or '<none>'}, "
        f"missing={','.join(missing) or '<none>'}"
    )
    return diagnostics, warnings


def send_verify_email(to_email: str, display_name: str | None, token: str) -> None:
    """
    Send email verification using Resend template.

    Template must define variables: CONFIRM_LINK, USER_NAME.
    """
    api_key, from_email = _resend_required_config()
    template_id = settings.RESEND_TEMPLATE_VERIFY_EMAIL
    if not template_id:
        raise RuntimeError(
            "RESEND_TEMPLATE_VERIFY_EMAIL is not set; cannot send verification email."
        )
    link = _build_frontend_link(settings.EMAIL_VERIFY_PATH, token)
    user_name = (display_name or "there").strip() or "there"
    resend.api_key = api_key
    params: resend.Emails.SendParams = {
        "from": from_email,
        "to": [to_email],
        "subject": "Confirm your email",
        "template": {
            "id": template_id,
            "variables": {
                VAR_CONFIRM_LINK: link,
                VAR_USER_NAME: user_name,
            },
        },
    }
    try:
        result = resend.Emails.send(params)
    except Exception as e:
        logger.warning(
            "Resend send failure type=verify_email to_email=%s error=%s",
            mask_email(to_email),
            str(e),
        )
        raise RuntimeError(f"Resend send failed: {e}") from e
    logger.info(
        "Resend send success type=verify_email to_email=%s id=%s",
        mask_email(to_email),
        getattr(result, "id", result) or "<none>",
    )


def send_password_reset_email(
    to_email: str, display_name: str | None, token: str
) -> None:
    """
    Send password reset email using Resend template.

    Template must define variables: RESET_LINK, USER_NAME.
    """
    api_key, from_email = _resend_required_config()
    template_id = settings.RESEND_TEMPLATE_PASSWORD_RESET
    if not template_id:
        raise RuntimeError(
            "RESEND_TEMPLATE_PASSWORD_RESET is not set; cannot send password reset email."
        )
    link = _build_frontend_link(settings.PASSWORD_RESET_PATH, token)
    user_name = (display_name or "there").strip() or "there"
    resend.api_key = api_key
    params: resend.Emails.SendParams = {
        "from": from_email,
        "to": [to_email],
        "subject": "Reset your password",
        "template": {
            "id": template_id,
            "variables": {
                VAR_RESET_LINK: link,
                VAR_USER_NAME: user_name,
            },
        },
    }
    try:
        result = resend.Emails.send(params)
    except Exception as e:
        logger.warning(
            "Resend send failure type=password_reset to_email=%s error=%s",
            mask_email(to_email),
            str(e),
        )
        raise RuntimeError(f"Resend send failed: {e}") from e
    logger.info(
        "Resend send success type=password_reset to_email=%s id=%s",
        mask_email(to_email),
        getattr(result, "id", result) or "<none>",
    )


def send_upsale_email(
    to_email: str,
    display_name: str | None,
    email_type: str,
    asset_name: str,
    buy_link: str,
) -> str | None:
    """Send an upsale campaign email using Resend template.

    Returns the Resend message ID on success, or None on failure.
    Raises RuntimeError only for configuration errors; delivery
    failures are logged and return None so the campaign can proceed.
    """
    api_key, from_email = _resend_required_config()
    template_map = _get_upsale_template_map()
    template_id = template_map.get(email_type, "")
    if not template_id:
        raise RuntimeError(
            f"Resend template for upsale email_type={email_type!r} is not configured."
        )

    user_name = (display_name or "there").strip() or "there"
    resend.api_key = api_key
    params: resend.Emails.SendParams = {
        "from": from_email,
        "to": [to_email],
        "subject": f"Special offer for {asset_name}",
        "template": {
            "id": template_id,
            "variables": {
                VAR_USER_NAME: user_name,
                VAR_ASSET_NAME: asset_name,
                VAR_BUY_LINK: buy_link,
            },
        },
    }
    try:
        result = resend.Emails.send(params)
    except Exception as e:
        logger.warning(
            "Resend send failure type=%s to_email=%s error=%s",
            email_type,
            mask_email(to_email),
            str(e),
        )
        return None
    msg_id = getattr(result, "id", None) or (result if isinstance(result, str) else None)
    logger.info(
        "Resend send success type=%s to_email=%s id=%s",
        email_type,
        mask_email(to_email),
        msg_id or "<none>",
    )
    return msg_id
