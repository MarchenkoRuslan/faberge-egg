import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import OneTimeToken, RefreshToken

ONE_TIME_PURPOSE_EMAIL_VERIFY = "email_verify"
ONE_TIME_PURPOSE_PASSWORD_RESET = "password_reset"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(48)


def get_latest_one_time_token(db: Session, user_id: int, purpose: str) -> OneTimeToken | None:
    return (
        db.query(OneTimeToken)
        .filter(OneTimeToken.user_id == user_id, OneTimeToken.purpose == purpose)
        .order_by(OneTimeToken.created_at.desc())
        .first()
    )


def issue_one_time_token(
    db: Session,
    user_id: int,
    purpose: str,
    expires_in_minutes: int,
) -> tuple[str, OneTimeToken]:
    raw = _new_token()
    record = OneTimeToken(
        user_id=user_id,
        purpose=purpose,
        token_hash=_hash_token(raw),
        expires_at=utcnow() + timedelta(minutes=expires_in_minutes),
    )
    db.add(record)
    db.flush()
    return raw, record


def consume_one_time_token(db: Session, raw_token: str, purpose: str) -> OneTimeToken | None:
    record = (
        db.query(OneTimeToken)
        .filter(
            OneTimeToken.token_hash == _hash_token(raw_token),
            OneTimeToken.purpose == purpose,
        )
        .first()
    )
    if not record:
        return None
    if record.used_at is not None or _as_utc(record.expires_at) <= utcnow():
        return None
    record.used_at = utcnow()
    db.flush()
    return record


def issue_refresh_token(
    db: Session,
    user_id: int,
    expires_in_days: int,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, RefreshToken]:
    raw = _new_token()
    record = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(raw),
        expires_at=utcnow() + timedelta(days=expires_in_days),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(record)
    db.flush()
    return raw, record


def get_valid_refresh_token(db: Session, raw_token: str) -> RefreshToken | None:
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == _hash_token(raw_token)).first()
    if not record:
        return None
    if record.revoked_at is not None or _as_utc(record.expires_at) <= utcnow():
        return None
    return record


def revoke_refresh_token(record: RefreshToken, replaced_by_id: int | None = None) -> None:
    record.revoked_at = utcnow()
    record.replaced_by_id = replaced_by_id


def revoke_refresh_token_by_raw(db: Session, raw_token: str) -> bool:
    record = get_valid_refresh_token(db, raw_token)
    if not record:
        return False
    revoke_refresh_token(record)
    db.flush()
    return True


def revoke_all_refresh_tokens_for_user(db: Session, user_id: int) -> None:
    now = utcnow()
    tokens = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .all()
    )
    for token in tokens:
        token.revoked_at = now
    db.flush()
