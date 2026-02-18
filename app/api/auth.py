import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_user
from app.models import User, get_db
from app.services.auth_tokens import (
    ONE_TIME_PURPOSE_EMAIL_VERIFY,
    ONE_TIME_PURPOSE_PASSWORD_RESET,
    consume_one_time_token,
    get_latest_one_time_token,
    issue_one_time_token,
    issue_refresh_token,
    revoke_all_refresh_tokens_for_user,
    revoke_refresh_token,
    revoke_refresh_token_by_raw,
    utcnow,
    get_valid_refresh_token,
)
from app.services.email_service import send_password_reset_email, send_verify_email

router = APIRouter()
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
logger = logging.getLogger(__name__)


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class RegisterRequest(CamelModel):
    display_name: str = Field(alias="displayName", min_length=1, max_length=255)
    email: EmailStr
    password: str
    confirm_password: str = Field(alias="confirmPassword")
    terms_agree: bool = Field(alias="termsAgree")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    @model_validator(mode="after")
    def validate_registration(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password confirmation does not match")
        if not self.terms_agree:
            raise ValueError("You must accept Terms of Use")
        return self


class RegisterResponse(CamelModel):
    id: int
    email: str
    display_name: str | None = Field(default=None, alias="displayName")
    is_email_verified: bool = Field(alias="isEmailVerified")
    requires_email_verification: bool = Field(alias="requiresEmailVerification")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"email": "user@example.com", "password": "securepassword"}]},
        populate_by_name=True,
    )


class TokenResponse(CamelModel):
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    token_type: str = "bearer"
    expires_in: int = Field(alias="expiresIn")
    refresh_expires_in: int = Field(alias="refreshExpiresIn")


class EmailVerifyRequest(CamelModel):
    email: EmailStr


class EmailVerifyConfirmRequest(CamelModel):
    token: str


class RefreshRequest(CamelModel):
    refresh_token: str = Field(alias="refreshToken")


class LogoutRequest(CamelModel):
    refresh_token: str = Field(alias="refreshToken")


class PasswordForgotRequest(CamelModel):
    email: EmailStr


class PasswordResetRequest(CamelModel):
    token: str
    password: str
    confirm_password: str = Field(alias="confirmPassword")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    @model_validator(mode="after")
    def validate_confirm(self) -> "PasswordResetRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password confirmation does not match")
        return self


class MessageResponse(CamelModel):
    message: str


class MeResponse(CamelModel):
    id: int
    email: str
    display_name: str | None = Field(default=None, alias="displayName")
    is_email_verified: bool = Field(alias="isEmailVerified")
    created_at: str = Field(alias="createdAt")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _build_token_response(access_token: str, refresh_token: str) -> TokenResponse:
    return TokenResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        expiresIn=settings.JWT_EXPIRE_MINUTES * 60,
        refreshExpiresIn=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60,
    )


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_client_ip(request: Request) -> str | None:
    if not request.client:
        return None
    return request.client.host


def _get_user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    if not user_agent:
        return None
    return user_agent[:512]


@router.post(
    "/register",
    response_model=RegisterResponse,
    summary="Register a new user",
)
def register(
    body: RegisterRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """Register a new user and send email verification link."""
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
    db.commit()
    db.refresh(user)

    try:
        send_verify_email(user.email, user.display_name, verify_token)
    except Exception:
        logger.exception("Failed to send verification email to user id=%s", user.id)

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
    db: Annotated[Session, Depends(get_db)],
):
    """Resend verification email (generic success response for privacy)."""
    user = db.query(User).filter(User.email == body.email).first()
    generic = MessageResponse(message="If the account exists, a verification email has been sent.")
    if not user or user.is_email_verified:
        return generic

    latest = get_latest_one_time_token(db, user.id, ONE_TIME_PURPOSE_EMAIL_VERIFY)
    if latest and _to_utc(latest.created_at) > utcnow() - timedelta(seconds=settings.EMAIL_RESEND_COOLDOWN_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another verification email",
        )

    verify_token, _ = issue_one_time_token(
        db=db,
        user_id=user.id,
        purpose=ONE_TIME_PURPOSE_EMAIL_VERIFY,
        expires_in_minutes=settings.EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES,
    )
    db.commit()

    try:
        send_verify_email(user.email, user.display_name, verify_token)
    except Exception:
        logger.exception("Failed to resend verification email to user id=%s", user.id)

    return generic


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
            detail="Invalid or expired verification token",
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
    current = get_valid_refresh_token(db, body.refresh_token)
    if not current:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user = db.query(User).filter(User.id == current.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    new_refresh, new_record = issue_refresh_token(
        db=db,
        user_id=user.id,
        expires_in_days=settings.JWT_REFRESH_EXPIRE_DAYS,
        ip=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )
    revoke_refresh_token(current, replaced_by_id=new_record.id)
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
    db: Annotated[Session, Depends(get_db)],
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
    db.commit()

    try:
        send_password_reset_email(user.email, user.display_name, reset_token)
    except Exception:
        logger.exception("Failed to send password reset email to user id=%s", user.id)

    return generic


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
            detail="Invalid or expired reset token",
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
