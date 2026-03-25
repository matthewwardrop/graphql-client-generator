"""Generate Python model classes from GraphQL object types and interfaces."""

from __future__ import annotations

from .._runtime.serialization import to_snake_case
from ..parser import FieldInfo, SchemaInfo


def generate_models(schema: SchemaInfo) -> str:
    """Return the contents of ``models.py`` for the generated package."""
    lines = [
        '"""GraphQL result types."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any, TypeVar",
        "",
        "import requests",
        "",
        "from ._runtime.model import GraphQLModel, graphql_field, QueryContext",
        "from ._runtime.client import GraphQLClientBase, _ResultRoot",
        "",
    ]

    # Collect all type names for the registry.
    all_type_names: list[str] = []

    # Interfaces first (they are base classes).
    for iface in sorted(schema.interfaces, key=lambda i: i.name):
        lines.extend(_generate_model_class(
            iface.name, iface.fields, iface.description, base="GraphQLModel",
        ))
        lines.append("")
        all_type_names.append(iface.name)

    # Object types.
    for t in sorted(schema.types, key=lambda t: t.name):
        # Determine base class: if type implements interfaces, use the first one.
        if t.interfaces:
            base = t.interfaces[0]
        else:
            base = "GraphQLModel"
        lines.extend(_generate_model_class(
            t.name, t.fields, t.description, base=base,
        ))
        lines.append("")
        all_type_names.append(t.name)

    # Union type aliases.
    for union in sorted(schema.unions, key=lambda u: u.name):
        members = " | ".join(union.member_types)
        if union.description:
            lines.append(f'# {union.description}')
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

    return "\n".join(lines)


def _generate_model_class(
    name: str,
    fields: list[FieldInfo],
    description: str,
    base: str,
) -> list[str]:
    """Generate a single model class."""
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
        py_name = to_snake_case(f.name)
        py_type = _model_python_type(f.python_type)
        lines.append(
            f"    {py_name}: {py_type} = graphql_field(\"{f.name}\", graphql_type=\"{f.graphql_type}\")"
        )

    # from_query classmethod
    lines.append("")
    lines.append("    T = TypeVar(\"T\", bound=\"GraphQLModel\")")
    lines.append("")
    lines.append("    @classmethod")
    lines.append("    def from_query(")
    lines.append("        cls,")
    lines.append("        query: str,")
    lines.append("        variables: dict[str, Any] | None = None,")
    lines.append("        operation_name: str | None = None,")
    lines.append("        *,")
    lines.append("        endpoint: str,")
    lines.append("        session: requests.Session | None = None,")
    lines.append("        auto_fetch: bool = True,")
    lines.append(f"    ) -> {name}:")
    lines.append(f'        """Execute a query and return a typed {name} result."""')
    lines.append("        client = GraphQLClientBase(")
    lines.append("            endpoint=endpoint,")
    lines.append("            session=session or requests.Session(),")
    lines.append("            auto_fetch=auto_fetch,")
    lines.append("        )")
    lines.append("        client._type_registry = TYPE_REGISTRY")
    lines.append("        return client.query(query, variables, operation_name)")

    return lines


def _generate_result_class(name: str, fields: list[FieldInfo]) -> list[str]:
    """Generate a typed _ResultRoot subclass with annotation-only attributes."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"class {name}(_ResultRoot):")
    lines.append(f'    """Typed result for {"query" if name == "QueryResult" else "mutation"} operations."""')
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
    """The Python type annotation for a model field.

    All model fields are effectively optional at the Python level (a query
    may or may not select them), but the descriptor handles access semantics.
    The annotation reflects the GraphQL schema nullability.
    """
    return python_type


def _escape_docstring(s: str) -> str:
    return s.replace('"""', r'\"\"\"')
