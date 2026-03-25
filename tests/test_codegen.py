"""Tests for graphql_client_generator.codegen modules."""

from __future__ import annotations

import pytest

from graphql_client_generator.codegen.client import generate_client
from graphql_client_generator.codegen.enums import generate_enums
from graphql_client_generator.codegen.inputs import generate_inputs
from graphql_client_generator.codegen.models import generate_models
from graphql_client_generator.codegen.package import generate_init, generate_pyproject
from graphql_client_generator.parser import (
    EnumInfo,
    FieldInfo,
    InputInfo,
    InterfaceInfo,
    SchemaInfo,
    TypeInfo,
    UnionInfo,
)


# ---------------------------------------------------------------------------
# generate_enums
# ---------------------------------------------------------------------------


class TestGenerateEnums:
    def test_generates_role_enum(self, minimal_schema: SchemaInfo):
        code = generate_enums(minimal_schema)
        assert "class Role(Enum):" in code
        assert 'ADMIN = "ADMIN"' in code
        assert 'USER = "USER"' in code
        assert 'GUEST = "GUEST"' in code

    def test_imports(self, minimal_schema: SchemaInfo):
        code = generate_enums(minimal_schema)
        assert "from enum import Enum" in code

    def test_empty_schema_no_enums(self, empty_schema: SchemaInfo):
        code = generate_enums(empty_schema)
        assert "class" not in code
        assert "from enum import Enum" in code

    def test_docstring_header(self, minimal_schema: SchemaInfo):
        code = generate_enums(minimal_schema)
        assert '"""GraphQL enum types."""' in code

    def test_enum_with_description(self):
        schema = SchemaInfo(
            enums=[EnumInfo(name="Color", values=["RED", "BLUE"], description="A color enum")]
        )
        code = generate_enums(schema)
        assert "class Color(Enum):" in code
        assert '"""A color enum"""' in code

    def test_enum_with_empty_values(self):
        schema = SchemaInfo(
            enums=[EnumInfo(name="Empty", values=[], description="")]
        )
        code = generate_enums(schema)
        assert "class Empty(Enum):" in code
        assert "    pass" in code

    def test_enum_escape_docstring(self):
        schema = SchemaInfo(
            enums=[EnumInfo(name="Tricky", values=["A"], description='Has """triple quotes"""')]
        )
        code = generate_enums(schema)
        assert r'\"\"\"' in code


# ---------------------------------------------------------------------------
# generate_inputs
# ---------------------------------------------------------------------------


class TestGenerateInputs:
    def test_generates_create_user_input(self, minimal_schema: SchemaInfo):
        code = generate_inputs(minimal_schema)
        assert "class CreateUserInput:" in code
        assert "@dataclass" in code

    def test_required_fields_before_optional(self, minimal_schema: SchemaInfo):
        code = generate_inputs(minimal_schema)
        # name and role are required (non-null), email is optional
        assert "name: str" in code
        assert "role: str" in code or "role: Role" in code
        assert "email:" in code

    def test_has_to_dict_method(self, minimal_schema: SchemaInfo):
        code = generate_inputs(minimal_schema)
        assert "def to_dict(self)" in code
        assert "serialize_input" in code

    def test_has_post_init(self, minimal_schema: SchemaInfo):
        code = generate_inputs(minimal_schema)
        assert "def __post_init__" in code

    def test_imports(self, minimal_schema: SchemaInfo):
        code = generate_inputs(minimal_schema)
        assert "from dataclasses import dataclass" in code
        assert "from ._runtime.serialization import serialize_input" in code

    def test_oneof_input(self, oneof_schema: SchemaInfo):
        code = generate_inputs(oneof_schema)
        assert "class SearchFilter:" in code
        assert "@oneOf" in code
        assert "Exactly one field must be set" in code

    def test_oneof_validation(self, oneof_schema: SchemaInfo):
        code = generate_inputs(oneof_schema)
        assert "len(_set) != 1" in code

    def test_empty_schema_no_inputs(self, empty_schema: SchemaInfo):
        code = generate_inputs(empty_schema)
        # No input dataclass should be generated
        assert "@dataclass" not in code

    def test_input_with_description(self):
        schema = SchemaInfo(
            inputs=[InputInfo(
                name="TestInput",
                fields=[FieldInfo(name="x", graphql_type="String!", python_type="str", is_non_null=True)],
                description="A test input",
            )]
        )
        code = generate_inputs(schema)
        assert '"""A test input"""' in code

    def test_input_field_with_description(self):
        schema = SchemaInfo(
            inputs=[InputInfo(
                name="TestInput",
                fields=[FieldInfo(
                    name="x", graphql_type="String!", python_type="str",
                    is_non_null=True, description="The X field",
                )],
            )]
        )
        code = generate_inputs(schema)
        assert "# The X field" in code

    def test_input_optional_field_with_description(self):
        schema = SchemaInfo(
            inputs=[InputInfo(
                name="TestInput",
                fields=[FieldInfo(
                    name="y", graphql_type="String", python_type="str | None",
                    is_non_null=False, description="Optional Y",
                )],
            )]
        )
        code = generate_inputs(schema)
        assert "# Optional Y" in code

    def test_input_with_no_fields(self):
        schema = SchemaInfo(
            inputs=[InputInfo(name="EmptyInput", fields=[])]
        )
        code = generate_inputs(schema)
        assert "class EmptyInput:" in code
        assert "    pass" in code

    def test_input_all_optional_post_init(self):
        schema = SchemaInfo(
            inputs=[InputInfo(
                name="OptInput",
                fields=[FieldInfo(
                    name="x", graphql_type="String", python_type="str | None",
                    is_non_null=False,
                )],
            )]
        )
        code = generate_inputs(schema)
        # post_init with no required fields should have "pass"
        assert "def __post_init__" in code

    def test_input_escape_docstring(self):
        schema = SchemaInfo(
            inputs=[InputInfo(
                name="TestInput",
                fields=[FieldInfo(name="x", graphql_type="String!", python_type="str", is_non_null=True)],
                description='Has """triple"""',
            )]
        )
        code = generate_inputs(schema)
        assert r'\"\"\"' in code


