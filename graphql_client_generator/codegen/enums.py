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
        lines.append(f"class {enum.name}(Enum):")
        if enum.description:
            lines.extend(_format_docstring(enum.description, 4))

        if not enum.values:
            lines.append("    pass")
        else:
            for val in enum.values:
                lines.append(f'    {val} = "{val}"')

        lines.append("")

    return "\n".join(lines)


def _format_docstring(description: str, indent: int) -> list[str]:
    """Return a properly indented triple-quoted docstring for *description*."""
    pad = " " * indent
    escaped = description.replace('"""', r'\"\"\"')
    raw = escaped.splitlines()
    if len(raw) == 1:
        return [f'{pad}"""{escaped}"""']
    result = [f'{pad}"""']
    for line in raw:
        stripped = line.strip()
        result.append(f"{pad}{stripped}" if stripped else "")
    result.append(f'{pad}"""')
    return result
