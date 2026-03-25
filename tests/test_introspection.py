"""Tests for graphql_client_generator.introspection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from graphql_client_generator.introspection import fetch_schema_sdl

# A minimal introspection response that graphql-core can build a schema from.
_MINIMAL_INTROSPECTION_RESPONSE = {
    "data": {
        "__schema": {
            "description": None,
            "queryType": {"name": "Query"},
            "mutationType": None,
            "subscriptionType": None,
            "types": [
                {
                    "kind": "OBJECT",
                    "name": "Query",
                    "description": None,
                    "specifiedByURL": None,
                    "fields": [
                        {
                            "name": "hello",
                            "description": None,
                            "args": [],
                            "type": {
                                "kind": "SCALAR",
                                "name": "String",
                                "ofType": None,
                            },
                            "isDeprecated": False,
                            "deprecationReason": None,
                        }
                    ],
                    "inputFields": None,
                    "interfaces": [],
                    "enumValues": None,
                    "possibleTypes": None,
                },
                {
                    "kind": "SCALAR",
                    "name": "String",
                    "description": "Built-in String",
                    "specifiedByURL": None,
                    "fields": None,
                    "inputFields": None,
                    "interfaces": None,
                    "enumValues": None,
                    "possibleTypes": None,
                },
                {
                    "kind": "SCALAR",
                    "name": "Boolean",
                    "description": "Built-in Boolean",
                    "specifiedByURL": None,
                    "fields": None,
                    "inputFields": None,
                    "interfaces": None,
                    "enumValues": None,
                    "possibleTypes": None,
                },
            ],
            "directives": [],
        }
    }
}


def _make_response(json_data: dict, status_code: int = 200, ok: bool = True) -> MagicMock:
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = status_code
    resp.reason = "OK" if ok else "Bad Request"
    resp.json.return_value = json_data
    return resp


class TestFetchSchemaSdl:
    def test_returns_sdl_string(self):
        """A successful introspection request should return SDL text."""
        with patch("requests.post", return_value=_make_response(_MINIMAL_INTROSPECTION_RESPONSE)):
            sdl = fetch_schema_sdl("http://example.com/graphql")
        assert "type Query" in sdl
        assert "hello" in sdl

    def test_uses_provided_headers(self):
        """Extra headers should be forwarded to the HTTP request."""
        with patch(
            "requests.post", return_value=_make_response(_MINIMAL_INTROSPECTION_RESPONSE)
        ) as mock_post:
            fetch_schema_sdl(
                "http://example.com/graphql",
                headers={"Authorization": "Bearer token"},
            )
        _, kwargs = mock_post.call_args
        sent_headers = kwargs.get("headers", {})
        assert sent_headers.get("Authorization") == "Bearer token"

    def test_uses_session_when_provided(self):
        """When a session is provided it should be used instead of requests.post."""
        session = MagicMock()
        session.post.return_value = _make_response(_MINIMAL_INTROSPECTION_RESPONSE)
        with patch("requests.post") as mock_post:
            fetch_schema_sdl("http://example.com/graphql", session=session)
        session.post.assert_called_once()
        mock_post.assert_not_called()

    def test_raises_on_http_error(self):
        """Non-OK HTTP responses should raise RuntimeError."""
        with (
            patch(
                "requests.post",
                return_value=_make_response({}, status_code=401, ok=False),
            ),
            pytest.raises(RuntimeError, match="401"),
        ):
            fetch_schema_sdl("http://example.com/graphql")

    def test_raises_on_graphql_errors(self):
        """GraphQL errors in the response body should raise RuntimeError."""
        error_response = {"errors": [{"message": "Not authorized"}]}
        with (
            patch("requests.post", return_value=_make_response(error_response)),
            pytest.raises(RuntimeError, match="Not authorized"),
        ):
            fetch_schema_sdl("http://example.com/graphql")
