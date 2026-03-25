"""Parse a ``.graphqls`` schema file into a structured ``SchemaInfo`` object
that the code generator consumes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graphql import build_schema
from graphql.type import (
    GraphQLEnumType,
    GraphQLField,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLList,
    GraphQLNamedType,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLUnionType,
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FieldArgInfo:
    """One argument on a field."""
    name: str
    graphql_type: str
    python_type: str
    default: Any = None
    description: str = ""


@dataclass
class FieldInfo:
    """A single field on a type or input."""
    name: str                  # camelCase GraphQL name
    graphql_type: str          # e.g. "String!", "[Int!]!"
    python_type: str           # e.g. "str", "list[int]"
    is_non_null: bool = False
    is_list: bool = False
    description: str = ""
    arguments: list[FieldArgInfo] = field(default_factory=list)


@dataclass
class TypeInfo:
    """A GraphQL object type (including Query, Mutation)."""
    name: str
    fields: list[FieldInfo] = field(default_factory=list)
    description: str = ""
    interfaces: list[str] = field(default_factory=list)  # interface names


@dataclass
class EnumInfo:
    """A GraphQL enum type."""
    name: str
    values: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class InputInfo:
    """A GraphQL input type."""
    name: str
    fields: list[FieldInfo] = field(default_factory=list)
    description: str = ""
    is_one_of: bool = False  # @oneOf directive


@dataclass
class InterfaceInfo:
    """A GraphQL interface type."""
    name: str
    fields: list[FieldInfo] = field(default_factory=list)
    implementing_types: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class UnionInfo:
    """A GraphQL union type."""
    name: str
    member_types: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class SchemaInfo:
    """Everything extracted from a ``.graphqls`` file."""
    types: list[TypeInfo] = field(default_factory=list)
    enums: list[EnumInfo] = field(default_factory=list)
    inputs: list[InputInfo] = field(default_factory=list)
    interfaces: list[InterfaceInfo] = field(default_factory=list)
    unions: list[UnionInfo] = field(default_factory=list)
    scalars: list[str] = field(default_factory=list)
    query_type: TypeInfo | None = None
    mutation_type: TypeInfo | None = None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# Built-in scalar names.
_BUILTIN_SCALARS = {"String", "Int", "Float", "Boolean", "ID"}

# Custom scalar -> Python type mapping.
_CUSTOM_SCALAR_MAP: dict[str, str] = {
    "DateTime": "str",
    "JSON": "Any",
}


def parse_schema(path: str | Path) -> SchemaInfo:
    """Parse a ``.graphqls`` file and return a :class:`SchemaInfo`."""
    return parse_schema_from_text(Path(path).read_text())


def parse_schema_from_text(schema_text: str) -> SchemaInfo:
    """Parse SDL text directly and return a :class:`SchemaInfo`."""
    text = schema_text

    # graphql-core's build_schema doesn't handle directives on input types
    # well, so we detect @oneOf manually.
    one_of_inputs = _detect_one_of_inputs(text)

    schema = build_schema(text)
    info = SchemaInfo()

    type_map = schema.type_map

    for name, gql_type in sorted(type_map.items()):
        # Skip built-in introspection types.
        if name.startswith("__"):
            continue

        if isinstance(gql_type, GraphQLEnumType):
            info.enums.append(_extract_enum(gql_type))

        elif isinstance(gql_type, GraphQLInputObjectType):
            inp = _extract_input(gql_type)
            inp.is_one_of = name in one_of_inputs
            info.inputs.append(inp)

        elif isinstance(gql_type, GraphQLInterfaceType):
            iface = _extract_interface(gql_type, type_map)
            info.interfaces.append(iface)

        elif isinstance(gql_type, GraphQLUnionType):
            info.unions.append(_extract_union(gql_type))

        elif isinstance(gql_type, GraphQLScalarType):
            if name not in _BUILTIN_SCALARS:
                info.scalars.append(name)

        elif isinstance(gql_type, GraphQLObjectType):
            type_info = _extract_type(gql_type)
            if name == "Query":
                info.query_type = type_info
            elif name == "Mutation":
                info.mutation_type = type_info
            elif name == "Subscription":
                pass  # skip subscriptions
            else:
                info.types.append(type_info)



    return info


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------

def _extract_type(gql_type: GraphQLObjectType) -> TypeInfo:
    return TypeInfo(
        name=gql_type.name,
        fields=[_extract_field(name, f) for name, f in gql_type.fields.items()],
        description=gql_type.description or "",
        interfaces=[iface.name for iface in gql_type.interfaces],
    )


def _extract_enum(gql_type: GraphQLEnumType) -> EnumInfo:
    return EnumInfo(
        name=gql_type.name,
        values=list(gql_type.values.keys()),
        description=gql_type.description or "",
    )


def _extract_input(gql_type: GraphQLInputObjectType) -> InputInfo:
    fields = []
    for name, f in gql_type.fields.items():
        graphql_type_str = _type_to_string(f.type)
        python_type_str = _graphql_type_to_python(f.type)
        is_non_null = isinstance(f.type, GraphQLNonNull)
        is_list = _is_list_type(f.type)
        fields.append(FieldInfo(
            name=name,
            graphql_type=graphql_type_str,
            python_type=python_type_str,
            is_non_null=is_non_null,
            is_list=is_list,
            description=f.description or "",
        ))
    return InputInfo(
        name=gql_type.name,
        fields=fields,
        description=gql_type.description or "",
    )


def _extract_interface(
    gql_type: GraphQLInterfaceType,
    type_map: dict[str, GraphQLNamedType],
) -> InterfaceInfo:
    implementing = []
    for name, t in type_map.items():
        if isinstance(t, GraphQLObjectType):
            if gql_type in t.interfaces:
                implementing.append(name)
    return InterfaceInfo(
        name=gql_type.name,
        fields=[_extract_field(name, f) for name, f in gql_type.fields.items()],
        implementing_types=sorted(implementing),
        description=gql_type.description or "",
    )


def _extract_union(gql_type: GraphQLUnionType) -> UnionInfo:
    return UnionInfo(
        name=gql_type.name,
        member_types=[t.name for t in gql_type.types],
        description=gql_type.description or "",
    )


def _extract_field(name: str, gql_field: GraphQLField) -> FieldInfo:
    graphql_type_str = _type_to_string(gql_field.type)
    python_type_str = _graphql_type_to_python(gql_field.type)
    is_non_null = isinstance(gql_field.type, GraphQLNonNull)
    is_list = _is_list_type(gql_field.type)

    args = []
    for arg_name, arg in gql_field.args.items():
        args.append(FieldArgInfo(
            name=arg_name,
            graphql_type=_type_to_string(arg.type),
            python_type=_graphql_type_to_python(arg.type),
            default=arg.default_value,
            description=arg.description or "",
        ))

    return FieldInfo(
        name=name,
        graphql_type=graphql_type_str,
        python_type=python_type_str,
        is_non_null=is_non_null,
        is_list=is_list,
        description=gql_field.description or "",
        arguments=args,
    )


# ---------------------------------------------------------------------------
# Type string helpers
# ---------------------------------------------------------------------------

def _type_to_string(gql_type: Any) -> str:
    """Convert a graphql-core type to its schema string representation."""
    if isinstance(gql_type, GraphQLNonNull):
        return f"{_type_to_string(gql_type.of_type)}!"
    if isinstance(gql_type, GraphQLList):
        return f"[{_type_to_string(gql_type.of_type)}]"
    return gql_type.name


_SCALAR_MAP: dict[str, str] = {
    "String": "str",
    "Int": "int",
    "Float": "float",
    "Boolean": "bool",
    "ID": "str",
    **_CUSTOM_SCALAR_MAP,
}


def _graphql_type_to_python(gql_type: Any, nullable: bool = True) -> str:
    """Convert a graphql-core type object to a Python type annotation string."""
    if isinstance(gql_type, GraphQLNonNull):
        return _graphql_type_to_python(gql_type.of_type, nullable=False)
    if isinstance(gql_type, GraphQLList):
        inner = _graphql_type_to_python(gql_type.of_type, nullable=True)
        base = f"list[{inner}]"
        return f"{base} | None" if nullable else base
    # Named type.
    name = gql_type.name
    py_name = _SCALAR_MAP.get(name, name)
    return f"{py_name} | None" if nullable else py_name


def _is_list_type(gql_type: Any) -> bool:
    if isinstance(gql_type, GraphQLNonNull):
        return _is_list_type(gql_type.of_type)
    return isinstance(gql_type, GraphQLList)


def _detect_one_of_inputs(schema_text: str) -> set[str]:
    """Find input type names that have the @oneOf directive."""
    pattern = r"input\s+(\w+)\s+@oneOf\b"
    return set(re.findall(pattern, schema_text))
