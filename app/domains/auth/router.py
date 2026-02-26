import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.rate_limit import require_email_rate_limit
from app.domains.auth.schemas import (
    EmailVerifyConfirmRequest,
    EmailVerifyRequest,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    MessageResponse,
    PasswordForgotRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    TokenValidateRequest,
    TokenValidateResponse,
)
from app.domains.auth.service import (
    ONE_TIME_PURPOSE_EMAIL_VERIFY,
    ONE_TIME_PURPOSE_PASSWORD_RESET,
    consume_one_time_token,
    create_access_token,
    get_latest_one_time_token,
    get_password_hash,
    issue_one_time_token,
    issue_refresh_token,
    revoke_all_refresh_tokens_for_user,
    revoke_refresh_token_by_raw,
    rotate_refresh_token,
    to_utc,
    utcnow,
    validate_one_time_token,
    verify_password,
)
from app.models import User
from app.shared.email_service import send_password_reset_email, send_verify_email
from app.shared.utils.redaction import mask_email
from app.shared.wallet_service import create_user_wallet

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_token_response(access_token: str, refresh_token: str) -> TokenResponse:
    return TokenResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        expiresIn=settings.JWT_EXPIRE_MINUTES * 60,
        refreshExpiresIn=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60,
    )


def _get_client_ip(request: Request) -> str | None:
    if not request.client:
        return None
    return request.client.host


def _get_user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    if not user_agent:
        return None
    return user_agent[:512]


def _request_correlation_id(request: Request) -> str:
    return (
        request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id")
        or "<missing>"
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    summary="Register a new user",
)
def register(
    body: RegisterRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _rate_limit: Annotated[None, Depends(require_email_rate_limit)],
):
    """Register a new user and send email verification link."""
    request_id = _request_correlation_id(request)
    masked_email = mask_email(body.email)
    logger.info(
        "register attempt request_id=%s email=%s",
        request_id,
        masked_email,
    )

    if db.query(User).filter(User.email == body.email).first():
        logger.info(
            "register duplicate_email request_id=%s email=%s",
            request_id,
            masked_email,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        display_name=body.display_name,
        email=body.email,
        hashed_password=get_password_hash(body.password),
        is_email_verified=False,
        terms_accepted_at=utcnow(),
        terms_accepted_ip=_get_client_ip(request),
    )
    db.add(user)
    db.flush()

    verify_token, _ = issue_one_time_token(
        db=db,
        user_id=user.id,
        purpose=ONE_TIME_PURPOSE_EMAIL_VERIFY,
        expires_in_minutes=settings.EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES,
    )

    try:
        logger.info(
            "register verification_email_send_started request_id=%s email=%s user_id=%s",
            request_id,
            masked_email,
            user.id,
        )
        send_verify_email(user.email, user.display_name, verify_token)
        logger.info(
            "register verification_email_sent_ok request_id=%s email=%s user_id=%s",
            request_id,
            masked_email,
            user.id,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "register verification_email_send_failed request_id=%s email=%s user_id=%s",
            request_id,
            masked_email,
            user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to send verification email",
        )

    db.commit()
    db.refresh(user)
    logger.info(
        "register success request_id=%s email=%s user_id=%s",
        request_id,
        masked_email,
        user.id,
    )

    try:
        create_user_wallet(user.id, db)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "register wallet_creation_failed request_id=%s user_id=%s "
            "(user created, wallet can be provisioned later)",
            request_id,
            user.id,
        )

    return RegisterResponse(
        id=user.id,
        email=user.email,
        displayName=user.display_name,
        isEmailVerified=user.is_email_verified,
        requiresEmailVerification=True,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and get access/refresh tokens",
)
def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """Login with email/password and return JWT access + opaque refresh token."""
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified",
        )

    access_token = create_access_token(user.id)
    refresh_token, _ = issue_refresh_token(
        db=db,
        user_id=user.id,
        expires_in_days=settings.JWT_REFRESH_EXPIRE_DAYS,
        ip=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )
    db.commit()

    return _build_token_response(access_token, refresh_token)


