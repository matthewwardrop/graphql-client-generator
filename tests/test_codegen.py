"""Tests for graphql_client_generator.codegen modules."""

from __future__ import annotations

from graphql_client_generator.codegen.client import generate_client
from graphql_client_generator.codegen.enums import generate_enums
from graphql_client_generator.codegen.inputs import generate_inputs
from graphql_client_generator.codegen.outputs import generate_outputs
from graphql_client_generator.codegen.package import generate_init, generate_pyproject
from graphql_client_generator.codegen.schema import generate_schema
from graphql_client_generator.parser import (
    EnumInfo,
    FieldArgInfo,
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
        schema = SchemaInfo(enums=[EnumInfo(name="Empty", values=[], description="")])
        code = generate_enums(schema)
        assert "class Empty(Enum):" in code
        assert "    pass" in code

    def test_enum_escape_docstring(self):
        schema = SchemaInfo(
            enums=[EnumInfo(name="Tricky", values=["A"], description='Has """triple quotes"""')]
        )
        code = generate_enums(schema)
        assert r"\"\"\"" in code


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
            inputs=[
                InputInfo(
                    name="TestInput",
                    fields=[
                        FieldInfo(
                            name="x", graphql_type="String!", python_type="str", is_non_null=True
                        )
                    ],
                    description="A test input",
                )
            ]
        )
        code = generate_inputs(schema)
        assert '"""A test input"""' in code

    def test_input_field_with_description(self):
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="TestInput",
                    fields=[
                        FieldInfo(
                            name="x",
                            graphql_type="String!",
                            python_type="str",
                            is_non_null=True,
                            description="The X field",
                        )
                    ],
                )
            ]
        )
        code = generate_inputs(schema)
        assert "# The X field" in code

    def test_input_optional_field_with_description(self):
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="TestInput",
                    fields=[
                        FieldInfo(
                            name="y",
                            graphql_type="String",
                            python_type="str | None",
                            is_non_null=False,
                            description="Optional Y",
                        )
                    ],
                )
            ]
        )
        code = generate_inputs(schema)
        assert "# Optional Y" in code

    def test_input_with_no_fields(self):
        schema = SchemaInfo(inputs=[InputInfo(name="EmptyInput", fields=[])])
        code = generate_inputs(schema)
        assert "class EmptyInput:" in code
        assert "    pass" in code

    def test_input_all_optional_post_init(self):
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="OptInput",
                    fields=[
                        FieldInfo(
                            name="x",
                            graphql_type="String",
                            python_type="str | None",
                            is_non_null=False,
                        )
                    ],
                )
            ]
        )
        code = generate_inputs(schema)
        assert "def __post_init__" not in code

    def test_input_escape_docstring(self):
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="TestInput",
                    fields=[
                        FieldInfo(
                            name="x", graphql_type="String!", python_type="str", is_non_null=True
                        )
                    ],
                    description='Has """triple"""',
                )
            ]
        )
        code = generate_inputs(schema)
        assert r"\"\"\"" in code

    def test_non_null_field_with_default_is_optional(self):
        """A non-null input field with a schema default should be optional."""

        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="Filter",
                    fields=[
                        FieldInfo(
                            name="active",
                            graphql_type="Boolean!",
                            python_type="bool",
                            is_non_null=True,
                            default=True,
                        ),
                        FieldInfo(
                            name="name",
                            graphql_type="String!",
                            python_type="str",
                            is_non_null=True,
                        ),
                    ],
                )
            ]
        )
        code = generate_inputs(schema)
        # 'name' is required (no default), 'active' has a default so it's optional
        assert "name: str" in code
        assert "active: bool = None" in code
        # required fields come before optional in the dataclass
        lines = code.splitlines()
        name_line = next(i for i, line in enumerate(lines) if "name: str" in line)
        active_line = next(i for i, line in enumerate(lines) if "active: bool" in line)
        assert name_line < active_line

    def test_non_null_field_with_default_no_post_init_validation(self):
        """A non-null field with a default should not be validated in __post_init__."""
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="Settings",
                    fields=[
                        FieldInfo(
                            name="verbose",
                            graphql_type="Boolean!",
                            python_type="bool",
                            is_non_null=True,
                            default=False,
                        ),
                    ],
                )
            ]
        )
        code = generate_inputs(schema)
        # No required fields -> no __post_init__
        assert "__post_init__" not in code

    def test_non_null_field_without_default_still_required(self):
        """A non-null field without a default is still required."""
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="Settings",
                    fields=[
                        FieldInfo(
                            name="name",
                            graphql_type="String!",
                            python_type="str",
                            is_non_null=True,
                        ),
                    ],
                )
            ]
        )
        code = generate_inputs(schema)
        assert "name: str" in code
        assert "= None" not in code.split("name: str")[1].split("\n")[0]
        assert "__post_init__" in code