# ---------------------------------------------------------------------------
# generate_models
# ---------------------------------------------------------------------------


class TestGenerateModels:
    def test_has_schema_field_import(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert "SchemaField" in code

    def test_has_type_registry(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert "TYPE_REGISTRY" in code
        assert '"User": User' in code
        assert '"Post": Post' in code

    def test_has_query_result(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert "class QueryResult(_ResultRoot):" in code

    def test_has_mutation_result(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert "class MutationResult(_ResultRoot):" in code

    def test_has_schema_class(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert "class _TestSchema:" in code
        assert "TestSchema = _TestSchema()" in code

    def test_model_classes_generated(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert "class User(" in code
        assert "class Post(" in code

    def test_interface_class_generated(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert "class Node(GraphQLModel):" in code

    def test_union_type_alias(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert "SearchResult = User | Post" in code

    def test_schema_class_has_query_fields(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        # The schema class should have user and users fields
        assert '"user"' in code
        assert '"users"' in code

    def test_schema_class_has_mutate(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert "class mutate:" in code

    def test_empty_schema(self, empty_schema: SchemaInfo):
        code = generate_models(empty_schema, "TestSchema")
        assert "TYPE_REGISTRY" in code
        # no mutation result for empty schema
        assert "MutationResult" not in code

    def test_typename_set_on_model(self, minimal_schema: SchemaInfo):
        code = generate_models(minimal_schema, "TestSchema")
        assert '__typename__ = "User"' in code
        assert '__typename__ = "Post"' in code

    def test_union_with_description(self):
        schema = SchemaInfo(
            unions=[UnionInfo(name="MyUnion", member_types=["A", "B"], description="A union")],
            types=[
                TypeInfo(name="A", fields=[FieldInfo(name="x", graphql_type="String", python_type="str | None")]),
                TypeInfo(name="B", fields=[FieldInfo(name="y", graphql_type="Int", python_type="int | None")]),
            ],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_models(schema, "TestSchema")
        assert "# A union" in code

    def test_type_with_description(self):
        schema = SchemaInfo(
            types=[TypeInfo(name="Foo", fields=[], description="A foo type")],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_models(schema, "TestSchema")
        assert '"""A foo type"""' in code

    def test_type_with_no_fields(self):
        schema = SchemaInfo(
            types=[TypeInfo(name="Empty", fields=[])],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_models(schema, "TestSchema")
        assert "class Empty(" in code
        assert "    pass" in code

    def test_model_escape_docstring(self):
        schema = SchemaInfo(
            types=[TypeInfo(name="Tricky", fields=[], description='Has """quotes"""')],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_models(schema, "TestSchema")
        assert r'\"\"\"' in code

    def test_no_query_no_mutation_no_result_classes(self):
        schema = SchemaInfo(
            types=[TypeInfo(name="Foo", fields=[FieldInfo(name="x", graphql_type="String", python_type="str | None")])],
        )
        code = generate_models(schema, "TestSchema")
        assert "QueryResult" not in code
        assert "MutationResult" not in code


# ---------------------------------------------------------------------------
# generate_client
# ---------------------------------------------------------------------------


class TestGenerateClient:
    def test_generates_client_class(self, minimal_schema: SchemaInfo):
        code = generate_client(minimal_schema, "TestClient")
        assert "class TestClient(GraphQLClientBase):" in code

    def test_has_query_method(self, minimal_schema: SchemaInfo):
        code = generate_client(minimal_schema, "TestClient")
        assert "def query(" in code
        assert "-> QueryResult:" in code

    def test_has_mutate_method(self, minimal_schema: SchemaInfo):
        code = generate_client(minimal_schema, "TestClient")
        assert "def mutate(" in code
        assert "-> MutationResult:" in code

    def test_imports_type_registry(self, minimal_schema: SchemaInfo):
        code = generate_client(minimal_schema, "TestClient")
        assert "TYPE_REGISTRY" in code

    def test_sets_type_registry(self, minimal_schema: SchemaInfo):
        code = generate_client(minimal_schema, "TestClient")
        assert "self._type_registry = TYPE_REGISTRY" in code

    def test_without_mutation(self, empty_schema: SchemaInfo):
        code = generate_client(empty_schema, "TestClient")
        # Should not import MutationResult
        assert "MutationResult" not in code
        # mutate method should still exist but return _ResultRoot
        assert "def mutate(" in code

    def test_without_query(self):
        # Schema with no query type
        schema = SchemaInfo()
        code = generate_client(schema, "TestClient")
        assert "QueryResult" not in code

    def test_has_resolve_query_function(self, minimal_schema: SchemaInfo):
        code = generate_client(minimal_schema, "TestClient")
        assert "def _resolve_query(" in code

    def test_init_method(self, minimal_schema: SchemaInfo):
        code = generate_client(minimal_schema, "TestClient")
        assert "def __init__(" in code
        assert "endpoint: str" in code
        assert "session:" in code
        assert "auto_fetch:" in code


# ---------------------------------------------------------------------------
# generate_init
# ---------------------------------------------------------------------------


class TestGenerateInit:
    def test_imports_client(self, minimal_schema: SchemaInfo):
        code = generate_init(
            minimal_schema, "my_package", "MyClient", "MySchema"
        )
        assert "from .client import MyClient" in code

    def test_imports_models(self, minimal_schema: SchemaInfo):
        code = generate_init(
            minimal_schema, "my_package", "MyClient", "MySchema"
        )
        assert "from .models import *" in code

    def test_imports_enums(self, minimal_schema: SchemaInfo):
        code = generate_init(
            minimal_schema, "my_package", "MyClient", "MySchema"
        )
        assert "from .enums import *" in code

    def test_imports_inputs(self, minimal_schema: SchemaInfo):
        code = generate_init(
            minimal_schema, "my_package", "MyClient", "MySchema"
        )
        assert "from .inputs import *" in code

    def test_imports_variable(self, minimal_schema: SchemaInfo):
        code = generate_init(
            minimal_schema, "my_package", "MyClient", "MySchema"
        )
        assert "from ._runtime.builder import Variable" in code

    def test_all_list(self, minimal_schema: SchemaInfo):
        code = generate_init(
            minimal_schema, "my_package", "MyClient", "MySchema"
        )
        assert "__all__" in code
        assert "'MyClient'" in code
        assert "'MySchema'" in code

    def test_docstring_includes_package_name(self, minimal_schema: SchemaInfo):
        code = generate_init(
            minimal_schema, "my_package", "MyClient", "MySchema"
        )
        assert "my_package" in code


# ---------------------------------------------------------------------------
# generate_pyproject
# ---------------------------------------------------------------------------


class TestGeneratePyproject:
    def test_contains_package_name(self):
        code = generate_pyproject("my_package")
        assert 'name = "my_package"' in code

    def test_contains_version(self):
        code = generate_pyproject("my_package")
        assert 'version = "0.1.0"' in code

    def test_contains_dependencies(self):
        code = generate_pyproject("my_package")
        assert '"requests"' in code
        assert '"graphql-core>=3.2"' in code

    def test_build_system(self):
        code = generate_pyproject("my_package")
        assert "[build-system]" in code
        assert "setuptools" in code

    def test_requires_python(self):
        code = generate_pyproject("my_package")
        assert 'requires-python = ">=3.10"' in code

    def test_description_includes_name(self):
        code = generate_pyproject("my_cool_client")
        assert "my_cool_client" in code