@router.post(
    "/verify-email/request",
    response_model=MessageResponse,
    summary="Resend email verification link",
)
def request_email_verification(
    body: EmailVerifyRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _rate_limit: Annotated[None, Depends(require_email_rate_limit)],
):
    """Resend verification email (generic success response for privacy)."""
    user = db.query(User).filter(User.email == body.email).first()
    generic = MessageResponse(message="If the account exists, a verification email has been sent.")
    if not user or user.is_email_verified:
        return generic

    latest = get_latest_one_time_token(db, user.id, ONE_TIME_PURPOSE_EMAIL_VERIFY)
    if latest and to_utc(latest.created_at) > utcnow() - timedelta(seconds=settings.EMAIL_RESEND_COOLDOWN_SECONDS):
        return generic

    verify_token, _ = issue_one_time_token(
        db=db,
        user_id=user.id,
        purpose=ONE_TIME_PURPOSE_EMAIL_VERIFY,
        expires_in_minutes=settings.EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES,
    )
    try:
        send_verify_email(user.email, user.display_name, verify_token)
    except Exception:
        db.rollback()
        logger.exception("Failed to resend verification email to user id=%s", user.id)
        return generic

    db.commit()

    return generic


@router.post(
    "/verify-email/validate",
    response_model=TokenValidateResponse,
    summary="Validate email verification link (token still active)",
)
def validate_email_verification_link(
    body: EmailVerifyConfirmRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Check if the verification link token is still valid. Does not consume the token."""
    token = validate_one_time_token(db, body.token, ONE_TIME_PURPOSE_EMAIL_VERIFY)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link is no longer active",
        )
    return TokenValidateResponse(valid=True)


@router.post(
    "/verify-email/confirm",
    response_model=MessageResponse,
    summary="Confirm email verification token",
)
def confirm_email_verification(
    body: EmailVerifyConfirmRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Confirm user email by one-time token."""
    token = consume_one_time_token(db, body.token, ONE_TIME_PURPOSE_EMAIL_VERIFY)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link is no longer active",
        )

    user = db.query(User).filter(User.id == token.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    if not user.is_email_verified:
        user.is_email_verified = True
        user.email_verified_at = utcnow()
    db.commit()
    return MessageResponse(message="Email has been verified")


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token pair",
)
def refresh_tokens(
    body: RefreshRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """Rotate refresh token and issue fresh access token."""
    rotated = rotate_refresh_token(
        db=db,
        raw_token=body.refresh_token,
        expires_in_days=settings.JWT_REFRESH_EXPIRE_DAYS,
        ip=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )
    if not rotated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id, new_refresh = rotated
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    db.commit()

    access_token = create_access_token(user.id)
    return _build_token_response(access_token, new_refresh)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout by revoking refresh token",
)
def logout(
    body: LogoutRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Revoke refresh token. Always returns success message."""
    revoke_refresh_token_by_raw(db, body.refresh_token)
    db.commit()
    return MessageResponse(message="Logged out")


@router.post(
    "/password/forgot",
    response_model=MessageResponse,
    summary="Request password reset email",
)
def request_password_reset(
    body: PasswordForgotRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _rate_limit: Annotated[None, Depends(require_email_rate_limit)],
):
    """Issue password reset token and send email (privacy-safe response)."""
    user = db.query(User).filter(User.email == body.email).first()
    generic = MessageResponse(message="If the account exists, a reset email has been sent.")
    if not user:
        return generic

    reset_token, _ = issue_one_time_token(
        db=db,
        user_id=user.id,
        purpose=ONE_TIME_PURPOSE_PASSWORD_RESET,
        expires_in_minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    )

    try:
        send_password_reset_email(user.email, user.display_name, reset_token)
    except Exception:
        db.rollback()
        logger.exception("Failed to send password reset email to user id=%s", user.id)
        return generic

    db.commit()

    return generic


@router.post(
    "/password/reset/validate",
    response_model=TokenValidateResponse,
    summary="Validate password reset link (token still active)",
)
def validate_password_reset_link(
    body: TokenValidateRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Check if the password reset link token is still valid. Does not consume the token."""
    token = validate_one_time_token(db, body.token, ONE_TIME_PURPOSE_PASSWORD_RESET)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link is no longer active",
        )
    return TokenValidateResponse(valid=True)


@router.post(
    "/password/reset",
    response_model=MessageResponse,
    summary="Reset password by token",
)
def reset_password(
    body: PasswordResetRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Reset password and revoke all active refresh tokens."""
    token = consume_one_time_token(db, body.token, ONE_TIME_PURPOSE_PASSWORD_RESET)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link is no longer active",
        )

    user = db.query(User).filter(User.id == token.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    user.hashed_password = get_password_hash(body.password)
    revoke_all_refresh_tokens_for_user(db, user.id)
    db.commit()
    return MessageResponse(message="Password has been reset")


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current authenticated user profile",
)
def me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Return profile of the authenticated user."""
    created = current_user.created_at.isoformat() if current_user.created_at else ""
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        displayName=current_user.display_name,
        isEmailVerified=current_user.is_email_verified,
        createdAt=created,
    )
