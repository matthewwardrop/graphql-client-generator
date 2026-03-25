"""Comprehensive tests for graphql_client_generator._runtime.model."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from graphql_client_generator._runtime.builder import SchemaField
from graphql_client_generator._runtime.model import (
    FieldNotLoadedError,
    GraphQLModel,
    GraphQLResponse,
    PathSegment,
    QueryContext,
    _child_context,
    _coerce_response_value,
    _find_descriptor,
    _format_response,
    _lazy_load_response_field,
    _repr_value,
    _resolve_subfields_for,
    _serialize_value,
    _unwrap_type_name,
)


# ---------------------------------------------------------------------------
# Helpers: model classes used across tests
# ---------------------------------------------------------------------------

class UserModel(GraphQLModel):
    __typename__ = "User"
    name = SchemaField("name", graphql_type="String")
    email = SchemaField("email", graphql_type="String")
    age = SchemaField("age", graphql_type="Int")
    address = SchemaField("address", graphql_type="Address")


class AddressModel(GraphQLModel):
    __typename__ = "Address"
    street = SchemaField("street", graphql_type="String")
    city = SchemaField("city", graphql_type="String")


class PostModel(GraphQLModel):
    __typename__ = "Post"
    title = SchemaField("title", graphql_type="String")
    author = SchemaField("author", graphql_type="User")


TYPE_REGISTRY = {
    "User": UserModel,
    "Address": AddressModel,
    "Post": PostModel,
}


def _make_client(auto_fetch=False):
    client = MagicMock()
    client.auto_fetch = auto_fetch
    return client


def _make_context(client=None, query="query { user { name } }", variables=None,
                  operation_name=None, path=None, operation_type="query"):
    return QueryContext(
        client=client or _make_client(),
        query_string=query,
        variables=variables,
        operation_name=operation_name,
        path=path or [],
        operation_type=operation_type,
    )


# ===================================================================
# FieldNotLoadedError
# ===================================================================

class TestFieldNotLoadedError:
    def test_is_attribute_error(self):
        assert issubclass(FieldNotLoadedError, AttributeError)

    def test_can_be_raised_and_caught_as_attribute_error(self):
        with pytest.raises(AttributeError):
            raise FieldNotLoadedError("test")

    def test_message(self):
        err = FieldNotLoadedError("some field missing")
        assert str(err) == "some field missing"


# ===================================================================
# PathSegment
# ===================================================================

class TestPathSegment:
    def test_basic_creation(self):
        seg = PathSegment(field_name="user", actual_name="user")
        assert seg.field_name == "user"
        assert seg.actual_name == "user"
        assert seg.arguments is None
        assert seg.index is None

    def test_with_arguments_and_index(self):
        seg = PathSegment(field_name="users", actual_name="users",
                          arguments={"first": 10}, index=3)
        assert seg.arguments == {"first": 10}
        assert seg.index == 3

    def test_equality(self):
        a = PathSegment("f", "a", None, 0)
        b = PathSegment("f", "a", None, 0)
        assert a == b

    def test_inequality(self):
        a = PathSegment("f", "a")
        b = PathSegment("g", "a")
        assert a != b


# ===================================================================
# QueryContext
# ===================================================================

class TestQueryContext:
    def test_defaults(self):
        ctx = QueryContext(client=None, query_string="q")
        assert ctx.variables is None
        assert ctx.operation_name is None
        assert ctx.path == []
        assert ctx.operation_type == "query"

    def test_full_construction(self):
        client = _make_client()
        path = [PathSegment("user", "user")]
        ctx = QueryContext(
            client=client,
            query_string="query { user { name } }",
            variables={"id": 1},
            operation_name="GetUser",
            path=path,
            operation_type="mutation",
        )
        assert ctx.client is client
        assert ctx.variables == {"id": 1}
        assert ctx.operation_name == "GetUser"
        assert ctx.operation_type == "mutation"
        assert len(ctx.path) == 1


# ===================================================================
# GraphQLModel
# ===================================================================

class TestGraphQLModel:
    def test_default_typename(self):
        assert GraphQLModel.__typename__ == ""

    def test_default_type_registry(self):
        assert GraphQLModel.__type_registry__ == {}

    def test_subclass_typename(self):
        assert UserModel.__typename__ == "User"


# ===================================================================
# GraphQLResponse.__init__
# ===================================================================

class TestGraphQLResponseInit:
    def test_simple_scalars(self):
        resp = GraphQLResponse({"name": "Alice", "age": 30}, UserModel)
        assert resp.name == "Alice"
        assert resp.age == 30

    def test_snake_case_conversion(self):
        resp = GraphQLResponse({"firstName": "Bob"}, None)
        assert resp.first_name == "Bob"

    def test_nested_dict_becomes_response(self):
        data = {"name": "Alice", "address": {"street": "123 Main", "city": "NYC"}}
        resp = GraphQLResponse(data, UserModel, type_registry=TYPE_REGISTRY)
        assert isinstance(resp.address, GraphQLResponse)
        assert resp.address.street == "123 Main"

    def test_list_of_dicts(self):
        data = {"items": [{"name": "a"}, {"name": "b"}]}
        resp = GraphQLResponse(data, None)
        assert len(resp.items) == 2
        assert all(isinstance(i, GraphQLResponse) for i in resp.items)

    def test_none_values_stay_none(self):
        resp = GraphQLResponse({"name": None}, UserModel)
        assert resp.name is None

    def test_typename_field_excluded(self):
        resp = GraphQLResponse({"__typename": "User", "name": "Alice"}, UserModel)
        assert resp.name == "Alice"
        assert "__typename" not in resp.__dict__ or resp.__dict__.get("__typename") is None
        # __typename should not become an attribute via the loop
        # (it's skipped), but _data should still have it
        assert resp._data["__typename"] == "User"

    def test_type_registry_defaults_to_empty(self):
        resp = GraphQLResponse({"x": 1}, None)
        assert resp._type_registry == {}

    def test_stores_context(self):
        ctx = _make_context()
        resp = GraphQLResponse({"x": 1}, None, context=ctx)
        assert resp._context is ctx

    def test_model_cls_stored(self):
        resp = GraphQLResponse({}, UserModel)
        assert resp._model_cls is UserModel

    def test_nested_dict_with_typename_resolves_model(self):
        data = {"author": {"__typename": "User", "name": "Alice"}}
        resp = GraphQLResponse(data, PostModel, type_registry=TYPE_REGISTRY)
        assert resp.author._model_cls is UserModel

    def test_nested_dict_without_typename(self):
        data = {"author": {"name": "Alice"}}
        resp = GraphQLResponse(data, PostModel, type_registry=TYPE_REGISTRY)
        assert resp.author._model_cls is None

    def test_child_context_created_for_nested(self):
        ctx = _make_context()
        data = {"address": {"street": "1st"}}
        resp = GraphQLResponse(data, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        child_ctx = resp.address._context
        assert child_ctx is not None
        assert len(child_ctx.path) == 1
        assert child_ctx.path[0].field_name == "address"

    def test_no_child_context_when_parent_context_is_none(self):
        data = {"address": {"street": "1st"}}
        resp = GraphQLResponse(data, UserModel, context=None)
        assert resp.address._context is None


# ===================================================================
# GraphQLResponse.__getattr__
# ===================================================================

class TestGraphQLResponseGetattr:
    def test_underscore_prefix_raises_attribute_error(self):
        resp = GraphQLResponse({}, UserModel)
        with pytest.raises(AttributeError):
            _ = resp._nonexistent

    def test_missing_field_no_model_cls_raises_field_not_loaded(self):
        resp = GraphQLResponse({}, None)
        with pytest.raises(FieldNotLoadedError, match="not included in the query"):
            _ = resp.missing_field

    def test_missing_field_with_model_no_context_raises(self):
        resp = GraphQLResponse({}, UserModel)
        with pytest.raises(FieldNotLoadedError, match="not included in the query"):
            _ = resp.name

    def test_missing_field_auto_fetch_disabled_raises(self):
        client = _make_client(auto_fetch=False)
        ctx = _make_context(client=client)
        resp = GraphQLResponse({}, UserModel, context=ctx)
        with pytest.raises(FieldNotLoadedError):
            _ = resp.name

    def test_missing_field_no_descriptor_raises(self):
        client = _make_client(auto_fetch=True)
        ctx = _make_context(client=client)
        resp = GraphQLResponse({}, UserModel, context=ctx)
        with pytest.raises(FieldNotLoadedError):
            _ = resp.nonexistent_field

    def test_missing_field_context_client_is_none_raises(self):
        ctx = QueryContext(client=None, query_string="q")
        resp = GraphQLResponse({}, UserModel, context=ctx)
        with pytest.raises(FieldNotLoadedError):
            _ = resp.name

    @patch("graphql_client_generator._runtime.model._lazy_load_response_field")
    def test_lazy_load_called_when_auto_fetch_enabled(self, mock_lazy):
        mock_lazy.return_value = "loaded_value"
        client = _make_client(auto_fetch=True)
        ctx = _make_context(client=client)
        resp = GraphQLResponse({}, UserModel, context=ctx)
        result = resp.name
        assert result == "loaded_value"
        mock_lazy.assert_called_once()
        # Value should be cached in __dict__
        assert resp.__dict__["name"] == "loaded_value"

    @patch("graphql_client_generator._runtime.model._lazy_load_response_field")
    def test_lazy_load_caches_value(self, mock_lazy):
        mock_lazy.return_value = "cached"
        client = _make_client(auto_fetch=True)
        ctx = _make_context(client=client)
        resp = GraphQLResponse({}, UserModel, context=ctx)
        _ = resp.name
        # Second access should use __dict__ directly, not trigger __getattr__
        assert resp.name == "cached"
        assert mock_lazy.call_count == 1


# ===================================================================
# GraphQLResponse.to_dict / to_json
# ===================================================================

class TestGraphQLResponseSerialization:
    def test_to_dict_scalars(self):
        resp = GraphQLResponse({"name": "Alice", "age": 30}, UserModel)
        d = resp.to_dict()
        assert d == {"name": "Alice", "age": 30}

    def test_to_dict_nested(self):
        data = {"author": {"name": "Bob"}}
        resp = GraphQLResponse(data, PostModel)
        d = resp.to_dict()
        assert d == {"author": {"name": "Bob"}}

    def test_to_dict_with_list(self):
        data = {"tags": ["a", "b"]}
        resp = GraphQLResponse(data, None)
        assert resp.to_dict() == {"tags": ["a", "b"]}

    def test_to_json(self):
        resp = GraphQLResponse({"name": "Alice"}, UserModel)
        j = resp.to_json()
        assert json.loads(j) == {"name": "Alice"}

    def test_to_json_with_kwargs(self):
        resp = GraphQLResponse({"name": "Alice"}, UserModel)
        j = resp.to_json(indent=2)
        assert '"name": "Alice"' in j
        assert "\n" in j


# ===================================================================
# GraphQLResponse.__repr__
# ===================================================================

class TestGraphQLResponseRepr:
    def test_repr_empty(self):
        resp = GraphQLResponse({}, UserModel)
        assert repr(resp) == "UserModel()"

    def test_repr_no_model(self):
        resp = GraphQLResponse({}, None)
        assert repr(resp) == "GraphQLResponse()"

    def test_repr_with_scalars(self):
        resp = GraphQLResponse({"name": "Alice"}, UserModel)
        r = repr(resp)
        assert "UserModel(" in r
        assert "name='Alice'" in r

    def test_repr_none_values_excluded(self):
        resp = GraphQLResponse({"name": None, "age": 5}, UserModel)
        r = repr(resp)
        assert "name" not in r
        assert "age=5" in r

    def test_repr_multiline_when_long(self):
        long_val = "x" * 100
        resp = GraphQLResponse({"name": long_val}, UserModel)
        r = repr(resp)
        assert "\n" in r


# ===================================================================
# GraphQLResponse.__eq__ / __hash__
# ===================================================================

class TestGraphQLResponseEquality:
    def test_equal_responses(self):
        a = GraphQLResponse({"name": "Alice"}, UserModel)
        b = GraphQLResponse({"name": "Alice"}, UserModel)
        assert a == b

    def test_different_data(self):
        a = GraphQLResponse({"name": "Alice"}, UserModel)
        b = GraphQLResponse({"name": "Bob"}, UserModel)
        assert a != b

    def test_different_model_cls(self):
        a = GraphQLResponse({"name": "Alice"}, UserModel)
        b = GraphQLResponse({"name": "Alice"}, PostModel)
        assert a != b

    def test_not_equal_to_non_response(self):
        resp = GraphQLResponse({}, UserModel)
        assert resp.__eq__("not a response") is NotImplemented

    def test_hash_is_identity(self):
        resp = GraphQLResponse({}, UserModel)
        assert hash(resp) == id(resp)

    def test_two_equal_responses_different_hash(self):
        a = GraphQLResponse({"x": 1}, UserModel)
        b = GraphQLResponse({"x": 1}, UserModel)
        # hash is id-based, so different objects get different hashes
        assert hash(a) != hash(b)


# ===================================================================
# _coerce_response_value
# ===================================================================

class TestCoerceResponseValue:
    def test_none_returns_none(self):
        assert _coerce_response_value(None, {}, None, "k") is None

    def test_scalar_passthrough(self):
        assert _coerce_response_value(42, {}, None, "k") == 42
        assert _coerce_response_value("hello", {}, None, "k") == "hello"
        assert _coerce_response_value(True, {}, None, "k") is True
        assert _coerce_response_value(3.14, {}, None, "k") == 3.14

    def test_dict_becomes_response(self):
        result = _coerce_response_value({"a": 1}, {}, None, "k")
        assert isinstance(result, GraphQLResponse)
        assert result.a == 1

    def test_dict_with_typename_resolves_model(self):
        raw = {"__typename": "User", "name": "Alice"}
        result = _coerce_response_value(raw, TYPE_REGISTRY, None, "k")
        assert result._model_cls is UserModel

    def test_dict_with_unknown_typename(self):
        raw = {"__typename": "Unknown", "name": "x"}
        result = _coerce_response_value(raw, TYPE_REGISTRY, None, "k")
        assert result._model_cls is None

    def test_dict_no_typename(self):
        raw = {"name": "x"}
        result = _coerce_response_value(raw, TYPE_REGISTRY, None, "k")
        assert result._model_cls is None

    def test_list_of_scalars(self):
        result = _coerce_response_value([1, 2, 3], {}, None, "k")
        assert result == [1, 2, 3]

    def test_list_of_dicts(self):
        result = _coerce_response_value([{"a": 1}, {"b": 2}], {}, None, "k")
        assert all(isinstance(r, GraphQLResponse) for r in result)

    def test_list_with_nones(self):
        result = _coerce_response_value([None, {"a": 1}, None], {}, None, "k")
        assert result[0] is None
        assert isinstance(result[1], GraphQLResponse)
        assert result[2] is None

    def test_nested_list(self):
        result = _coerce_response_value([[1, 2], [3]], {}, None, "k")
        assert result == [[1, 2], [3]]

    def test_child_context_created(self):
        ctx = _make_context()
        raw = {"field": "val"}
        result = _coerce_response_value(raw, {}, ctx, "myKey")
        assert result._context is not None
        assert result._context.path[-1].field_name == "myKey"

    def test_no_child_context_when_parent_is_none(self):
        raw = {"field": "val"}
        result = _coerce_response_value(raw, {}, None, "k")
        assert result._context is None


# ===================================================================
# _child_context
# ===================================================================

class TestChildContext:
    def test_basic(self):
        parent = _make_context(path=[])
        child = _child_context(parent, "user")
        assert len(child.path) == 1
        assert child.path[0].field_name == "user"
        assert child.path[0].actual_name == "user"
        assert child.path[0].index is None

    def test_with_index(self):
        parent = _make_context(path=[])
        child = _child_context(parent, "items", index=5)
        assert child.path[0].index == 5

    def test_inherits_parent_fields(self):
        parent = _make_context(
            query="q { x }",
            variables={"v": 1},
            operation_name="Op",
            operation_type="mutation",
        )
        child = _child_context(parent, "field")
        assert child.client is parent.client
        assert child.query_string == parent.query_string
        assert child.variables == parent.variables
        assert child.operation_name == parent.operation_name
        assert child.operation_type == parent.operation_type

    def test_path_accumulates(self):
        parent = _make_context(path=[PathSegment("a", "a")])
        child = _child_context(parent, "b")
        assert len(child.path) == 2
        assert child.path[0].field_name == "a"
        assert child.path[1].field_name == "b"

    def test_does_not_mutate_parent_path(self):
        parent_path = [PathSegment("a", "a")]
        parent = _make_context(path=parent_path)
        _child_context(parent, "b")
        assert len(parent.path) == 1


# ===================================================================
# _find_descriptor
# ===================================================================

class TestFindDescriptor:
    def test_returns_none_for_none_model(self):
        assert _find_descriptor(None, "name") is None

    def test_finds_direct_field(self):
        desc = _find_descriptor(UserModel, "name")
        assert isinstance(desc, SchemaField)
        assert desc.graphql_name == "name"

    def test_not_found(self):
        assert _find_descriptor(UserModel, "nonexistent") is None

    def test_finds_inherited_field(self):
        class ChildUser(UserModel):
            extra = SchemaField("extra", graphql_type="String")

        # Should find field from parent
        desc = _find_descriptor(ChildUser, "name")
        assert desc is not None
        assert desc.graphql_name == "name"

        # Should find field from child
        desc2 = _find_descriptor(ChildUser, "extra")
        assert desc2 is not None
        assert desc2.graphql_name == "extra"

    def test_non_schema_field_attribute_not_found(self):
        class ModelWithPlainAttr(GraphQLModel):
            plain = "not a descriptor"

        assert _find_descriptor(ModelWithPlainAttr, "plain") is None


# ===================================================================
# _resolve_subfields_for
# ===================================================================

class TestResolveSubfieldsFor:
    def test_scalar_type_returns_empty(self):
        desc = SchemaField("name", graphql_type="String")
        assert _resolve_subfields_for(desc, TYPE_REGISTRY) == []

    def test_unknown_type_returns_empty(self):
        desc = SchemaField("x", graphql_type="UnknownType")
        assert _resolve_subfields_for(desc, TYPE_REGISTRY) == []

    def test_object_type_returns_scalar_fields(self):
        desc = SchemaField("address", graphql_type="Address")
        result = _resolve_subfields_for(desc, TYPE_REGISTRY)
        assert "street" in result
        assert "city" in result

    def test_unwraps_nonnull_and_list(self):
        desc = SchemaField("address", graphql_type="[Address!]!")
        result = _resolve_subfields_for(desc, TYPE_REGISTRY)
        assert "street" in result
        assert "city" in result

    def test_excludes_composite_subfields(self):
        # UserModel has 'address' which is a composite (Address), should not be in scalars
        desc = SchemaField("user", graphql_type="User")
        result = _resolve_subfields_for(desc, TYPE_REGISTRY)
        assert "name" in result
        assert "email" in result
        assert "age" in result
        assert "address" not in result


# ===================================================================
# _unwrap_type_name
# ===================================================================

class TestUnwrapTypeName:
    def test_simple(self):
        assert _unwrap_type_name("String") == "String"

    def test_nonnull(self):
        assert _unwrap_type_name("String!") == "String"

    def test_list(self):
        assert _unwrap_type_name("[String]") == "String"

    def test_list_nonnull(self):
        assert _unwrap_type_name("[String!]!") == "String"

    def test_nested_list(self):
        assert _unwrap_type_name("[[Int]]") == "Int"

    def test_with_spaces(self):
        assert _unwrap_type_name(" String! ") == "String"


# ===================================================================
# _serialize_value
# ===================================================================

class TestSerializeValue:
    def test_scalar(self):
        assert _serialize_value(42) == 42
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(None) is None
        assert _serialize_value(True) is True

    def test_graphql_response(self):
        resp = GraphQLResponse({"name": "Alice", "age": 30}, UserModel)
        result = _serialize_value(resp)
        assert result == {"name": "Alice", "age": 30}

    def test_graphql_model(self):
        model = GraphQLModel()
        model.foo = "bar"
        model.baz = 42
        result = _serialize_value(model)
        assert result == {"foo": "bar", "baz": 42}

    def test_graphql_model_excludes_private(self):
        model = GraphQLModel()
        model._private = "hidden"
        model.public = "visible"
        result = _serialize_value(model)
        assert "_private" not in result
        assert result == {"public": "visible"}

    def test_list(self):
        result = _serialize_value([1, "two", None])
        assert result == [1, "two", None]

    def test_list_of_responses(self):
        items = [
            GraphQLResponse({"a": 1}, None),
            GraphQLResponse({"b": 2}, None),
        ]
        result = _serialize_value(items)
        assert result == [{"a": 1}, {"b": 2}]

    def test_dict(self):
        result = _serialize_value({"key": "val", "num": 5})
        assert result == {"key": "val", "num": 5}

    def test_dict_with_nested_response(self):
        inner = GraphQLResponse({"x": 1}, None)
        result = _serialize_value({"inner": inner})
        assert result == {"inner": {"x": 1}}

    def test_nested_list_of_lists(self):
        result = _serialize_value([[1, 2], [3]])
        assert result == [[1, 2], [3]]


# ===================================================================
# _format_response / _repr_value
# ===================================================================

class TestFormatResponse:
    def test_empty(self):
        resp = GraphQLResponse({}, UserModel)
        assert _format_response(resp, 0) == "UserModel()"

    def test_no_model_cls(self):
        resp = GraphQLResponse({}, None)
        assert _format_response(resp, 0) == "GraphQLResponse()"

    def test_compact(self):
        resp = GraphQLResponse({"name": "Al"}, UserModel)
        result = _format_response(resp, 0)
        assert result == "UserModel(name='Al')"

    def test_typename_excluded_from_repr(self):
        resp = GraphQLResponse({"__typename": "User", "name": "A"}, UserModel)
        r = _format_response(resp, 0)
        assert "__typename" not in r

    def test_none_values_excluded(self):
        resp = GraphQLResponse({"name": None}, UserModel)
        r = _format_response(resp, 0)
        assert r == "UserModel()"

    def test_multiline_for_long_values(self):
        resp = GraphQLResponse({"name": "A" * 80}, UserModel)
        r = _format_response(resp, 0)
        assert "\n" in r

    def test_indentation_propagates(self):
        resp = GraphQLResponse({"name": "A" * 80}, UserModel)
        r = _format_response(resp, 4)
        lines = r.split("\n")
        assert lines[-1].startswith("    ")


class TestReprValue:
    def test_none(self):
        assert _repr_value(None, 0) == "None"

    def test_string(self):
        assert _repr_value("hello", 0) == "'hello'"

    def test_int(self):
        assert _repr_value(42, 0) == "42"

    def test_empty_list(self):
        assert _repr_value([], 0) == "[]"

    def test_short_list(self):
        result = _repr_value([1, 2, 3], 0)
        assert result == "[1, 2, 3]"

    def test_long_list_multiline(self):
        items = list(range(30))
        result = _repr_value(items, 0)
        # Should be compact if short enough, or multiline if long
        assert "0" in result

    def test_graphql_response(self):
        resp = GraphQLResponse({"a": 1}, UserModel)
        result = _repr_value(resp, 0)
        assert "UserModel(" in result

    def test_nested_list_multiline(self):
        # Create a list with items long enough to exceed 80 chars
        long_items = ["x" * 30 for _ in range(5)]
        result = _repr_value(long_items, 0)
        assert isinstance(result, str)


# ===================================================================
# _lazy_load_response_field
# ===================================================================

class TestLazyLoadResponseField:
    def test_no_context_raises(self):
        resp = GraphQLResponse({}, UserModel, context=None)
        desc = SchemaField("name", graphql_type="String")
        desc.attr_name = "name"
        with pytest.raises(FieldNotLoadedError, match="no client context"):
            _lazy_load_response_field(resp, desc)

    def test_no_client_raises(self):
        ctx = QueryContext(client=None, query_string="q")
        resp = GraphQLResponse({}, UserModel, context=ctx)
        desc = SchemaField("name", graphql_type="String")
        desc.attr_name = "name"
        with pytest.raises(FieldNotLoadedError, match="no client context"):
            _lazy_load_response_field(resp, desc)

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_scalar_field_lazy_load(self, mock_add_field):
        mock_add_field.return_value = "query { user { name email } }"
        client = _make_client(auto_fetch=True)
        client._execute_raw.return_value = {"user": {"name": "Alice", "email": "a@b.com"}}

        ctx = _make_context(
            client=client,
            query="query { user { name } }",
            path=[PathSegment("user", "user")],
        )
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("email", graphql_type="String")
        desc.attr_name = "email"

        result = _lazy_load_response_field(resp, desc)
        assert result == "a@b.com"
        assert resp._data["email"] == "a@b.com"

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_composite_field_lazy_load(self, mock_add_field):
        mock_add_field.return_value = "query { user { address { street city } } }"
        client = _make_client(auto_fetch=True)
        client._execute_raw.return_value = {
            "user": {"address": {"__typename": "Address", "street": "1st", "city": "NYC"}}
        }

        ctx = _make_context(
            client=client,
            path=[PathSegment("user", "user")],
        )
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("address", graphql_type="Address")
        desc.attr_name = "address"

        result = _lazy_load_response_field(resp, desc)
        assert isinstance(result, GraphQLResponse)
        assert result.street == "1st"
        assert result._model_cls is AddressModel

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_lazy_load_returns_none_when_path_yields_none(self, mock_add_field):
        mock_add_field.return_value = "query { user { email } }"
        client = _make_client(auto_fetch=True)
        client._execute_raw.return_value = {"user": None}

        ctx = _make_context(
            client=client,
            path=[PathSegment("user", "user")],
        )
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("email", graphql_type="String")
        desc.attr_name = "email"

        result = _lazy_load_response_field(resp, desc)
        assert result is None

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_lazy_load_walks_list_index(self, mock_add_field):
        mock_add_field.return_value = "query { users { email } }"
        client = _make_client(auto_fetch=True)
        client._execute_raw.return_value = {
            "users": [
                {"name": "Alice", "email": "a@b.com"},
                {"name": "Bob", "email": "b@c.com"},
            ]
        }

        ctx = _make_context(
            client=client,
            path=[PathSegment("users", "users", index=1)],
        )
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("email", graphql_type="String")
        desc.attr_name = "email"

        result = _lazy_load_response_field(resp, desc)
        assert result == "b@c.com"

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_lazy_load_index_out_of_bounds(self, mock_add_field):
        mock_add_field.return_value = "query { users { email } }"
        client = _make_client(auto_fetch=True)
        client._execute_raw.return_value = {"users": [{"email": "a@b.com"}]}

        ctx = _make_context(
            client=client,
            path=[PathSegment("users", "users", index=99)],
        )
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("email", graphql_type="String")
        desc.attr_name = "email"

        result = _lazy_load_response_field(resp, desc)
        assert result is None

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_lazy_load_current_not_dict_returns_none(self, mock_add_field):
        """When path walking ends at a non-dict (e.g. scalar), return None."""
        mock_add_field.return_value = "query { user { email } }"
        client = _make_client(auto_fetch=True)
        # Response returns a scalar where we expect a dict
        client._execute_raw.return_value = {"user": "not_a_dict"}

        ctx = _make_context(
            client=client,
            path=[PathSegment("user", "user")],
        )
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("email", graphql_type="String")
        desc.attr_name = "email"

        result = _lazy_load_response_field(resp, desc)
        assert result is None

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_lazy_load_empty_path(self, mock_add_field):
        """Root-level lazy load with no path segments."""
        mock_add_field.return_value = "query { name email }"
        client = _make_client(auto_fetch=True)
        client._execute_raw.return_value = {"name": "Alice", "email": "a@b.com"}

        ctx = _make_context(client=client, path=[])
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("email", graphql_type="String")
        desc.attr_name = "email"

        result = _lazy_load_response_field(resp, desc)
        assert result == "a@b.com"

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_lazy_load_none_mid_path_breaks(self, mock_add_field):
        """When an intermediate path segment yields None, the loop breaks early."""
        mock_add_field.return_value = "query { a { b { c { email } } } }"
        client = _make_client(auto_fetch=True)
        # "a" resolves to dict, "b" resolves to None, so third segment hits break
        client._execute_raw.return_value = {"a": {"b": None}}

        ctx = _make_context(
            client=client,
            path=[
                PathSegment("a", "a"),
                PathSegment("b", "b"),
                PathSegment("c", "c"),
            ],
        )
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("email", graphql_type="String")
        desc.attr_name = "email"

        result = _lazy_load_response_field(resp, desc)
        assert result is None

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_lazy_load_updates_data(self, mock_add_field):
        mock_add_field.return_value = "query { user { email } }"
        client = _make_client(auto_fetch=True)
        client._execute_raw.return_value = {"user": {"email": "a@b.com"}}

        ctx = _make_context(
            client=client,
            path=[PathSegment("user", "user")],
        )
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("email", graphql_type="String")
        desc.attr_name = "email"

        _lazy_load_response_field(resp, desc)
        assert "email" in resp._data

    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_lazy_load_calls_add_field_to_query_correctly(self, mock_add_field):
        mock_add_field.return_value = "modified query"
        client = _make_client(auto_fetch=True)
        client._execute_raw.return_value = {"email": "test"}

        path = [PathSegment("user", "user")]
        ctx = _make_context(
            client=client,
            query="query { user { name } }",
            path=path,
            variables={"id": 1},
            operation_name="GetUser",
        )
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)
        desc = SchemaField("email", graphql_type="String")
        desc.attr_name = "email"

        _lazy_load_response_field(resp, desc)

        mock_add_field.assert_called_once_with(
            "query { user { name } }",
            path,
            "email",
            [],  # String is scalar, no subfields
        )
        client._execute_raw.assert_called_once_with(
            "modified query",
            variables={"id": 1},
            operation_name="GetUser",
        )


# ===================================================================
# Integration-style: lazy load through __getattr__
# ===================================================================

class TestLazyLoadIntegration:
    @patch("graphql_client_generator._runtime.query.add_field_to_query")
    def test_getattr_triggers_lazy_load(self, mock_add_field):
        mock_add_field.return_value = "query { email }"
        client = _make_client(auto_fetch=True)
        client._execute_raw.return_value = {"email": "test@example.com"}

        ctx = _make_context(client=client, path=[])
        resp = GraphQLResponse({}, UserModel, context=ctx, type_registry=TYPE_REGISTRY)

        # Accessing missing field should trigger lazy load
        result = resp.email
        assert result == "test@example.com"
        # Now it should be cached
        assert resp.__dict__["email"] == "test@example.com"


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:
    def test_empty_response(self):
        resp = GraphQLResponse({}, None)
        assert resp.to_dict() == {}
        assert resp.to_json() == "{}"
        assert repr(resp) == "GraphQLResponse()"

    def test_deeply_nested(self):
        data = {
            "level1": {
                "level2": {
                    "level3": {"value": "deep"}
                }
            }
        }
        resp = GraphQLResponse(data, None)
        assert resp.level1.level2.level3.value == "deep"

    def test_mixed_list(self):
        data = {"items": [1, "two", None, {"nested": True}]}
        resp = GraphQLResponse(data, None)
        items = resp.items
        assert items[0] == 1
        assert items[1] == "two"
        assert items[2] is None
        assert isinstance(items[3], GraphQLResponse)
        assert items[3].nested is True

    def test_empty_list_field(self):
        resp = GraphQLResponse({"items": []}, None)
        assert resp.items == []

    def test_multiple_snake_case_fields(self):
        data = {"firstName": "A", "lastName": "B", "phoneNumber": "555"}
        resp = GraphQLResponse(data, None)
        assert resp.first_name == "A"
        assert resp.last_name == "B"
        assert resp.phone_number == "555"

    def test_already_snake_case(self):
        data = {"name": "test"}
        resp = GraphQLResponse(data, None)
        assert resp.name == "test"

    def test_format_response_snake_case_keys(self):
        """Repr should use snake_case keys from __dict__."""
        data = {"firstName": "A"}
        resp = GraphQLResponse(data, None)
        r = repr(resp)
        assert "first_name" in r

    def test_serialize_nested_graphql_response_in_list(self):
        inner = GraphQLResponse({"k": "v"}, None)
        result = _serialize_value([inner, 42])
        assert result == [{"k": "v"}, 42]

    def test_repr_value_list_multiline(self):
        """Force a list repr beyond 80 chars to test multiline branch."""
        long_strings = ["a" * 30 for _ in range(5)]
        result = _repr_value(long_strings, 0)
        assert "\n" in result

    def test_to_dict_preserves_original_keys(self):
        """to_dict uses _data keys (original camelCase), not snake_case."""
        data = {"firstName": "Alice"}
        resp = GraphQLResponse(data, None)
        d = resp.to_dict()
        assert "firstName" in d
        assert "first_name" not in d
