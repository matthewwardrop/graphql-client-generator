"""Generate Python enum classes from GraphQL enum types."""

from __future__ import annotations

from ..parser import SchemaInfo


def generate_enums(schema: SchemaInfo) -> str:
    """Return the contents of ``enums.py`` for the generated package."""
    lines = [
        '"""GraphQL enum types."""',
        "",
        "from enum import Enum",
        "",
    ]

    for enum in sorted(schema.enums, key=lambda e: e.name):
        lines.append("")
        if enum.description:
            lines.append(f'class {enum.name}(Enum):')
            lines.append(f'    """{_escape_docstring(enum.description)}"""')
        else:
            lines.append(f"class {enum.name}(Enum):")

        if not enum.values:
            lines.append("    pass")
        else:
            for val in enum.values:
                lines.append(f'    {val} = "{val}"')

        lines.append("")

    return "\n".join(lines)


def _escape_docstring(s: str) -> str:
    return s.replace('"""', r'\"\"\"')
