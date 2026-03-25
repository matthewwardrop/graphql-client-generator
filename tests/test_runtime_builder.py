"""Comprehensive unit tests for graphql_client_generator._runtime.builder."""

from __future__ import annotations

import pytest

from graphql_client_generator._runtime.builder import (
    BuiltQuery,
    FieldSelector,
    SchemaField,
    Variable,
    VariableRef,
    _scalar_field_names,
    _to_literal,
    _VariableNamespace,
    build_query_string,
    to_graphql,
)

# ---------------------------------------------------------------------------
# Test model classes with SchemaField descriptors
# ---------------------------------------------------------------------------


class Address:
    """Leaf type with only scalar fields."""

    street = SchemaField("street", "String!")
    city = SchemaField("city", "String!")
    zip_code = SchemaField("zipCode", "String")


class Post:
    """Composite type with scalar and composite fields."""

    id = SchemaField("id", "ID!")
    title = SchemaField("title", "String!")
    body = SchemaField("body", "String")


class User:
    """Composite type referencing other composites."""

    id = SchemaField("id", "ID!")
    name = SchemaField("name", "String!")
    email = SchemaField("email", "String")
    address = SchemaField("address", "Address", target_cls=lambda: Address)
    posts = SchemaField("posts", "[Post!]!", target_cls=lambda: Post)


class UserChild(User):
    """Subclass to test MRO traversal."""

    age = SchemaField("age", "Int")


class EmptyModel:
    """A model with no SchemaField descriptors at all."""

    pass


class CompositeOnly:
    """A model with only composite (non-scalar) fields."""

    user = SchemaField("user", "User", target_cls=lambda: User)


# A non-callable sentinel to test the non-callable branch of _resolve_target.
_NON_CALLABLE_TARGET = User


# ---------------------------------------------------------------------------
# _VariableNamespace / Variable singleton
# ---------------------------------------------------------------------------


class TestVariableNamespace:
    def test_getattr_returns_variable_ref(self):
        ref = Variable.user_id
        assert isinstance(ref, VariableRef)
        assert ref.name == "user_id"

    def test_getattr_different_names(self):
        a = Variable.foo
        b = Variable.bar
        assert a.name == "foo"
        assert b.name == "bar"

    def test_getattr_underscore_prefix_raises(self):
        with pytest.raises(AttributeError, match="_secret"):
            Variable._secret

    def test_getattr_dunder_raises(self):
        with pytest.raises(AttributeError):
            Variable.__something__

    def test_repr(self):
        assert repr(Variable) == "Variable"

    def test_is_singleton_instance(self):
        assert isinstance(Variable, _VariableNamespace)


# ---------------------------------------------------------------------------
# VariableRef
# ---------------------------------------------------------------------------


class TestVariableRef:
    def test_init_and_name(self):
        ref = VariableRef("x")
        assert ref.name == "x"

    def test_repr(self):
        assert repr(VariableRef("userId")) == "$userId"

    def test_eq_same_name(self):
        assert VariableRef("a") == VariableRef("a")

    def test_eq_different_name(self):
        assert VariableRef("a") != VariableRef("b")

    def test_eq_non_variable_ref(self):
        assert VariableRef("a") != "a"
        assert VariableRef("a") != 42
        assert VariableRef("a") is not None

    def test_hash_same_name(self):
        assert hash(VariableRef("a")) == hash(VariableRef("a"))

    def test_hash_usable_in_set(self):
        s = {VariableRef("x"), VariableRef("x"), VariableRef("y")}
        assert len(s) == 2

    def test_hash_usable_as_dict_key(self):
        d = {VariableRef("k"): "val"}
        assert d[VariableRef("k")] == "val"


# ---------------------------------------------------------------------------
# FieldSelector
# ---------------------------------------------------------------------------


