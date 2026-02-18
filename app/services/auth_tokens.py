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


def _db_datetime(db: Session, value: datetime) -> datetime:
    bind = db.get_bind()
    if bind and bind.dialect.name == "sqlite":
        return value.replace(tzinfo=None)
    return value


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
    token_hash = _hash_token(raw_token)
    now = utcnow()
    db_now = _db_datetime(db, now)

    updated = (
        db.query(OneTimeToken)
        .filter(
            OneTimeToken.token_hash == token_hash,
            OneTimeToken.purpose == purpose,
            OneTimeToken.used_at.is_(None),
            OneTimeToken.expires_at > db_now,
        )
        .update(
            {
                OneTimeToken.used_at: db_now,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        return None

    record = (
        db.query(OneTimeToken)
        .filter(
            OneTimeToken.token_hash == token_hash,
            OneTimeToken.purpose == purpose,
        )
        .first()
    )
    if not record:
        return None
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
    now = utcnow()
    db_now = _db_datetime(db, now)
    updated = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == _hash_token(raw_token),
            RefreshToken.revoked_at.is_(None),
        )
        .update(
            {
                RefreshToken.revoked_at: db_now,
            },
            synchronize_session=False,
        )
    )
    return updated == 1


def revoke_all_refresh_tokens_for_user(db: Session, user_id: int) -> None:
    now = utcnow()
    db_now = _db_datetime(db, now)
    tokens = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .all()
    )
    for token in tokens:
        token.revoked_at = db_now
    db.flush()


def rotate_refresh_token(
    db: Session,
    raw_token: str,
    expires_in_days: int,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[int, str] | None:
    token_hash = _hash_token(raw_token)
    now = utcnow()
    db_now = _db_datetime(db, now)

    current = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if not current:
        return None
    if current.revoked_at is not None or _as_utc(current.expires_at) <= now:
        return None

    updated = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.id == current.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > db_now,
        )
        .update(
            {
                RefreshToken.revoked_at: db_now,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        return None

    new_raw, new_record = issue_refresh_token(
        db=db,
        user_id=current.user_id,
        expires_in_days=expires_in_days,
        ip=ip,
        user_agent=user_agent,
    )
    current.replaced_by_id = new_record.id
    db.flush()
    return current.user_id, new_raw
