"""Fetch a GraphQL schema from a live endpoint via introspection."""

from __future__ import annotations

from graphql.utilities import build_client_schema, get_introspection_query, print_schema


def fetch_schema_sdl(
    endpoint: str,
    session: object | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    """Query *endpoint* for its schema via introspection and return SDL text.

    Parameters
    ----------
    endpoint:
        The GraphQL HTTP endpoint URL.
    session:
        An optional ``requests.Session`` to use for the request.  When
        supplied it inherits any auth, cookies, or TLS settings already
        configured on the session.  When omitted a bare ``requests.post``
        call is used instead.
    headers:
        Extra HTTP headers to include in the introspection request (e.g.
        ``{"Authorization": "Bearer <token>"}``).  These are merged on top
        of any headers already set on *session*.

    Returns
    -------
    str
        The schema in SDL (Schema Definition Language) format.

    Raises
    ------
    RuntimeError
        If the HTTP request fails or the response contains GraphQL errors.
    """
    import requests  # imported lazily so the package doesn't hard-require it at import time

    query = get_introspection_query()
    payload = {"query": query}
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    if session is not None:
        response = session.post(endpoint, json=payload, headers=request_headers)  # type: ignore[attr-defined]
    else:
        response = requests.post(endpoint, json=payload, headers=request_headers)

    if not response.ok:
        raise RuntimeError(
            f"Introspection request failed: {response.status_code} {response.reason}"
        )

    data = response.json()
    if "errors" in data:
        messages = "; ".join(e.get("message", str(e)) for e in data["errors"])
        raise RuntimeError(f"GraphQL errors during introspection: {messages}")

    schema = build_client_schema(data["data"])
    return print_schema(schema)