class TestFieldSelectorInit:
    def test_defaults(self):
        sel = FieldSelector("myField")
        assert sel._graphql_name == "myField"
        assert sel._target_cls is None
        assert sel._arg_types == {}
        assert sel._arg_doc == ""
        assert sel._args == {}
        assert sel._sub_selections == []
        assert sel._alias is None

    def test_with_all_args(self):
        def target_fn():
            return User

        sel = FieldSelector(
            "user",
            target_cls=target_fn,
            arg_types={"id": "ID!"},
            arg_doc="Fetch user by ID",
        )
        assert sel._target_cls is target_fn
        assert sel._arg_types == {"id": "ID!"}
        assert sel._arg_doc == "Fetch user by ID"


class TestFieldSelectorClone:
    def test_clone_creates_independent_copy(self):
        def target_fn():
            return User

        sel = FieldSelector("f", target_cls=target_fn, arg_types={"a": "Int"})
        sel._args = {"a": 1}
        sel._sub_selections = [FieldSelector("child")]
        sel._alias = "myAlias"

        clone = sel._clone()
        assert clone._graphql_name == "f"
        assert clone._target_cls is target_fn
        assert clone._arg_types == {"a": "Int"}
        assert clone._args == {"a": 1}
        assert clone._sub_selections == [sel._sub_selections[0]]
        assert clone._alias == "myAlias"

        # Mutating clone does not affect original
        clone._args["b"] = 2
        assert "b" not in sel._args
        clone._sub_selections.append(FieldSelector("extra"))
        assert len(sel._sub_selections) == 1


