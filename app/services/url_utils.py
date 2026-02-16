from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def append_query_param(url: str, key: str, value: str | int) -> str:
    """Append a query parameter to URL while preserving existing query params and fragments."""
    parts = urlsplit(url)
    query_params = parse_qsl(parts.query, keep_blank_values=True)
    query_params.append((key, str(value)))
    updated_query = urlencode(query_params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, updated_query, parts.fragment))
