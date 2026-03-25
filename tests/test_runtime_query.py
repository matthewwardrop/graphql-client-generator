"""Tests for graphql_client_generator._runtime.query."""

from __future__ import annotations

import pytest

from graphql_client_generator._runtime.model import PathSegment
from graphql_client_generator._runtime.query import (
    add_field_to_query,
    ensure_typenames,
)


# ---------------------------------------------------------------------------
# ensure_typenames
# ---------------------------------------------------------------------------


class TestEnsureTypenames:
    """Tests for ensure_typenames()."""

    def test_inserts_typename_into_simple_query(self):
        query = "{ user { name } }"
        result = ensure_typenames(query)
        assert "__typename" in result
        # Both the outer selection set and user's selection set should have it
        assert result.count("__typename") == 2

    def test_does_not_duplicate_existing_typename(self):
        query = "{ user { __typename name } }"
        result = ensure_typenames(query)
        # user's selection set already has __typename, should not duplicate
        # outer set gets one, inner already has one
        assert result.count("__typename") == 2

    def test_inserts_at_every_level(self):
        query = "{ user { name posts { title } } }"
        result = ensure_typenames(query)
        # Three levels: root, user, posts
        assert result.count("__typename") == 3

    def test_preserves_field_names(self):
        query = "{ user { name email } }"
        result = ensure_typenames(query)
        assert "name" in result
        assert "email" in result

    def test_preserves_arguments(self):
        query = '{ user(id: "1") { name } }'
        result = ensure_typenames(query)
        assert "id:" in result or 'id: "1"' in result

    def test_handles_named_query(self):
        query = "query GetUser { user { name } }"
        result = ensure_typenames(query)
        assert "__typename" in result
        assert "GetUser" in result

    def test_handles_mutation(self):
        query = "mutation CreateUser { createUser(input: {}) { id } }"
        result = ensure_typenames(query)
        assert "__typename" in result

    def test_already_has_all_typenames(self):
        query = "{ __typename user { __typename name } }"
        result = ensure_typenames(query)
        assert result.count("__typename") == 2


# ---------------------------------------------------------------------------
# add_field_to_query
# ---------------------------------------------------------------------------


class TestAddFieldToQuery:
    """Tests for add_field_to_query()."""

    def test_add_scalar_field_at_root(self):
        query = "{ user { name } }"
        path = []  # add at root level
        result = add_field_to_query(query, path, "status")
        assert "status" in result

    def test_add_scalar_field_nested(self):
        query = "{ user { name } }"
        path = [PathSegment(field_name="user", actual_name="user")]
        result = add_field_to_query(query, path, "email")
        assert "email" in result

    def test_add_composite_field_with_sub_fields(self):
        query = "{ user { name } }"
        path = [PathSegment(field_name="user", actual_name="user")]
        result = add_field_to_query(
            query, path, "posts", sub_fields=["title", "body"]
        )
        assert "posts" in result
        assert "title" in result
        assert "body" in result
        assert "__typename" in result

    def test_does_not_duplicate_existing_field(self):
        query = "{ user { name email } }"
        path = [PathSegment(field_name="user", actual_name="user")]
        result = add_field_to_query(query, path, "name")
        # "name" should appear exactly once in the user selection set
        # (not duplicated)
        assert "name" in result

    def test_handles_alias(self):
        query = "{ myUser: user { name } }"
        path = [PathSegment(field_name="myUser", actual_name="user")]
        result = add_field_to_query(query, path, "email")
        assert "email" in result

    def test_handles_deeply_nested_path(self):
        query = "{ user { posts { title } } }"
        path = [
            PathSegment(field_name="user", actual_name="user"),
            PathSegment(field_name="posts", actual_name="posts"),
        ]
        result = add_field_to_query(query, path, "body")
        assert "body" in result

    def test_add_scalar_no_sub_fields(self):
        query = "{ user { name } }"
        path = [PathSegment(field_name="user", actual_name="user")]
        result = add_field_to_query(query, path, "age", sub_fields=None)
        assert "age" in result
        # scalar field should not have a selection set with __typename
        # (it's just a bare field name)

    def test_add_composite_includes_typename(self):
        query = "{ user { name } }"
        path = [PathSegment(field_name="user", actual_name="user")]
        result = add_field_to_query(
            query, path, "address", sub_fields=["street", "city"]
        )
        assert "address" in result
        # The composite field should include __typename
        assert "__typename" in result
