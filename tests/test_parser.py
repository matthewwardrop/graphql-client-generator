"""Tests for graphql_client_generator.parser."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from graphql import build_schema
from graphql.type import GraphQLList, GraphQLNonNull

from graphql_client_generator.parser import (
    EnumInfo,
    FieldArgInfo,
    FieldInfo,
    InputInfo,
    InterfaceInfo,
    SchemaInfo,
    TypeInfo,
    UnionInfo,
    _detect_one_of_inputs,
    _graphql_type_to_python,
    _is_list_type,
    _type_to_string,
    parse_schema,
)


# ---------------------------------------------------------------------------
# Tests for parse_schema with minimal_schema fixture
# ---------------------------------------------------------------------------


class TestParseSchemaMinimal:
    """Tests using the minimal_schema fixture."""

    def test_types_extracted(self, minimal_schema: SchemaInfo):
        type_names = {t.name for t in minimal_schema.types}
        assert "User" in type_names
        assert "Post" in type_names

    def test_query_type_exists(self, minimal_schema: SchemaInfo):
        assert minimal_schema.query_type is not None
        assert minimal_schema.query_type.name == "Query"

    def test_mutation_type_exists(self, minimal_schema: SchemaInfo):
        assert minimal_schema.mutation_type is not None
        assert minimal_schema.mutation_type.name == "Mutation"

    def test_enums_extracted(self, minimal_schema: SchemaInfo):
        enum_names = {e.name for e in minimal_schema.enums}
        assert "Role" in enum_names
        role_enum = next(e for e in minimal_schema.enums if e.name == "Role")
        assert role_enum.values == ["ADMIN", "USER", "GUEST"]

    def test_inputs_extracted(self, minimal_schema: SchemaInfo):
        input_names = {i.name for i in minimal_schema.inputs}
        assert "CreateUserInput" in input_names
        create_input = next(
            i for i in minimal_schema.inputs if i.name == "CreateUserInput"
        )
        field_names = [f.name for f in create_input.fields]
        assert "name" in field_names
        assert "email" in field_names
        assert "role" in field_names

    def test_interfaces_extracted(self, minimal_schema: SchemaInfo):
        iface_names = {i.name for i in minimal_schema.interfaces}
        assert "Node" in iface_names
        node_iface = next(
            i for i in minimal_schema.interfaces if i.name == "Node"
        )
        assert len(node_iface.fields) == 1
        assert node_iface.fields[0].name == "id"

    def test_interface_implementing_types(self, minimal_schema: SchemaInfo):
        node_iface = next(
            i for i in minimal_schema.interfaces if i.name == "Node"
        )
        assert sorted(node_iface.implementing_types) == ["Post", "User"]

    def test_unions_extracted(self, minimal_schema: SchemaInfo):
        union_names = {u.name for u in minimal_schema.unions}
        assert "SearchResult" in union_names
        search_union = next(
            u for u in minimal_schema.unions if u.name == "SearchResult"
        )
        assert sorted(search_union.member_types) == ["Post", "User"]

    def test_no_scalars_in_minimal(self, minimal_schema: SchemaInfo):
        # minimal_schema has no custom scalars
        assert minimal_schema.scalars == []

    def test_query_fields(self, minimal_schema: SchemaInfo):
        qt = minimal_schema.query_type
        assert qt is not None
        field_names = {f.name for f in qt.fields}
        assert "user" in field_names
        assert "users" in field_names

    def test_query_user_field_info(self, minimal_schema: SchemaInfo):
        qt = minimal_schema.query_type
        user_field = next(f for f in qt.fields if f.name == "user")
        assert user_field.graphql_type == "User"
        assert user_field.python_type == "User | None"
        assert user_field.is_non_null is False
        assert user_field.is_list is False

    def test_query_users_field_info(self, minimal_schema: SchemaInfo):
        qt = minimal_schema.query_type
        users_field = next(f for f in qt.fields if f.name == "users")
        assert users_field.graphql_type == "[User!]!"
        assert users_field.is_non_null is True
        assert users_field.is_list is True

    def test_query_user_arguments(self, minimal_schema: SchemaInfo):
        qt = minimal_schema.query_type
        user_field = next(f for f in qt.fields if f.name == "user")
        assert len(user_field.arguments) == 1
        arg = user_field.arguments[0]
        assert arg.name == "id"
        assert arg.graphql_type == "ID!"
        assert arg.python_type == "str"

    def test_query_users_arguments_with_default(self, minimal_schema: SchemaInfo):
        qt = minimal_schema.query_type
        users_field = next(f for f in qt.fields if f.name == "users")
        assert len(users_field.arguments) == 1
        arg = users_field.arguments[0]
        assert arg.name == "first"
        assert arg.graphql_type == "Int"
        assert arg.default == 10

    def test_user_type_fields(self, minimal_schema: SchemaInfo):
        user_type = next(t for t in minimal_schema.types if t.name == "User")
        field_names = {f.name for f in user_type.fields}
        assert field_names == {"id", "name", "email", "role", "posts"}

    def test_user_type_interfaces(self, minimal_schema: SchemaInfo):
        user_type = next(t for t in minimal_schema.types if t.name == "User")
        assert user_type.interfaces == ["Node"]

    def test_user_name_field_is_non_null(self, minimal_schema: SchemaInfo):
        user_type = next(t for t in minimal_schema.types if t.name == "User")
        name_field = next(f for f in user_type.fields if f.name == "name")
        assert name_field.is_non_null is True
        assert name_field.graphql_type == "String!"
        assert name_field.python_type == "str"

    def test_user_email_field_is_nullable(self, minimal_schema: SchemaInfo):
        user_type = next(t for t in minimal_schema.types if t.name == "User")
        email_field = next(f for f in user_type.fields if f.name == "email")
        assert email_field.is_non_null is False
        assert email_field.graphql_type == "String"
        assert email_field.python_type == "str | None"

    def test_user_posts_field_is_list(self, minimal_schema: SchemaInfo):
        user_type = next(t for t in minimal_schema.types if t.name == "User")
        posts_field = next(f for f in user_type.fields if f.name == "posts")
        assert posts_field.is_list is True
        assert posts_field.graphql_type == "[Post!]!"

    def test_input_field_info(self, minimal_schema: SchemaInfo):
        create_input = next(
            i for i in minimal_schema.inputs if i.name == "CreateUserInput"
        )
        name_field = next(f for f in create_input.fields if f.name == "name")
        assert name_field.is_non_null is True
        assert name_field.graphql_type == "String!"
        assert name_field.python_type == "str"

        email_field = next(f for f in create_input.fields if f.name == "email")
        assert email_field.is_non_null is False

    def test_input_not_one_of(self, minimal_schema: SchemaInfo):
        create_input = next(
            i for i in minimal_schema.inputs if i.name == "CreateUserInput"
        )
        assert create_input.is_one_of is False

    def test_mutation_field(self, minimal_schema: SchemaInfo):
        mt = minimal_schema.mutation_type
        assert mt is not None
        field_names = {f.name for f in mt.fields}
        assert "createUser" in field_names
        create_field = next(f for f in mt.fields if f.name == "createUser")
        assert create_field.is_non_null is True
        assert len(create_field.arguments) == 1
        assert create_field.arguments[0].name == "input"


# ---------------------------------------------------------------------------
# Tests for parse_schema with oneof_schema fixture
# ---------------------------------------------------------------------------


class TestParseSchemaOneOf:
    """Tests using the oneof_schema fixture."""

    def test_oneof_input_detected(self, oneof_schema: SchemaInfo):
        input_names = {i.name for i in oneof_schema.inputs}
        assert "SearchFilter" in input_names
        sf = next(i for i in oneof_schema.inputs if i.name == "SearchFilter")
        assert sf.is_one_of is True

    def test_oneof_fields(self, oneof_schema: SchemaInfo):
        sf = next(i for i in oneof_schema.inputs if i.name == "SearchFilter")
        field_names = [f.name for f in sf.fields]
        assert "byName" in field_names
        assert "byId" in field_names


# ---------------------------------------------------------------------------
# Tests for parse_schema with scalar_schema fixture
# ---------------------------------------------------------------------------


class TestParseSchemaScalar:
    """Tests using the scalar_schema fixture."""

    def test_custom_scalars_extracted(self, scalar_schema: SchemaInfo):
        assert sorted(scalar_schema.scalars) == ["DateTime", "JSON"]

    def test_event_type(self, scalar_schema: SchemaInfo):
        type_names = {t.name for t in scalar_schema.types}
        assert "Event" in type_names
        event = next(t for t in scalar_schema.types if t.name == "Event")
        timestamp_field = next(
            f for f in event.fields if f.name == "timestamp"
        )
        assert timestamp_field.graphql_type == "DateTime!"
        assert timestamp_field.python_type == "str"

    def test_json_field_python_type(self, scalar_schema: SchemaInfo):
        event = next(t for t in scalar_schema.types if t.name == "Event")
        metadata_field = next(
            f for f in event.fields if f.name == "metadata"
        )
        assert metadata_field.graphql_type == "JSON"
        assert metadata_field.python_type == "Any | None"


# ---------------------------------------------------------------------------
# Tests for parse_schema with empty_schema fixture
# ---------------------------------------------------------------------------


class TestParseSchemaEmpty:
    """Tests using the empty_schema fixture."""

    def test_query_type_exists(self, empty_schema: SchemaInfo):
        assert empty_schema.query_type is not None
        assert empty_schema.query_type.name == "Query"

    def test_no_mutation(self, empty_schema: SchemaInfo):
        assert empty_schema.mutation_type is None

    def test_no_types(self, empty_schema: SchemaInfo):
        assert empty_schema.types == []

    def test_no_enums(self, empty_schema: SchemaInfo):
        assert empty_schema.enums == []

    def test_no_inputs(self, empty_schema: SchemaInfo):
        assert empty_schema.inputs == []

    def test_no_interfaces(self, empty_schema: SchemaInfo):
        assert empty_schema.interfaces == []

    def test_no_unions(self, empty_schema: SchemaInfo):
        assert empty_schema.unions == []

    def test_hello_field(self, empty_schema: SchemaInfo):
        qt = empty_schema.query_type
        assert len(qt.fields) == 1
        assert qt.fields[0].name == "hello"
        assert qt.fields[0].graphql_type == "String"
        assert qt.fields[0].python_type == "str | None"
        assert qt.fields[0].is_non_null is False
        assert qt.fields[0].is_list is False


# ---------------------------------------------------------------------------
# Tests for private helpers
# ---------------------------------------------------------------------------


class TestTypeToString:
    """Tests for _type_to_string."""

    def _get_type(self, type_str: str):
        """Build a schema and extract a type object for testing."""
        schema = build_schema(f"type Query {{ f: {type_str} }}")
        return schema.type_map["Query"].fields["f"].type

    def test_simple_named_type(self):
        gql_type = self._get_type("String")
        assert _type_to_string(gql_type) == "String"

    def test_non_null_type(self):
        gql_type = self._get_type("String!")
        assert _type_to_string(gql_type) == "String!"

    def test_list_type(self):
        gql_type = self._get_type("[String]")
        assert _type_to_string(gql_type) == "[String]"

    def test_non_null_list_of_non_null(self):
        gql_type = self._get_type("[String!]!")
        assert _type_to_string(gql_type) == "[String!]!"

    def test_nested_list(self):
        gql_type = self._get_type("[[Int]]")
        assert _type_to_string(gql_type) == "[[Int]]"


class TestGraphqlTypeToPython:
    """Tests for _graphql_type_to_python."""

    def _get_type(self, type_str: str):
        schema = build_schema(f"type Query {{ f: {type_str} }}")
        return schema.type_map["Query"].fields["f"].type

    def test_nullable_string(self):
        gql_type = self._get_type("String")
        assert _graphql_type_to_python(gql_type) == "str | None"

    def test_non_null_string(self):
        gql_type = self._get_type("String!")
        assert _graphql_type_to_python(gql_type) == "str"

    def test_nullable_int(self):
        gql_type = self._get_type("Int")
        assert _graphql_type_to_python(gql_type) == "int | None"

    def test_non_null_int(self):
        gql_type = self._get_type("Int!")
        assert _graphql_type_to_python(gql_type) == "int"

    def test_nullable_float(self):
        gql_type = self._get_type("Float")
        assert _graphql_type_to_python(gql_type) == "float | None"

    def test_non_null_boolean(self):
        gql_type = self._get_type("Boolean!")
        assert _graphql_type_to_python(gql_type) == "bool"

    def test_non_null_id(self):
        gql_type = self._get_type("ID!")
        assert _graphql_type_to_python(gql_type) == "str"

    def test_nullable_list(self):
        gql_type = self._get_type("[String]")
        assert _graphql_type_to_python(gql_type) == "list[str | None] | None"

    def test_non_null_list_of_non_null(self):
        gql_type = self._get_type("[String!]!")
        assert _graphql_type_to_python(gql_type) == "list[str]"

    def test_custom_type_nullable(self):
        schema = build_schema("type Query { f: Foo }\ntype Foo { x: Int }")
        gql_type = schema.type_map["Query"].fields["f"].type
        assert _graphql_type_to_python(gql_type) == "Foo | None"

    def test_custom_type_non_null(self):
        schema = build_schema("type Query { f: Foo! }\ntype Foo { x: Int }")
        gql_type = schema.type_map["Query"].fields["f"].type
        assert _graphql_type_to_python(gql_type) == "Foo"


class TestIsListType:
    """Tests for _is_list_type."""

    def _get_type(self, type_str: str):
        schema = build_schema(f"type Query {{ f: {type_str} }}")
        return schema.type_map["Query"].fields["f"].type

    def test_not_list(self):
        assert _is_list_type(self._get_type("String")) is False

    def test_not_list_non_null(self):
        assert _is_list_type(self._get_type("String!")) is False

    def test_list(self):
        assert _is_list_type(self._get_type("[String]")) is True

    def test_non_null_list(self):
        assert _is_list_type(self._get_type("[String]!")) is True

    def test_non_null_list_of_non_null(self):
        assert _is_list_type(self._get_type("[String!]!")) is True


class TestParseSchemaSubscription:
    """Test that Subscription types are skipped."""

    def test_subscription_type_skipped(self, tmp_path):
        schema_text = """\
type Query { hello: String }
type Subscription { onMessage: String }
"""
        p = tmp_path / "sub.graphqls"
        p.write_text(schema_text)
        schema = parse_schema(p)
        type_names = {t.name for t in schema.types}
        assert "Subscription" not in type_names
        assert schema.query_type is not None


class TestDetectOneOfInputs:
    """Tests for _detect_one_of_inputs."""

    def test_detects_oneof(self):
        text = "input SearchFilter @oneOf {\n  byName: String\n}"
        result = _detect_one_of_inputs(text)
        assert result == {"SearchFilter"}

    def test_no_oneof(self):
        text = "input CreateUserInput {\n  name: String!\n}"
        result = _detect_one_of_inputs(text)
        assert result == set()

    def test_multiple_oneof(self):
        text = (
            "input A @oneOf { x: String }\n"
            "input B @oneOf { y: String }\n"
            "input C { z: String }\n"
        )
        result = _detect_one_of_inputs(text)
        assert result == {"A", "B"}

    def test_oneof_with_extra_spaces(self):
        text = "input   Foo   @oneOf { x: String }"
        result = _detect_one_of_inputs(text)
        assert result == {"Foo"}
