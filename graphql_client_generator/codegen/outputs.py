"""Generate Python model classes from GraphQL object types and interfaces."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .._runtime.serialization import to_snake_case

if TYPE_CHECKING:
    from ..parser import FieldInfo, InputInfo, SchemaInfo

# Scalar type names that should NOT get a target_cls.
_SCALAR_NAMES = {"str", "int", "float", "bool", "Any"}


def generate_outputs(schema: SchemaInfo) -> str:
    """Return the contents of ``outputs.py`` for the generated package."""
    # Collect all type/interface/union names so we know which fields are composite.
    all_composite_names: set[str] = set()
    for t in schema.types:
        all_composite_names.add(t.name)
    for iface in schema.interfaces:
        all_composite_names.add(iface.name)
    for union in schema.unions:
        all_composite_names.add(union.name)

    # Build input map for detecting and flattening input args.
    input_map: dict[str, InputInfo] = {inp.name: inp for inp in schema.inputs}

    # Check if any output field references an input type (for conditional import).
    needs_inputs_import = _any_field_has_input_arg(schema, input_map)

    lines = [
        '"""GraphQL schema output types."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    if needs_inputs_import:
        lines.append("from . import inputs")
    lines.append("from ._runtime.builder import SchemaField")
    lines.append("from ._runtime.client import _ResultRoot")
    if schema.unions:
        lines.append("from ._runtime.model import GraphQLModel, GraphQLUnion")
    else:
        lines.append("from ._runtime.model import GraphQLModel")
    lines.append("")

    # Collect all type names for the registry.
    all_type_names: list[str] = []

    # Interfaces first (they are base classes).
    for iface in sorted(schema.interfaces, key=lambda i: i.name):
        lines.extend(
            _generate_model_class(
                iface.name,
                iface.fields,
                iface.description,
                base="GraphQLModel",
                composite_names=all_composite_names,
                input_map=input_map,
            )
        )
        lines.append("")
        all_type_names.append(iface.name)

    # Object types.
    for t in sorted(schema.types, key=lambda t: t.name):
        base = t.interfaces[0] if t.interfaces else "GraphQLModel"
        lines.extend(
            _generate_model_class(
                t.name,
                t.fields,
                t.description,
                base=base,
                composite_names=all_composite_names,
                input_map=input_map,
            )
        )
        lines.append("")
        all_type_names.append(t.name)

    # Union types.
    for union in sorted(schema.unions, key=lambda u: u.name):
        lines.append("")
        lines.append(f"class {union.name}(GraphQLUnion):")
        if union.description:
            lines.extend(_format_docstring(union.description, 4))
        members_str = ", ".join(union.member_types)
        lines.append(f"    __member_types__ = lambda: [{members_str}]")
        # Expose member types as class attributes for tab completion.
        for member_name in union.member_types:
            lines.append(f"    {member_name} = {member_name}")
        lines.append("")

    # Type registry: maps __typename -> class.
    lines.append("")
    lines.append("TYPE_REGISTRY: dict[str, type[GraphQLModel]] = {")
    for name in sorted(all_type_names):
        lines.append(f'    "{name}": {name},')
    lines.append("}")
    lines.append("")

    # QueryResult / MutationResult typed wrappers.
    if schema.query_type:
        lines.extend(_generate_result_class("QueryResult", schema.query_type.fields))
        lines.append("")
    if schema.mutation_type:
        lines.extend(_generate_result_class("MutationResult", schema.mutation_type.fields))
        lines.append("")

    return "\n".join(lines)


