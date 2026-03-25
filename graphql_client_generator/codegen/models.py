"""Generate Python model classes from GraphQL object types and interfaces."""

from __future__ import annotations

import re

from .._runtime.serialization import to_snake_case
from ..parser import FieldInfo, SchemaInfo


# Scalar type names that should NOT get a target_cls.
_SCALAR_NAMES = {"str", "int", "float", "bool", "Any"}


def generate_models(schema: SchemaInfo, schema_class_name: str) -> str:
    """Return the contents of ``models.py`` for the generated package."""
    # Collect all type/interface names so we know which fields are composite.
    all_composite_names: set[str] = set()
    for t in schema.types:
        all_composite_names.add(t.name)
    for iface in schema.interfaces:
        all_composite_names.add(iface.name)

    lines = [
        '"""GraphQL schema types and query builder."""',
        "",
        "from __future__ import annotations",
        "",
        "from ._runtime.builder import BuiltQuery, SchemaField",
        "from ._runtime.client import GraphQLClientBase, _ResultRoot",
        "from ._runtime.model import GraphQLModel",
        "",
    ]

    # Collect all type names for the registry.
    all_type_names: list[str] = []

    # Interfaces first (they are base classes).
    for iface in sorted(schema.interfaces, key=lambda i: i.name):
        lines.extend(_generate_model_class(
            iface.name, iface.fields, iface.description,
            base="GraphQLModel", composite_names=all_composite_names,
        ))
        lines.append("")
        all_type_names.append(iface.name)

    # Object types.
    for t in sorted(schema.types, key=lambda t: t.name):
        base = t.interfaces[0] if t.interfaces else "GraphQLModel"
        lines.extend(_generate_model_class(
            t.name, t.fields, t.description,
            base=base, composite_names=all_composite_names,
        ))
        lines.append("")
        all_type_names.append(t.name)

    # Union type aliases.
    for union in sorted(schema.unions, key=lambda u: u.name):
        members = " | ".join(union.member_types)
        if union.description:
            lines.append(f"# {union.description}")
        lines.append(f"{union.name} = {members}")
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

    # Schema namespace class.
    lines.extend(_generate_schema_class(
        schema_class_name, schema, all_composite_names,
    ))
    lines.append("")

    return "\n".join(lines)


def _generate_model_class(
    name: str,
    fields: list[FieldInfo],
    description: str,
    base: str,
    composite_names: set[str],
) -> list[str]:
    """Generate a single model class with SchemaField descriptors."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"class {name}({base}):")
    if description:
        lines.append(f'    """{_escape_docstring(description)}"""')
    lines.append(f'    __typename__ = "{name}"')
    lines.append("")

    if not fields:
        lines.append("    pass")
        return lines

    for f in fields:
        lines.append(_generate_schema_field(f, composite_names, indent=4))

    return lines


def _generate_schema_field(
    f: FieldInfo,
    composite_names: set[str],
    indent: int,
) -> str:
    """Generate a single SchemaField line."""
    pad = " " * indent
    py_name = to_snake_case(f.name)
    target_type = _unwrap_type_name(f.graphql_type)
    target_cls = f"lambda: {target_type}" if target_type in composite_names else "None"

    # Build arg_types dict if the field has arguments.
    arg_types_str = ""
    if f.arguments:
        arg_entries = ", ".join(
            f'"{a.name}": "{a.graphql_type}"' for a in f.arguments
        )
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
        py_type = _model_python_type(f.python_type)
        lines.append(f"    {py_name}: {py_type}")
    return lines


def _model_python_type(python_type: str) -> str:
    """The Python type annotation for a model field."""
    return python_type


def _escape_docstring(s: str) -> str:
    return s.replace('"""', r'\"\"\"')


def _unwrap_type_name(graphql_type: str) -> str:
    """Extract the base type name from ``[Foo!]!`` -> ``Foo``."""
    return re.sub(r"[!\[\]]", "", graphql_type).strip()
