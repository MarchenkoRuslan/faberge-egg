import logging

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_s3_client():
    global _client
    if _client is not None:
        return _client

    endpoint = settings.S3_ENDPOINT
    if not endpoint:
        logger.warning("S3_ENDPOINT is not configured; storage service will be unavailable")
        return None

    _client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
        config=BotoConfig(signature_version="s3v4"),
    )
    return _client


def get_presigned_url(key: str, expires_in: int | None = None) -> str | None:
    """Generate a presigned URL for a storage object.

    Returns None when S3 is not configured (graceful degradation for dev/test).
    """
    client = _get_s3_client()
    if client is None:
        return None

    if expires_in is None:
        expires_in = settings.PRESIGNED_URL_EXPIRES

    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError):
        logger.exception("Failed to generate presigned URL for key=%s", key)
        return None


def upload_file(key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
    """Upload bytes to the bucket. Returns True on success."""
    client = _get_s3_client()
    if client is None:
        return False

    try:
        client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return True
    except (BotoCoreError, ClientError):
        logger.exception("Failed to upload file key=%s", key)
        return False