def _generate_model_class(
    name: str,
    fields: list[FieldInfo],
    description: str,
    base: str,
    composite_names: set[str],
    input_map: dict[str, InputInfo],
) -> list[str]:
    """Generate a single model class with SchemaField descriptors."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"class {name}({base}):")
    if description:
        lines.extend(_format_docstring(description, 4))
    lines.append(f'    __typename__ = "{name}"')
    lines.append("")

    if not fields:
        lines.append("    pass")
        return lines

    for f in fields:
        detected = _detect_input_arg(f, input_map)
        lines.append(_generate_schema_field(f, composite_names, indent=4, input_info=detected))

    return lines


def _detect_input_arg(
    f: FieldInfo,
    input_map: dict[str, InputInfo],
) -> tuple[str, InputInfo] | None:
    """Return (arg_name, InputInfo) if the field has exactly one Input-typed arg."""
    matches: list[tuple[str, InputInfo]] = []
    for a in f.arguments:
        type_name = _unwrap_type_name(a.graphql_type)
        if type_name in input_map:
            matches.append((a.name, input_map[type_name]))
    if len(matches) == 1:
        return matches[0]
    return None


def _generate_schema_field(
    f: FieldInfo,
    composite_names: set[str],
    indent: int,
    input_info: tuple[str, InputInfo] | None = None,
) -> str:
    """Generate a single SchemaField line (using lambda for deferred resolution)."""
    pad = " " * indent
    py_name = to_snake_case(f.name)
    target_type = _unwrap_type_name(f.graphql_type)
    target_cls = f"lambda: {target_type}" if target_type in composite_names else "None"

    # Build arg_types dict and optional input_arg/input_cls.
    input_extra = ""
    if input_info:
        arg_name, inp = input_info
        arg_entries = ", ".join(
            f'"{to_snake_case(field.name)}": '
            f'"{_effective_arg_type(field.graphql_type, field.has_default)}"'
            for field in inp.fields
        )
        arg_types_str = f", arg_types={{{arg_entries}}}"
        input_extra = f', input_arg="{arg_name}", input_cls=inputs.{inp.name}'
    elif f.arguments:
        arg_entries = ", ".join(
            f'"{a.name}": "{_effective_arg_type(a.graphql_type, a.has_default)}"'
            for a in f.arguments
        )
        arg_types_str = f", arg_types={{{arg_entries}}}"
    else:
        arg_types_str = ""

    # Build doc string.
    doc_str = ""
    if f.arguments:
        arg_sig = ", ".join(f"{a.name}: {a.graphql_type}" for a in f.arguments)
        doc_str = f', doc="{f.name}({arg_sig})"'

    return (
        f'{pad}{py_name} = SchemaField("{f.name}", '
        f'graphql_type="{f.graphql_type}", '
        f"target_cls={target_cls}"
        f"{arg_types_str}{doc_str}{input_extra})"
    )


def _generate_result_class(name: str, fields: list[FieldInfo]) -> list[str]:
    """Generate a typed _ResultRoot subclass with annotation-only attributes."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"class {name}(_ResultRoot):")
    kind = "query" if name == "QueryResult" else "mutation"
    lines.append(f'    """Typed result for {kind} operations."""')
    lines.append("")
    if not fields:
        lines.append("    pass")
        return lines
    for f in fields:
        py_name = to_snake_case(f.name)
        py_type = f.python_type
        lines.append(f"    {py_name}: {py_type}")
    return lines


def _format_docstring(description: str, indent: int) -> list[str]:
    """Return a properly indented triple-quoted docstring for *description*."""
    pad = " " * indent
    escaped = description.replace('"""', r"\"\"\"")
    raw = escaped.splitlines()
    if len(raw) == 1:
        return [f'{pad}"""{escaped}"""']
    result = [f'{pad}"""']
    for line in raw:
        stripped = line.strip()
        result.append(f"{pad}{stripped}" if stripped else "")
    result.append(f'{pad}"""')
    return result


def _format_comment(description: str, indent: int) -> list[str]:
    """Return each line of *description* as a ``# `` comment."""
    pad = " " * indent
    return [f"{pad}# {line}" if line.strip() else f"{pad}#" for line in description.splitlines()]


def _any_field_has_input_arg(
    schema: SchemaInfo,
    input_map: dict[str, InputInfo],
) -> bool:
    """Return True if any output type field has a detected input arg."""
    for t in schema.types:
        for f in t.fields:
            if _detect_input_arg(f, input_map):
                return True
    for iface in schema.interfaces:
        for f in iface.fields:
            if _detect_input_arg(f, input_map):
                return True
    return False


def _effective_arg_type(graphql_type: str, has_default: bool) -> str:
    """Strip trailing ``!`` when the arg has a schema default (not required from client)."""
    if has_default and graphql_type.endswith("!"):
        return graphql_type[:-1]
    return graphql_type


def _unwrap_type_name(graphql_type: str) -> str:
    """Extract the base type name from ``[Foo!]!`` -> ``Foo``."""
    return re.sub(r"[!\[\]]", "", graphql_type).strip()