# ---------------------------------------------------------------------------
# generate_outputs
# ---------------------------------------------------------------------------


class TestGenerateOutputs:
    def test_has_schema_field_import(self, minimal_schema: SchemaInfo):
        code = generate_outputs(minimal_schema)
        assert "SchemaField" in code

    def test_has_type_registry(self, minimal_schema: SchemaInfo):
        code = generate_outputs(minimal_schema)
        assert "TYPE_REGISTRY" in code
        assert '"User": User' in code
        assert '"Post": Post' in code

    def test_has_query_result(self, minimal_schema: SchemaInfo):
        code = generate_outputs(minimal_schema)
        assert "class QueryResult(_ResultRoot):" in code

    def test_has_mutation_result(self, minimal_schema: SchemaInfo):
        code = generate_outputs(minimal_schema)
        assert "class MutationResult(_ResultRoot):" in code

    def test_model_classes_generated(self, minimal_schema: SchemaInfo):
        code = generate_outputs(minimal_schema)
        assert "class User(" in code
        assert "class Post(" in code

    def test_nested_field_with_flattened_input(self):
        """Fields on output types with a single Input-typed arg get flattened."""
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="UpdateInput",
                    fields=[
                        FieldInfo("name", "String!", "str", is_non_null=True),
                    ],
                ),
            ],
            types=[
                TypeInfo(
                    name="UserOps",
                    fields=[
                        FieldInfo(
                            name="update",
                            graphql_type="User!",
                            python_type="User",
                            arguments=[
                                FieldArgInfo("input", "UpdateInput!", "UpdateInput"),
                            ],
                        ),
                    ],
                ),
            ],
        )
        code = generate_outputs(schema)
        assert 'input_arg="input"' in code
        assert "input_cls=inputs.UpdateInput" in code
        assert "from . import inputs" in code

    def test_interface_field_with_flattened_input(self):
        """Interface fields with Input-typed args also get flattened."""
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="ActionInput",
                    fields=[FieldInfo("reason", "String!", "str", is_non_null=True)],
                ),
            ],
            interfaces=[
                InterfaceInfo(
                    name="Actionable",
                    fields=[
                        FieldInfo(
                            name="perform",
                            graphql_type="Boolean!",
                            python_type="bool",
                            arguments=[
                                FieldArgInfo("input", "ActionInput!", "ActionInput"),
                            ],
                        ),
                    ],
                ),
            ],
        )
        code = generate_outputs(schema)
        assert "input_cls=inputs.ActionInput" in code
        assert "from . import inputs" in code

    def test_interface_class_generated(self, minimal_schema: SchemaInfo):
        code = generate_outputs(minimal_schema)
        assert "class Node(GraphQLModel):" in code

    def test_union_type_alias(self, minimal_schema: SchemaInfo):
        code = generate_outputs(minimal_schema)
        assert "SearchResult = User | Post" in code

    def test_empty_schema(self, empty_schema: SchemaInfo):
        code = generate_outputs(empty_schema)
        assert "TYPE_REGISTRY" in code
        assert "MutationResult" not in code

    def test_typename_set_on_model(self, minimal_schema: SchemaInfo):
        code = generate_outputs(minimal_schema)
        assert '__typename__ = "User"' in code
        assert '__typename__ = "Post"' in code

    def test_union_with_description(self):
        schema = SchemaInfo(
            unions=[UnionInfo(name="MyUnion", member_types=["A", "B"], description="A union")],
            types=[
                TypeInfo(
                    name="A",
                    fields=[FieldInfo(name="x", graphql_type="String", python_type="str | None")],
                ),
                TypeInfo(
                    name="B",
                    fields=[FieldInfo(name="y", graphql_type="Int", python_type="int | None")],
                ),
            ],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_outputs(schema)
        assert "# A union" in code

    def test_type_with_description(self):
        schema = SchemaInfo(
            types=[TypeInfo(name="Foo", fields=[], description="A foo type")],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_outputs(schema)
        assert '"""A foo type"""' in code

    def test_type_with_no_fields(self):
        schema = SchemaInfo(
            types=[TypeInfo(name="Empty", fields=[])],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_outputs(schema)
        assert "class Empty(" in code
        assert "    pass" in code

    def test_model_escape_docstring(self):
        schema = SchemaInfo(
            types=[TypeInfo(name="Tricky", fields=[], description='Has """quotes"""')],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_outputs(schema)
        assert r"\"\"\"" in code

    def test_no_query_no_mutation_no_result_classes(self):
        schema = SchemaInfo(
            types=[
                TypeInfo(
                    name="Foo",
                    fields=[FieldInfo(name="x", graphql_type="String", python_type="str | None")],
                )
            ],
        )
        code = generate_outputs(schema)
        assert "QueryResult" not in code
        assert "MutationResult" not in code

    def test_model_field_with_arguments(self):
        from graphql_client_generator.parser import FieldArgInfo

        schema = SchemaInfo(
            types=[
                TypeInfo(
                    name="Foo",
                    fields=[
                        FieldInfo(
                            name="items",
                            graphql_type="[String!]!",
                            python_type="list[str]",
                            arguments=[
                                FieldArgInfo(name="limit", graphql_type="Int!", python_type="int")
                            ],
                        )
                    ],
                )
            ],
        )
        code = generate_outputs(schema)
        assert 'arg_types={"limit": "Int!"}' in code
        assert 'doc="items(limit: Int!)"' in code


# ---------------------------------------------------------------------------
# generate_schema
# ---------------------------------------------------------------------------


class TestGenerateSchema:
    def test_has_schema_class(self, minimal_schema: SchemaInfo):
        code = generate_schema(minimal_schema, "TestSchema")
        assert "class _TestSchema:" in code
        assert "TestSchema = _TestSchema()" in code

    def test_schema_class_has_query_fields(self, minimal_schema: SchemaInfo):
        code = generate_schema(minimal_schema, "TestSchema")
        assert '"user"' in code
        assert '"users"' in code

    def test_has_mutation_class(self, minimal_schema: SchemaInfo):
        code = generate_schema(minimal_schema, "TestSchema", "TestMutation")
        assert "class _TestMutation:" in code
        assert "TestMutation = _TestMutation()" in code

    def test_mutation_field_has_flattened_input(self, minimal_schema: SchemaInfo):
        code = generate_schema(minimal_schema, "TestSchema", "TestMutation")
        assert 'input_arg="input"' in code
        assert "input_cls=inputs.CreateUserInput" in code
        # arg_types should have flattened Input fields, not the original arg
        assert '"name": "String!"' in code
        assert '"role": "Role!"' in code

    def test_no_mutation_class_when_empty(self, empty_schema: SchemaInfo):
        code = generate_schema(empty_schema, "TestSchema")
        assert "class _TestSchema:" in code
        assert "Mutation" not in code

    def test_imports_outputs_and_inputs(self, minimal_schema: SchemaInfo):
        code = generate_schema(minimal_schema, "TestSchema")
        assert "from . import inputs, outputs" in code

    def test_uses_direct_type_refs(self, minimal_schema: SchemaInfo):
        code = generate_schema(minimal_schema, "TestSchema")
        assert "outputs." in code
        assert "lambda:" not in code

    def test_mutation_getitem_builds_mutation(self, minimal_schema: SchemaInfo):
        code = generate_schema(minimal_schema, "TestSchema", "TestMutation")
        assert '"mutation"' in code

    def test_no_query_type_still_generates(self):
        schema = SchemaInfo()
        code = generate_schema(schema, "TestSchema")
        assert "class _TestSchema:" in code

    def test_mutation_no_input_arg_when_scalar_args(self):
        schema = SchemaInfo(
            inputs=[],
            mutation_type=TypeInfo(
                name="Mutation",
                fields=[
                    FieldInfo(
                        name="deleteUser",
                        graphql_type="Boolean!",
                        python_type="bool",
                        arguments=[FieldArgInfo("id", "ID!", "str")],
                    ),
                ],
            ),
        )
        code = generate_schema(schema, "TestSchema", "TestMutation")
        assert "input_arg" not in code

    def test_query_field_with_input_arg_gets_flattened(self):
        """Query fields (not just mutations) with an input arg get input_cls wiring."""
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="NodeFilter",
                    fields=[
                        FieldInfo("name", "String", "str | None", is_non_null=False),
                        FieldInfo("active", "Boolean!", "bool", is_non_null=True),
                    ],
                ),
            ],
            types=[
                TypeInfo(
                    name="Node",
                    fields=[
                        FieldInfo("id", "ID!", "str", is_non_null=True),
                    ],
                ),
            ],
            query_type=TypeInfo(
                name="Query",
                fields=[
                    FieldInfo(
                        name="findNodes",
                        graphql_type="[Node!]!",
                        python_type="list[Node]",
                        arguments=[
                            FieldArgInfo("filter", "NodeFilter!", "NodeFilter"),
                        ],
                    ),
                ],
            ),
        )
        code = generate_schema(schema, "TestSchema")
        assert 'input_arg="filter"' in code
        assert "input_cls=inputs.NodeFilter" in code

    def test_arg_with_default_strips_bang_in_schema(self):
        """Args with defaults should have '!' stripped in arg_types."""
        schema = SchemaInfo(
            query_type=TypeInfo(
                name="Query",
                fields=[
                    FieldInfo(
                        name="items",
                        graphql_type="[String!]!",
                        python_type="list[str]",
                        arguments=[
                            FieldArgInfo("limit", "Int!", "int", default=10),
                            FieldArgInfo("id", "ID!", "str"),
                        ],
                    ),
                ],
            ),
        )
        code = generate_schema(schema, "TestSchema")
        # 'limit' has a default -> no '!' in arg_types
        assert '"limit": "Int"' in code
        # 'id' has no default -> '!' preserved
        assert '"id": "ID!"' in code

    def test_flattened_input_field_with_default_strips_bang_in_schema(self):
        """Flattened input fields with defaults strip '!' in arg_types."""
        schema = SchemaInfo(
            inputs=[
                InputInfo(
                    name="Opts",
                    fields=[
                        FieldInfo(
                            "verbose",
                            "Boolean!",
                            "bool",
                            is_non_null=True,
                            default=False,
                        ),
                        FieldInfo(
                            "name",
                            "String!",
                            "str",
                            is_non_null=True,
                        ),
                    ],
                ),
            ],
            mutation_type=TypeInfo(
                name="Mutation",
                fields=[
                    FieldInfo(
                        name="run",
                        graphql_type="Boolean!",
                        python_type="bool",
                        arguments=[
                            FieldArgInfo("opts", "Opts!", "Opts"),
                        ],
                    ),
                ],
            ),
        )
        code = generate_schema(schema, "TestSchema", "TestMutation")
        # verbose has default=False -> no '!'
        assert '"verbose": "Boolean"' in code
        # name has no default -> '!' preserved
        assert '"name": "String!"' in code


# ---------------------------------------------------------------------------
# generate_outputs - arg default handling
# ---------------------------------------------------------------------------


class TestGenerateOutputsArgDefaults:
    def test_output_field_arg_with_default_strips_bang(self):
        """Output type field args with defaults strip '!' in arg_types."""
        schema = SchemaInfo(
            types=[
                TypeInfo(
                    name="Foo",
                    fields=[
                        FieldInfo(
                            name="items",
                            graphql_type="[String!]!",
                            python_type="list[str]",
                            arguments=[
                                FieldArgInfo("limit", "Int!", "int", default=25),
                                FieldArgInfo("cursor", "String!", "str"),
                            ],
                        )
                    ],
                )
            ],
        )
        code = generate_outputs(schema)
        assert '"limit": "Int"' in code
        assert '"cursor": "String!"' in code


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
        assert "MutationResult" not in code
        assert "def mutate(" not in code

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
        code = generate_init(minimal_schema, "my_package", "MyClient", "MySchema")
        assert "from .client import MyClient" in code

    def test_imports_schema_class(self, minimal_schema: SchemaInfo):
        code = generate_init(minimal_schema, "my_package", "MyClient", "MySchema")
        assert "from .schema import MySchema" in code

    def test_imports_mutation_class(self, minimal_schema: SchemaInfo):
        code = generate_init(
            minimal_schema,
            "my_package",
            "MyClient",
            "MySchema",
            mutation_class_name="MyMutation",
        )
        assert "from .schema import MySchema, MyMutation" in code
        assert "'MyMutation'" in code

    def test_no_mutation_when_empty(self, minimal_schema: SchemaInfo):
        code = generate_init(minimal_schema, "my_package", "MyClient", "MySchema")
        assert "MyMutation" not in code

    def test_imports_modules(self, minimal_schema: SchemaInfo):
        code = generate_init(minimal_schema, "my_package", "MyClient", "MySchema")
        assert "from . import outputs" in code
        assert "from . import schema" in code
        assert "from . import enums" in code
        assert "from . import inputs" in code

    def test_imports_variable(self, minimal_schema: SchemaInfo):
        code = generate_init(minimal_schema, "my_package", "MyClient", "MySchema")
        assert "from ._runtime.builder import Variable" in code

    def test_all_list(self, minimal_schema: SchemaInfo):
        code = generate_init(minimal_schema, "my_package", "MyClient", "MySchema")
        assert "__all__" in code
        assert "'MyClient'" in code
        assert "'MySchema'" in code
        assert "'outputs'" in code
        assert "'schema'" in code
        assert "'enums'" in code
        assert "'inputs'" in code

    def test_docstring_includes_package_name(self, minimal_schema: SchemaInfo):
        code = generate_init(minimal_schema, "my_package", "MyClient", "MySchema")
        assert "my_package" in code

    def test_regen_command_included(self, minimal_schema: SchemaInfo):
        code = generate_init(
            minimal_schema,
            "my_package",
            "MyClient",
            "MySchema",
            regen_command="python -m graphql_client_generator schema.graphqls -n my_package",
        )
        assert "To regenerate:" in code
        assert "python -m graphql_client_generator schema.graphqls -n my_package" in code

    def test_regen_command_omitted_when_empty(self, minimal_schema: SchemaInfo):
        code = generate_init(minimal_schema, "my_package", "MyClient", "MySchema")
        assert "To regenerate:" not in code


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


# ---------------------------------------------------------------------------
# Multiline descriptions
# ---------------------------------------------------------------------------

MULTILINE_SCHEMA = """\
type Query { ping: String }

type Status {
  id: ID!
}

enum Priority {
  HIGH
  LOW
}

input CreateInput {
  name: String!
}

union Result = Status
"""

MULTILINE_DESC = "First line.\nWhen creating: required.\nSee `docs` for details."
MULTILINE_CLASS_DESC = "Short summary.\nLonger explanation here.\nFinal note."


class TestMultilineDescriptions:
    def _make_input_schema(self, field_desc: str = "", class_desc: str = "") -> SchemaInfo:
        return SchemaInfo(
            inputs=[
                InputInfo(
                    name="MyInput",
                    description=class_desc,
                    fields=[
                        FieldInfo(
                            name="id",
                            graphql_type="Int",
                            python_type="int | None",
                            description=field_desc,
                        )
                    ],
                )
            ]
        )

    def test_multiline_field_comment_all_lines_prefixed(self):
        schema = self._make_input_schema(field_desc=MULTILINE_DESC)
        code = generate_inputs(schema)
        assert "    # First line." in code
        assert "    # When creating: required." in code
        assert "    # See `docs` for details." in code

    def test_multiline_field_comment_no_bare_continuation(self):
        schema = self._make_input_schema(field_desc=MULTILINE_DESC)
        code = generate_inputs(schema)
        # No line should start with non-comment, non-indent content mid-description
        compile(code, "<generated>", "exec")  # must not raise SyntaxError

    def test_multiline_input_class_docstring(self):
        schema = self._make_input_schema(class_desc=MULTILINE_CLASS_DESC)
        code = generate_inputs(schema)
        assert '    """' in code
        assert "    Short summary." in code
        assert "    Longer explanation here." in code
        assert "    Final note." in code
        compile(code, "<generated>", "exec")

    def test_multiline_enum_docstring(self):
        schema = SchemaInfo(
            enums=[EnumInfo(name="Color", values=["RED"], description=MULTILINE_CLASS_DESC)]
        )
        code = generate_enums(schema)
        assert "    Short summary." in code
        assert "    Longer explanation here." in code
        compile(code, "<generated>", "exec")

    def test_multiline_model_class_docstring(self):
        schema = SchemaInfo(
            types=[TypeInfo(name="Widget", description=MULTILINE_CLASS_DESC, fields=[])],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_outputs(schema)
        assert "    Short summary." in code
        assert "    Longer explanation here." in code
        compile(code, "<generated>", "exec")

    def test_multiline_union_comment(self):
        schema = SchemaInfo(
            types=[TypeInfo(name="A", fields=[]), TypeInfo(name="B", fields=[])],
            unions=[UnionInfo(name="AB", member_types=["A", "B"], description=MULTILINE_DESC)],
            query_type=TypeInfo(name="Query", fields=[]),
        )
        code = generate_outputs(schema)
        assert "# First line." in code
        assert "# When creating: required." in code
        compile(code, "<generated>", "exec")

    def test_single_line_description_unchanged(self):
        schema = self._make_input_schema(class_desc="Single line.")
        code = generate_inputs(schema)
        assert '"""Single line."""' in code

    def test_backtick_in_field_description_no_syntax_error(self):
        schema = self._make_input_schema(field_desc="Must be `null` when absent.")
        code = generate_inputs(schema)
        compile(code, "<generated>", "exec")