class TestFieldSelectorCall:
    def test_no_arg_types_raises(self):
        sel = FieldSelector("plain")
        with pytest.raises(TypeError, match="takes no arguments"):
            sel()

    def test_no_arg_types_raises_with_kwargs(self):
        sel = FieldSelector("plain")
        with pytest.raises(TypeError, match="takes no arguments"):
            sel(x=1)

    def test_unknown_arg_raises(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        with pytest.raises(TypeError, match="Unknown argument 'bad'"):
            sel(bad="value")

    def test_unknown_arg_shows_valid(self):
        sel = FieldSelector("user", arg_types={"id": "ID!", "name": "String"})
        with pytest.raises(TypeError, match="Valid arguments: id, name"):
            sel(bad="value")

    def test_valid_args_returns_new_selector(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        result = sel(id="123")
        assert result is not sel
        assert result._args == {"id": "123"}
        assert sel._args == {}  # original unchanged

    def test_multiple_valid_args(self):
        sel = FieldSelector("users", arg_types={"first": "Int", "after": "String"})
        result = sel(first=10, after="cursor")
        assert result._args == {"first": 10, "after": "cursor"}

    def test_variable_ref_as_arg(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        result = sel(id=Variable.userId)
        assert isinstance(result._args["id"], VariableRef)
        assert result._args["id"].name == "userId"

    def test_missing_required_arg_raises(self):
        sel = FieldSelector("user", arg_types={"id": "ID!", "name": "String"})
        with pytest.raises(TypeError, match="Missing required argument.*'user': id"):
            sel(name="Alice")

    def test_missing_multiple_required_args(self):
        sel = FieldSelector(
            "create",
            arg_types={"a": "Int!", "b": "String!", "c": "Float"},
        )
        with pytest.raises(TypeError, match="Missing required argument.*'create': a, b"):
            sel(c=1.0)

    def test_optional_arg_not_required(self):
        sel = FieldSelector("users", arg_types={"limit": "Int", "offset": "Int"})
        result = sel()  # no required args, should succeed
        assert result._args == {}

    def test_required_arg_provided_passes(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        result = sel(id="123")
        assert result._args == {"id": "123"}


class TestFieldSelectorSignature:
    def test_signature_set_when_arg_types(self):
        import inspect

        sel = FieldSelector("book", arg_types={"id": "ID!", "title": "String"})
        sig = inspect.signature(sel)
        params = list(sig.parameters.values())
        assert len(params) == 2
        assert params[0].name == "id"
        assert params[0].annotation == "ID!"
        assert params[0].kind == inspect.Parameter.KEYWORD_ONLY
        assert params[1].name == "title"
        assert params[1].annotation == "String"
        assert sig.return_annotation is FieldSelector

    def test_no_signature_when_no_args(self):
        sel = FieldSelector("name")
        assert not hasattr(sel, "__signature__")

    def test_doc_set_when_arg_types(self):
        sel = FieldSelector("book", arg_types={"id": "ID!", "limit": "Int"})
        assert sel.__doc__ == "book(id: ID!, limit: Int)"

    def test_doc_not_overridden_when_no_args(self):
        sel = FieldSelector("name")
        # Should have the class-level docstring, not a custom one
        assert "field selection" in sel.__doc__.lower()


class TestFieldSelectorGetitem:
    def test_single_selection(self):
        child = FieldSelector("name")
        parent = FieldSelector("user", target_cls=lambda: User)
        result = parent[child]
        assert result is not parent
        assert len(result._sub_selections) == 1
        assert result._sub_selections[0] is child

    def test_tuple_selections(self):
        c1 = FieldSelector("name")
        c2 = FieldSelector("email")
        parent = FieldSelector("user", target_cls=lambda: User)
        result = parent[c1, c2]
        assert len(result._sub_selections) == 2

    def test_original_unchanged(self):
        parent = FieldSelector("user", target_cls=lambda: User)
        _ = parent[FieldSelector("name")]
        assert parent._sub_selections == []

    def test_getitem_missing_required_args_raises(self):
        sel = FieldSelector("user", arg_types={"id": "ID!", "name": "String"})
        with pytest.raises(TypeError, match="Missing required argument.*'user': id"):
            sel[FieldSelector("name")]

    def test_getitem_after_call_with_required_args_passes(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        result = sel(id="123")[FieldSelector("name")]
        assert result._args == {"id": "123"}
        assert len(result._sub_selections) == 1

    def test_getitem_no_required_args_passes(self):
        sel = FieldSelector("users", arg_types={"limit": "Int"})
        result = sel[FieldSelector("name")]
        assert len(result._sub_selections) == 1

    def test_getitem_no_arg_types_passes(self):
        sel = FieldSelector("name")
        result = sel[FieldSelector("sub")]
        assert len(result._sub_selections) == 1


class TestFieldSelectorAlias:
    def test_as_sets_alias(self):
        sel = FieldSelector("user")
        aliased = sel.as_("primaryUser")
        assert aliased._alias == "primaryUser"
        assert aliased is not sel
        assert sel._alias is None

    def test_alias_preserved_through_chaining(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        result = sel.as_("u")(id="1")
        assert result._alias == "u"
        assert result._args == {"id": "1"}


class TestFieldSelectorGetattr:
    def test_underscore_prefix_raises(self):
        sel = FieldSelector("user", target_cls=lambda: User)
        with pytest.raises(AttributeError, match="_hidden"):
            sel._hidden

    def test_unknown_field_raises(self):
        sel = FieldSelector("user", target_cls=lambda: User)
        with pytest.raises(AttributeError, match="No field 'nonexistent'"):
            sel.nonexistent

    def test_no_target_cls_raises(self):
        sel = FieldSelector("scalar_field")
        with pytest.raises(AttributeError, match="No field 'anything'"):
            sel.anything

    def test_access_child_field(self):
        sel = FieldSelector("user", target_cls=lambda: User)
        child = sel.name
        assert isinstance(child, FieldSelector)
        assert child._graphql_name == "name"

    def test_access_composite_child(self):
        sel = FieldSelector("user", target_cls=lambda: User)
        addr = sel.address
        assert addr._graphql_name == "address"

    def test_access_inherited_field_via_mro(self):
        sel = FieldSelector("userChild", target_cls=lambda: UserChild)
        # Field from parent class User
        child = sel.name
        assert child._graphql_name == "name"
        # Field from UserChild itself
        age = sel.age
        assert age._graphql_name == "age"

    def test_target_cls_callable(self):
        """target_cls can be a callable (e.g. lambda) that returns a class."""
        sel = FieldSelector("user", target_cls=lambda: User)
        child = sel.name
        assert child._graphql_name == "name"


class TestFieldSelectorResolveTarget:
    def test_none_target(self):
        sel = FieldSelector("x")
        assert sel._resolve_target() is None

    def test_callable_target_returns_class(self):
        sel = FieldSelector("x", target_cls=lambda: User)
        assert sel._resolve_target() is User

    def test_callable_target_returns_address(self):
        sel = FieldSelector("x", target_cls=lambda: Address)
        assert sel._resolve_target() is Address

    def test_direct_type_reference(self):
        """When target_cls is a type, it is returned directly without calling."""
        sel = FieldSelector("x", target_cls=User)
        assert sel._resolve_target() is User


class TestFieldSelectorDir:
    def test_always_includes_as_(self):
        sel = FieldSelector("x")
        assert "as_" in dir(sel)

    def test_includes_call_when_has_args(self):
        sel = FieldSelector("x", arg_types={"id": "ID!"})
        assert "__call__" in dir(sel)

    def test_no_call_when_no_args(self):
        sel = FieldSelector("x")
        assert "__call__" not in dir(sel)

    def test_includes_child_fields(self):
        sel = FieldSelector("user", target_cls=lambda: User)
        d = dir(sel)
        assert "id" in d
        assert "name" in d
        assert "email" in d
        assert "address" in d
        assert "posts" in d

    def test_inherited_fields_in_dir(self):
        sel = FieldSelector("userChild", target_cls=lambda: UserChild)
        d = dir(sel)
        assert "age" in d
        assert "name" in d  # from parent

    def test_no_target_no_fields(self):
        sel = FieldSelector("scalar")
        d = dir(sel)
        assert d == ["as_"]

    def test_callable_target_in_dir(self):
        sel = FieldSelector("user", target_cls=lambda: User)
        assert "name" in dir(sel)

    def test_underscore_fields_excluded(self):
        """SchemaField attrs starting with _ should not appear in dir."""

        class WithUnderscore:
            _hidden = SchemaField("hidden", "String")
            visible = SchemaField("visible", "String")

        sel = FieldSelector("x", target_cls=lambda: WithUnderscore)
        d = dir(sel)
        assert "visible" in d
        assert "_hidden" not in d


class TestFieldSelectorRepr:
    def test_repr_calls_to_graphql(self):
        sel = FieldSelector("name")
        assert repr(sel) == "name"


# ---------------------------------------------------------------------------
# SchemaField descriptor
# ---------------------------------------------------------------------------


class TestSchemaField:
    def test_init_defaults(self):
        sf = SchemaField("fieldName")
        assert sf.graphql_name == "fieldName"
        assert sf.graphql_type == ""
        assert sf.attr_name is None
        assert sf._target_cls is None
        assert sf._arg_types == {}
        assert sf._doc == ""

    def test_init_all_params(self):
        sf = SchemaField(
            "user",
            "User!",
            target_cls=lambda: User,
            arg_types={"id": "ID!"},
            doc="A user",
        )
        assert sf.graphql_name == "user"
        assert sf.graphql_type == "User!"
        assert sf._arg_types == {"id": "ID!"}
        assert sf._doc == "A user"

    def test_set_name(self):
        sf = SchemaField("myField")
        sf.__set_name__(User, "my_field")
        assert sf.attr_name == "my_field"

    def test_get_returns_field_selector(self):
        """Accessing SchemaField on a class returns a FieldSelector."""
        sel = User.name
        assert isinstance(sel, FieldSelector)
        assert sel._graphql_name == "name"

    def test_get_on_instance(self):
        u = User()
        sel = u.name
        assert isinstance(sel, FieldSelector)
        assert sel._graphql_name == "name"

    def test_get_with_target_cls(self):
        sel = User.address
        # The target_cls is a lambda; the FieldSelector stores it as-is
        assert callable(sel._target_cls)

    def test_get_with_arg_types(self):
        sf = SchemaField("user", arg_types={"id": "ID!"}, doc="user doc")
        sel = sf._make_selector()
        assert sel._arg_types == {"id": "ID!"}
        assert sel._arg_doc == "user doc"

    def test_make_selector(self):
        def target_fn():
            return User

        sf = SchemaField("test", "String!", target_cls=target_fn, arg_types={"a": "Int"}, doc="d")
        sel = sf._make_selector()
        assert sel._graphql_name == "test"
        assert sel._target_cls is target_fn
        assert sel._arg_types == {"a": "Int"}
        assert sel._arg_doc == "d"

    def test_repr(self):
        sf = SchemaField("myField")
        assert repr(sf) == "SchemaField('myField')"

    def test_set_name_via_class_definition(self):
        """__set_name__ is called automatically during class creation."""
        # Access the descriptor directly from the class __dict__
        desc = User.__dict__["id"]
        assert isinstance(desc, SchemaField)
        assert desc.attr_name == "id"

    def test_set_name_on_subclass_field(self):
        desc = UserChild.__dict__["age"]
        assert isinstance(desc, SchemaField)
        assert desc.attr_name == "age"


# ---------------------------------------------------------------------------
# BuiltQuery
# ---------------------------------------------------------------------------


class TestBuiltQuery:
    def test_to_graphql_simple(self):
        sel = FieldSelector("name")
        bq = BuiltQuery([sel], {})
        result = bq.to_graphql()
        assert result == "query { name }"

    def test_to_graphql_with_aliases(self):
        sel = FieldSelector("user")
        bq = BuiltQuery([], {"myUser": sel})
        result = bq.to_graphql()
        assert "myUser: user" in result

    def test_repr_equals_to_graphql(self):
        sel = FieldSelector("name")
        bq = BuiltQuery([sel], {})
        assert repr(bq) == bq.to_graphql()

    def test_operation_type_mutation(self):
        sel = FieldSelector("createUser")
        bq = BuiltQuery([sel], {}, operation_type="mutation")
        assert bq.to_graphql().startswith("mutation")

    def test_operation_type_default(self):
        bq = BuiltQuery([], {})
        assert bq.operation_type == "query"

    def test_stores_selections_and_aliases(self):
        sels = [FieldSelector("a")]
        aliases = {"b": FieldSelector("c")}
        bq = BuiltQuery(sels, aliases, "subscription")
        assert bq.selections is sels
        assert bq.aliases is aliases
        assert bq.operation_type == "subscription"


# ---------------------------------------------------------------------------
# build_query_string
# ---------------------------------------------------------------------------


class TestBuildQueryString:
    def test_single_scalar_field(self):
        sel = FieldSelector("name")
        result = build_query_string([sel], {})
        assert result == "query { name }"

    def test_multiple_fields(self):
        s1 = FieldSelector("name")
        s2 = FieldSelector("email")
        result = build_query_string([s1, s2], {})
        assert result == "query { name email }"

    def test_aliases_only(self):
        sel = FieldSelector("user")
        result = build_query_string([], {"u1": sel})
        assert result == "query { u1: user }"

    def test_selections_and_aliases(self):
        sel1 = FieldSelector("name")
        sel2 = FieldSelector("user")
        result = build_query_string([sel1], {"u": sel2})
        assert result == "query { name u: user }"

    def test_with_variable_refs(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        sel_with_args = sel(id=Variable.userId)
        result = build_query_string([sel_with_args], {})
        assert result == "query($userId: ID!) { user(id: $userId) }"

    def test_multiple_variable_refs(self):
        sel = FieldSelector("users", arg_types={"first": "Int", "after": "String"})
        sel_with_args = sel(first=Variable.count, after=Variable.cursor)
        result = build_query_string([sel_with_args], {})
        assert "$count: Int" in result
        assert "$cursor: String" in result

    def test_mutation_operation_type(self):
        sel = FieldSelector("createUser")
        result = build_query_string([sel], {}, operation_type="mutation")
        assert result.startswith("mutation")

    def test_empty_selections_and_aliases(self):
        result = build_query_string([], {})
        assert result == "query {  }"

    def test_variable_in_alias(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        result = build_query_string([], {"u": sel(id=Variable.uid)})
        assert "$uid: ID!" in result
        assert "u: user(id: $uid)" in result


# ---------------------------------------------------------------------------
# to_graphql (single field)
# ---------------------------------------------------------------------------


class TestToGraphql:
    def test_simple_field(self):
        sel = FieldSelector("name")
        assert to_graphql(sel) == "name"

    def test_field_with_alias(self):
        sel = FieldSelector("name")
        aliased = sel.as_("myName")
        assert to_graphql(aliased) == "myName: name"

    def test_field_with_literal_args(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        result = to_graphql(sel(id="123"))
        assert result == 'user(id: "123")'

    def test_field_with_variable_ref_args(self):
        var_refs: dict[str, str] = {}
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        result = to_graphql(sel(id=Variable.userId), var_refs)
        assert result == "user(id: $userId)"
        assert var_refs == {"userId": "ID!"}

    def test_variable_ref_arg_type_default_string(self):
        """If arg type not found in _arg_types, defaults to 'String'."""
        var_refs: dict[str, str] = {}
        sel = FieldSelector("user", arg_types={})
        # Directly set args bypassing __call__ validation
        sel_clone = sel._clone()
        sel_clone._args = {"unknown": VariableRef("x")}
        to_graphql(sel_clone, var_refs)
        assert var_refs["x"] == "String"

    def test_field_with_sub_selections(self):
        child1 = FieldSelector("name")
        child2 = FieldSelector("email")
        parent = FieldSelector("user", target_cls=lambda: User)
        result = to_graphql(parent[child1, child2])
        assert result == "user { __typename name email }"

    def test_field_with_single_sub_selection(self):
        child = FieldSelector("name")
        parent = FieldSelector("user", target_cls=lambda: User)
        result = to_graphql(parent[child])
        assert result == "user { __typename name }"

    def test_auto_expand_scalar_fields(self):
        """Composite field without explicit sub-selections auto-expands."""
        sel = FieldSelector("address", target_cls=lambda: Address)
        result = to_graphql(sel)
        assert "__typename" in result
        assert "street" in result
        assert "city" in result
        assert "zipCode" in result

    def test_no_auto_expand_for_scalar(self):
        """Scalar field (no target_cls) should not auto-expand."""
        sel = FieldSelector("name")
        assert to_graphql(sel) == "name"

    def test_alias_with_args_and_subselections(self):
        child = FieldSelector("name")
        sel = FieldSelector("user", target_cls=lambda: User, arg_types={"id": "ID!"})
        result = to_graphql(sel.as_("u")(id="1")[child])
        assert result == 'u: user(id: "1") { __typename name }'

    def test_var_refs_none_creates_new_dict(self):
        """When var_refs is None, it creates a new dict internally."""
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        sel_with_args = sel(id=Variable.x)
        result = to_graphql(sel_with_args)
        assert result == "user(id: $x)"

    def test_nested_sub_selections(self):
        inner = FieldSelector("street")
        addr = FieldSelector("address", target_cls=lambda: Address)[inner]
        parent = FieldSelector("user", target_cls=lambda: User)[addr]
        result = to_graphql(parent)
        assert result == "user { __typename address { __typename street } }"

    def test_auto_expand_no_scalars(self):
        """Composite with only composite children should not auto-expand."""
        sel = FieldSelector("comp", target_cls=lambda: CompositeOnly)
        result = to_graphql(sel)
        # CompositeOnly has only 'user' which has target_cls (non-scalar)
        # So _scalar_field_names returns [] -> no auto-expand
        assert result == "comp"

    def test_auto_expand_with_args(self):
        sel = FieldSelector(
            "address",
            target_cls=lambda: Address,
            arg_types={"format": "String"},
        )
        result = to_graphql(sel(format="short"))
        assert 'address(format: "short") { __typename' in result

    def test_empty_model_no_auto_expand(self):
        sel = FieldSelector("empty", target_cls=lambda: EmptyModel)
        result = to_graphql(sel)
        assert result == "empty"

    def test_multiple_literal_args(self):
        sel = FieldSelector("users", arg_types={"first": "Int", "after": "String"})
        result = to_graphql(sel(first=10, after="abc"))
        assert "first: 10" in result
        assert 'after: "abc"' in result

    def test_sub_selections_with_alias(self):
        child = FieldSelector("name")
        parent = FieldSelector("user", target_cls=lambda: User)
        result = to_graphql(parent.as_("u")[child])
        assert result == "u: user { __typename name }"


# ---------------------------------------------------------------------------
# _scalar_field_names
# ---------------------------------------------------------------------------


class TestScalarFieldNames:
    def test_simple_class(self):
        names = _scalar_field_names(Address)
        assert set(names) == {"street", "city", "zipCode"}

    def test_mixed_scalars_and_composites(self):
        names = _scalar_field_names(User)
        # Only fields where target_cls is None (scalars)
        assert "id" in names
        assert "name" in names
        assert "email" in names
        assert "address" not in names
        assert "posts" not in names

    def test_inherited_fields(self):
        names = _scalar_field_names(UserChild)
        assert "age" in names
        assert "id" in names
        assert "name" in names

    def test_no_schema_fields(self):
        names = _scalar_field_names(EmptyModel)
        assert names == []

    def test_only_composite_fields(self):
        names = _scalar_field_names(CompositeOnly)
        assert names == []


# ---------------------------------------------------------------------------
# _to_literal
# ---------------------------------------------------------------------------


class TestToLiteral:
    def test_string(self):
        assert _to_literal("hello") == '"hello"'

    def test_string_with_quotes(self):
        assert _to_literal('say "hi"') == '"say \\"hi\\""'

    def test_string_with_backslash(self):
        assert _to_literal("back\\slash") == '"back\\\\slash"'

    def test_string_with_both(self):
        assert _to_literal('a\\"b') == '"a\\\\\\"b"'

    def test_empty_string(self):
        assert _to_literal("") == '""'

    def test_bool_true(self):
        assert _to_literal(True) == "true"

    def test_bool_false(self):
        assert _to_literal(False) == "false"

    def test_int(self):
        assert _to_literal(42) == "42"

    def test_negative_int(self):
        assert _to_literal(-1) == "-1"

    def test_zero(self):
        assert _to_literal(0) == "0"

    def test_float(self):
        assert _to_literal(3.14) == "3.14"

    def test_negative_float(self):
        assert _to_literal(-0.5) == "-0.5"

    def test_list_empty(self):
        assert _to_literal([]) == "[]"

    def test_list_of_ints(self):
        assert _to_literal([1, 2, 3]) == "[1, 2, 3]"

    def test_list_of_strings(self):
        assert _to_literal(["a", "b"]) == '["a", "b"]'

    def test_nested_list(self):
        assert _to_literal([[1], [2]]) == "[[1], [2]]"

    def test_dict_empty(self):
        assert _to_literal({}) == "{}"

    def test_dict_simple(self):
        result = _to_literal({"name": "Alice", "age": 30})
        assert result == '{name: "Alice", age: 30}'

    def test_dict_nested(self):
        result = _to_literal({"input": {"name": "A"}})
        assert result == '{input: {name: "A"}}'

    def test_none(self):
        assert _to_literal(None) == "null"

    def test_variable_ref(self):
        assert _to_literal(VariableRef("x")) == "$x"

    def test_unknown_type_fallback(self):
        """Unrecognized types fall through to str()."""

        class Custom:
            def __str__(self):
                return "CUSTOM"

        assert _to_literal(Custom()) == "CUSTOM"

    def test_bool_before_int(self):
        """bool is a subclass of int; must check bool first."""
        assert _to_literal(True) == "true"
        assert _to_literal(False) == "false"

    def test_list_with_mixed_types(self):
        result = _to_literal([1, "two", True, None])
        assert result == '[1, "two", true, null]'

    def test_dict_with_variable_ref_value(self):
        result = _to_literal({"id": VariableRef("uid")})
        assert result == "{id: $uid}"

    def test_list_single_element(self):
        assert _to_literal([42]) == "[42]"

    def test_dict_single_key(self):
        assert _to_literal({"x": 1}) == "{x: 1}"


# ---------------------------------------------------------------------------
# Integration / end-to-end tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_query_with_chaining(self):
        """Build a query using the descriptor-based API end to end."""
        user_sel = FieldSelector(
            "user",
            target_cls=lambda: User,
            arg_types={"id": "ID!"},
        )
        q = user_sel(id=Variable.userId)[
            FieldSelector("name"),
            FieldSelector("email"),
        ]
        bq = BuiltQuery([q], {})
        result = bq.to_graphql()
        assert "query($userId: ID!)" in result
        assert "user(id: $userId) { __typename name email }" in result

    def test_query_with_alias_in_aliases_dict(self):
        s1 = FieldSelector("user", arg_types={"id": "ID!"})(id="1")
        s2 = FieldSelector("user", arg_types={"id": "ID!"})(id="2")
        bq = BuiltQuery([], {"first": s1, "second": s2})
        result = bq.to_graphql()
        assert 'first: user(id: "1")' in result
        assert 'second: user(id: "2")' in result

    def test_query_auto_expand_through_descriptor(self):
        """Accessing SchemaField on a class and auto-expanding."""
        sel = User.address
        result = to_graphql(sel)
        assert result == "address { __typename street city zipCode }"

    def test_deeply_nested_query(self):
        user_sel = FieldSelector("user", target_cls=lambda: User)
        inner_post = FieldSelector("title")
        posts = FieldSelector("posts", target_cls=lambda: Post)[inner_post]
        q = user_sel[
            FieldSelector("name"),
            posts,
        ]
        result = to_graphql(q)
        assert result == "user { __typename name posts { __typename title } }"

    def test_alias_on_field_selector_in_graphql(self):
        sel = FieldSelector("name").as_("firstName")
        result = to_graphql(sel)
        assert result == "firstName: name"

    def test_sub_selection_with_variable_args(self):
        var_refs: dict[str, str] = {}
        child = FieldSelector(
            "posts",
            target_cls=lambda: Post,
            arg_types={"first": "Int"},
        )
        child_with_args = child(first=Variable.count)
        parent = FieldSelector("user", target_cls=lambda: User)[child_with_args]
        result = to_graphql(parent, var_refs)
        assert "posts(first: $count)" in result
        assert var_refs["count"] == "Int"

    def test_multiple_aliases_with_variables(self):
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        s1 = sel(id=Variable.id1)
        s2 = sel(id=Variable.id2)
        result = build_query_string([], {"a": s1, "b": s2})
        assert "$id1: ID!" in result
        assert "$id2: ID!" in result
        assert "a: user(id: $id1)" in result
        assert "b: user(id: $id2)" in result

    def test_chained_getattr_then_getitem(self):
        """Access child field via __getattr__, then set sub-selections."""
        user_sel = FieldSelector("user", target_cls=lambda: User)
        posts_sel = user_sel.posts[FieldSelector("title")]
        result = to_graphql(posts_sel)
        assert result == "posts { __typename title }"

    def test_repr_round_trip(self):
        """repr of FieldSelector should produce valid-looking GraphQL."""
        sel = FieldSelector("user", arg_types={"id": "ID!"})
        sel_with_args = sel(id="abc")
        assert repr(sel_with_args) == 'user(id: "abc")'
