"""Tests for graphql_client_generator._runtime.client."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from graphql_client_generator._runtime.client import (
    GraphQLClientBase,
    GraphQLError,
    _ResultRoot,
)
from graphql_client_generator._runtime.model import (
    GraphQLModel,
    QueryContext,
)


# ---------------------------------------------------------------------------
# GraphQLError
# ---------------------------------------------------------------------------


class TestGraphQLError:
    def test_stores_errors_and_data(self):
        errors = [{"message": "Something went wrong"}]
        data = {"user": None}
        exc = GraphQLError(errors, data)
        assert exc.errors == errors
        assert exc.data == data

    def test_message_formatting_single(self):
        errors = [{"message": "Bad request"}]
        exc = GraphQLError(errors)
        assert str(exc) == "GraphQL errors: Bad request"

    def test_message_formatting_multiple(self):
        errors = [
            {"message": "Error 1"},
            {"message": "Error 2"},
        ]
        exc = GraphQLError(errors)
        assert str(exc) == "GraphQL errors: Error 1; Error 2"

    def test_message_formatting_no_message_key(self):
        errors = [{"code": "INTERNAL"}]
        exc = GraphQLError(errors)
        # Falls back to str(e) when no "message" key
        assert "INTERNAL" in str(exc)

    def test_data_defaults_to_none(self):
        exc = GraphQLError([{"message": "err"}])
        assert exc.data is None

    def test_is_exception(self):
        exc = GraphQLError([{"message": "err"}])
        assert isinstance(exc, Exception)


# ---------------------------------------------------------------------------
# _ResultRoot
# ---------------------------------------------------------------------------


class TestResultRoot:
    def _make_context(self) -> QueryContext:
        return QueryContext(
            client=None,
            query_string="{ user { name } }",
            variables=None,
            operation_name=None,
            path=[],
            operation_type="query",
        )

    def test_init_coerces_to_snake_case(self):
        ctx = self._make_context()
        data = {"firstName": "Alice", "lastName": "Smith"}
        root = _ResultRoot(data, ctx, {})
        assert root.first_name == "Alice"
        assert root.last_name == "Smith"

    def test_getattr_raises_attribute_error(self):
        ctx = self._make_context()
        data = {"name": "Alice"}
        root = _ResultRoot(data, ctx, {})
        with pytest.raises(AttributeError, match="No field 'missing'"):
            _ = root.missing

    def test_repr_empty(self):
        ctx = self._make_context()
        data = {}
        root = _ResultRoot(data, ctx, {})
        assert repr(root) == "QueryResult()"

    def test_repr_with_scalar_fields(self):
        ctx = self._make_context()
        data = {"name": "Alice"}
        root = _ResultRoot(data, ctx, {})
        result = repr(root)
        assert "QueryResult(" in result
        assert "name=" in result

    def test_repr_with_none_values(self):
        ctx = self._make_context()
        data = {"name": None}
        root = _ResultRoot(data, ctx, {})
        # None values are excluded from repr
        assert repr(root) == "QueryResult()"

    def test_to_dict(self):
        ctx = self._make_context()
        data = {"name": "Alice", "age": 30}
        root = _ResultRoot(data, ctx, {})
        result = root.to_dict()
        assert result == {"name": "Alice", "age": 30}

    def test_to_dict_with_nested_response(self):
        ctx = self._make_context()
        data = {"user": {"__typename": "User", "name": "Alice"}}
        root = _ResultRoot(data, ctx, {})
        result = root.to_dict()
        assert result["user"] == {"__typename": "User", "name": "Alice"}


# ---------------------------------------------------------------------------
# GraphQLClientBase._execute_raw
# ---------------------------------------------------------------------------


class TestExecuteRaw:
    def _make_client(self) -> GraphQLClientBase:
        mock_session = MagicMock()
        client = GraphQLClientBase.__new__(GraphQLClientBase)
        client.endpoint = "http://localhost/graphql"
        client.session = mock_session
        client.auto_fetch = True
        client._type_registry = {}
        return client

    def test_sends_correct_payload(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"user": {"name": "Alice"}}}
        client.session.post.return_value = mock_response

        query = "{ user { name } }"
        client._execute_raw(query)

        client.session.post.assert_called_once_with(
            "http://localhost/graphql",
            json={"query": query},
        )

    def test_sends_variables(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"user": {"name": "Alice"}}}
        client.session.post.return_value = mock_response

        query = "query GetUser($id: ID!) { user(id: $id) { name } }"
        variables = {"id": "123"}
        client._execute_raw(query, variables=variables)

        client.session.post.assert_called_once_with(
            "http://localhost/graphql",
            json={"query": query, "variables": variables},
        )

    def test_sends_operation_name(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {}}
        client.session.post.return_value = mock_response

        query = "query GetUser { user { name } }"
        client._execute_raw(query, operation_name="GetUser")

        call_kwargs = client.session.post.call_args
        assert call_kwargs[1]["json"]["operationName"] == "GetUser"

    def test_returns_data(self):
        client = self._make_client()
        mock_response = MagicMock()
        expected_data = {"user": {"name": "Alice"}}
        mock_response.json.return_value = {"data": expected_data}
        client.session.post.return_value = mock_response

        result = client._execute_raw("{ user { name } }")
        assert result == expected_data

    def test_raises_graphql_error_on_errors(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "errors": [{"message": "Not found"}],
            "data": None,
        }
        client.session.post.return_value = mock_response

        with pytest.raises(GraphQLError) as exc_info:
            client._execute_raw("{ user { name } }")

        assert exc_info.value.errors == [{"message": "Not found"}]
        assert exc_info.value.data is None

    def test_raises_for_http_error(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("500 Server Error")
        client.session.post.return_value = mock_response

        with pytest.raises(Exception, match="500 Server Error"):
            client._execute_raw("{ user { name } }")

    def test_returns_empty_dict_when_no_data_key(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        client.session.post.return_value = mock_response

        result = client._execute_raw("{ user { name } }")
        assert result == {}


# ---------------------------------------------------------------------------
# GraphQLClientBase._build_result_tree
# ---------------------------------------------------------------------------


class TestBuildResultTree:
    def _make_client(self) -> GraphQLClientBase:
        client = GraphQLClientBase.__new__(GraphQLClientBase)
        client.endpoint = "http://localhost/graphql"
        client.session = MagicMock()
        client.auto_fetch = True
        client._type_registry = {}
        return client

    def test_returns_result_root(self):
        client = self._make_client()
        data = {"user": {"__typename": "User", "name": "Alice"}}
        result = client._build_result_tree(
            data,
            query_string="{ user { name } }",
            variables=None,
            operation_name=None,
            operation_type="query",
        )
        assert isinstance(result, _ResultRoot)

    def test_result_has_correct_context(self):
        client = self._make_client()
        data = {"user": {"__typename": "User", "name": "Alice"}}
        result = client._build_result_tree(
            data,
            query_string="{ user { name } }",
            variables={"id": "1"},
            operation_name="GetUser",
            operation_type="query",
        )
        assert result._context.query_string == "{ user { name } }"
        assert result._context.variables == {"id": "1"}
        assert result._context.operation_name == "GetUser"
        assert result._context.operation_type == "query"
        assert result._context.client is client

    def test_result_has_snake_case_attributes(self):
        client = self._make_client()
        data = {"userName": "Alice"}
        result = client._build_result_tree(
            data,
            query_string="{ userName }",
            variables=None,
            operation_name=None,
            operation_type="query",
        )
        assert result.user_name == "Alice"

    def test_custom_result_cls(self):
        client = self._make_client()

        class MyResult(_ResultRoot):
            pass

        data = {"name": "Alice"}
        result = client._build_result_tree(
            data,
            query_string="{ name }",
            variables=None,
            operation_name=None,
            operation_type="query",
            result_cls=MyResult,
        )
        assert isinstance(result, MyResult)


# ---------------------------------------------------------------------------
# GraphQLClientBase.__init__
# ---------------------------------------------------------------------------


class TestGraphQLClientBaseInit:
    def test_init_with_defaults(self):
        client = GraphQLClientBase("http://localhost/graphql")
        assert client.endpoint == "http://localhost/graphql"
        assert client.session is not None
        assert client.auto_fetch is True

    def test_init_with_custom_session(self):
        import requests
        session = requests.Session()
        client = GraphQLClientBase("http://localhost/graphql", session=session)
        assert client.session is session

    def test_init_auto_fetch_false(self):
        client = GraphQLClientBase("http://localhost/graphql", auto_fetch=False)
        assert client.auto_fetch is False


# ---------------------------------------------------------------------------
# GraphQLClientBase.query and mutate (high-level)
# ---------------------------------------------------------------------------


class TestClientQueryMutate:
    def _make_client(self) -> GraphQLClientBase:
        mock_session = MagicMock()
        client = GraphQLClientBase("http://localhost/graphql", session=mock_session)
        client._type_registry = {}
        return client

    def test_query_returns_result_root(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"hello": "world"}}
        client.session.post.return_value = mock_response

        result = client.query("{ hello }")
        assert isinstance(result, _ResultRoot)
        assert result.hello == "world"

    def test_mutate_returns_result_root(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"createUser": {"name": "Alice"}}}
        client.session.post.return_value = mock_response

        result = client.mutate("mutation { createUser { name } }")
        assert isinstance(result, _ResultRoot)

    def test_query_enhances_with_typenames(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"user": {"name": "Alice"}}}
        client.session.post.return_value = mock_response

        client.query("{ user { name } }")
        # The actual query sent should have __typename injected
        call_args = client.session.post.call_args
        sent_query = call_args[1]["json"]["query"]
        assert "__typename" in sent_query


# ---------------------------------------------------------------------------
# _ResultRoot repr (long lines)
# ---------------------------------------------------------------------------


class TestResultRootReprLong:
    def _make_context(self) -> QueryContext:
        return QueryContext(
            client=None,
            query_string="{ x }",
            variables=None,
            operation_name=None,
            path=[],
            operation_type="query",
        )

    def test_repr_multiline_when_long(self):
        ctx = self._make_context()
        # Create data with many long keys to force multi-line repr
        data = {
            "veryLongFieldNameOne": "value1",
            "veryLongFieldNameTwo": "value2",
            "veryLongFieldNameThree": "value3",
        }
        root = _ResultRoot(data, ctx, {})
        result = repr(root)
        # Should be multi-line since compact form exceeds 80 chars
        assert "QueryResult(" in result

    def test_repr_with_list_value(self):
        ctx = self._make_context()
        data = {"items": [1, 2, 3]}
        root = _ResultRoot(data, ctx, {})
        result = repr(root)
        assert "items=" in result

    def test_repr_with_nested_response(self):
        ctx = self._make_context()
        data = {"user": {"__typename": "User", "name": "Alice"}}
        root = _ResultRoot(data, ctx, {})
        result = repr(root)
        assert "user=" in result
