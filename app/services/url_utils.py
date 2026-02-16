from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException, status


ALLOWED_REDIRECT_SCHEMES = {"http", "https"}


def append_query_param(url: str, key: str, value: str | int) -> str:
    """Append a query parameter to URL while preserving existing query params and fragments."""
    parts = urlsplit(url)
    query_params = parse_qsl(parts.query, keep_blank_values=True)
    query_params.append((key, str(value)))
    updated_query = urlencode(query_params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, updated_query, parts.fragment))


def validate_checkout_redirect_url(url: str, field_name: str) -> str:
    """Validate user-provided redirect URL for checkout.

    Allows only absolute HTTP(S) URLs without embedded user credentials.
    """
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_REDIRECT_SCHEMES or not parts.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be an absolute http(s) URL",
        )
    if parts.username or parts.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must not contain credentials",
        )
    return url
