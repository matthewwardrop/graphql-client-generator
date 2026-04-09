"""Generate the schema query-builder namespace from GraphQL root types."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .._runtime.serialization import to_snake_case

if TYPE_CHECKING:
    from ..parser import FieldInfo, InputInfo, SchemaInfo


def generate_schema(
    schema: SchemaInfo,
    schema_class_name: str,
    mutation_class_name: str = "",
) -> str:
    """Return the contents of ``schema.py`` for the generated package."""
    # Collect composite type names so we know which fields need a target_cls.
    all_composite_names: set[str] = set()
    for t in schema.types:
        all_composite_names.add(t.name)
    for iface in schema.interfaces:
        all_composite_names.add(iface.name)
    for union in schema.unions:
        all_composite_names.add(union.name)

    # Build input map for detecting and flattening input args.
    input_map: dict[str, InputInfo] = {inp.name: inp for inp in schema.inputs}

    lines = [
        '"""GraphQL schema query builder."""',
        "",
        "from . import inputs, outputs",
        "from ._runtime.builder import BuiltQuery, SchemaField",
        "",
    ]

    # Query schema.
    if schema.query_type:
        lines.extend(
            _generate_root_class(
                schema_class_name,
                schema.query_type.fields,
                all_composite_names,
                input_map,
                operation_type="query",
            )
        )
    else:
        lines.extend(
            _generate_root_class(
                schema_class_name,
                [],
                all_composite_names,
                input_map,
                operation_type="query",
            )
        )

    # Mutation schema.
    if mutation_class_name and schema.mutation_type:
        lines.append("")
        lines.extend(
            _generate_root_class(
                mutation_class_name,
                schema.mutation_type.fields,
                all_composite_names,
                input_map,
                operation_type="mutation",
            )
        )

    lines.append("")

    return "\n".join(lines)


def _generate_root_class(
    class_name: str,
    fields: list[FieldInfo],
    composite_names: set[str],
    input_map: dict[str, InputInfo],
    operation_type: str = "query",
) -> list[str]:
    """Generate a root schema namespace class (query or mutation)."""
    lines: list[str] = []
    kind = "Query" if operation_type == "query" else "Mutation"

    lines.append("")
    lines.append(f"class _{class_name}:")
    lines.append(
        f'    """Root {kind.lower()} fields.  '
        f'Use ``{class_name}[...]`` to build a {kind.lower()}."""'
    )
    lines.append("")

    for f in fields:
        detected = _detect_input_arg(f, input_map)
        lines.append(_generate_schema_field(f, composite_names, indent=4, input_info=detected))
    if fields:
        lines.append("")

    # __getitem__ to build a BuiltQuery.
    lines.append("    def __getitem__(self, selections):")
    lines.append("        if not isinstance(selections, tuple):")
    lines.append("            selections = (selections,)")
    lines.append(f'        return BuiltQuery(list(selections), {{}}, "{operation_type}")')
    lines.append("")

    # __dir__ for tab completion.
    lines.append("    def __dir__(self):")
    lines.append("        return [")
    for f in fields:
        py_name = to_snake_case(f.name)
        lines.append(f'            "{py_name}",')
    lines.append("        ]")
    lines.append("")

    # Singleton instance.
    lines.append(f"{class_name} = _{class_name}()")

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
    """Generate a single SchemaField line using direct outputs.<Type> references."""
    pad = " " * indent
    py_name = to_snake_case(f.name)
    target_type = _unwrap_type_name(f.graphql_type)
    target_cls = f"outputs.{target_type}" if target_type in composite_names else "None"

    # Build arg_types dict and optional input_arg/input_cls.
    input_extra = ""
    if input_info:
        arg_name, inp = input_info
        # Flatten the Input type's fields as arg_types.
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


def _effective_arg_type(graphql_type: str, has_default: bool) -> str:
    """Strip trailing ``!`` when the arg has a schema default (not required from client)."""
    if has_default and graphql_type.endswith("!"):
        return graphql_type[:-1]
    return graphql_type


def _unwrap_type_name(graphql_type: str) -> str:
    """Extract the base type name from ``[Foo!]!`` -> ``Foo``."""
    return re.sub(r"[!\[\]]", "", graphql_type).strip()
