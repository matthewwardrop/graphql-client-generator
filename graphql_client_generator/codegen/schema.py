"""Generate the schema query-builder namespace from GraphQL root types."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .._runtime.serialization import to_snake_case

if TYPE_CHECKING:
    from ..parser import FieldInfo, SchemaInfo


def generate_schema(schema: SchemaInfo, schema_class_name: str) -> str:
    """Return the contents of ``schema.py`` for the generated package."""
    # Collect composite type names so we know which fields need a target_cls.
    all_composite_names: set[str] = set()
    for t in schema.types:
        all_composite_names.add(t.name)
    for iface in schema.interfaces:
        all_composite_names.add(iface.name)

    lines = [
        '"""GraphQL schema query builder."""',
        "",
        "from . import outputs",
        "from ._runtime.builder import BuiltQuery, SchemaField",
        "",
    ]

    lines.extend(
        _generate_schema_class(
            schema_class_name,
            schema,
            all_composite_names,
        )
    )
    lines.append("")

    return "\n".join(lines)


def _generate_schema_class(
    schema_class_name: str,
    schema: SchemaInfo,
    composite_names: set[str],
) -> list[str]:
    """Generate the root schema namespace class."""
    lines: list[str] = []

    lines.append("")
    lines.append(f"class _{schema_class_name}:")
    lines.append('    """Root query fields.  Use ``Schema[...]`` to build a query."""')
    lines.append("")

    # Query root fields.
    if schema.query_type:
        for f in schema.query_type.fields:
            lines.append(_generate_schema_field(f, composite_names, indent=4))
        lines.append("")

    # __getitem__ to build a BuiltQuery.
    lines.append("    def __getitem__(self, selections):")
    lines.append("        if not isinstance(selections, tuple):")
    lines.append("            selections = (selections,)")
    lines.append('        return BuiltQuery(list(selections), {}, "query")')
    lines.append("")

    # Mutation sub-namespace.
    if schema.mutation_type and schema.mutation_type.fields:
        lines.append("    class mutate:")
        lines.append('        """Mutation root fields.  Use ``Schema.mutate[...]``."""')
        lines.append("")
        for f in schema.mutation_type.fields:
            lines.append(_generate_schema_field(f, composite_names, indent=8))
        lines.append("")
        lines.append("        def __getitem__(self, selections):")
        lines.append("            if not isinstance(selections, tuple):")
        lines.append("                selections = (selections,)")
        lines.append('            return BuiltQuery(list(selections), {}, "mutation")')
        lines.append("")

    # __dir__ for tab completion.
    lines.append("    def __dir__(self):")
    lines.append("        return [")
    if schema.query_type:
        for f in schema.query_type.fields:
            py_name = to_snake_case(f.name)
            lines.append(f'            "{py_name}",')
    lines.append("        ]")
    lines.append("")

    # Singleton instance.
    lines.append(f"{schema_class_name} = _{schema_class_name}()")

    return lines


def _generate_schema_field(
    f: FieldInfo,
    composite_names: set[str],
    indent: int,
) -> str:
    """Generate a single SchemaField line using direct outputs.<Type> references."""
    pad = " " * indent
    py_name = to_snake_case(f.name)
    target_type = _unwrap_type_name(f.graphql_type)
    target_cls = f"outputs.{target_type}" if target_type in composite_names else "None"

    # Build arg_types dict if the field has arguments.
    arg_types_str = ""
    if f.arguments:
        arg_entries = ", ".join(f'"{a.name}": "{a.graphql_type}"' for a in f.arguments)
        arg_types_str = f", arg_types={{{arg_entries}}}"

    # Build doc string.
    doc_str = ""
    if f.arguments:
        arg_sig = ", ".join(f"{a.name}: {a.graphql_type}" for a in f.arguments)
        doc_str = f', doc="{f.name}({arg_sig})"'

    return (
        f'{pad}{py_name} = SchemaField("{f.name}", '
        f'graphql_type="{f.graphql_type}", '
        f"target_cls={target_cls}"
        f"{arg_types_str}{doc_str})"
    )


def _unwrap_type_name(graphql_type: str) -> str:
    """Extract the base type name from ``[Foo!]!`` -> ``Foo``."""
    return re.sub(r"[!\[\]]", "", graphql_type).strip()
