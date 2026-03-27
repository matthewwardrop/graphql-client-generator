"""Generate Python dataclass input types from GraphQL input types."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._runtime.serialization import to_snake_case

if TYPE_CHECKING:
    from ..parser import FieldInfo, InputInfo, SchemaInfo


def generate_inputs(schema: SchemaInfo) -> str:
    """Return the contents of ``inputs.py`` for the generated package."""
    lines = [
        '"""GraphQL input types."""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass, field as dc_field",
        "from typing import Any",
        "",
        "from ._runtime.serialization import serialize_input",
        "",
    ]

    # Forward-reference all enum names we might need.
    enum_names = {e.name for e in schema.enums}

    for inp in sorted(schema.inputs, key=lambda i: i.name):
        lines.extend(_generate_input(inp, enum_names))
        lines.append("")

    return "\n".join(lines)


def _generate_input(inp: InputInfo, enum_names: set[str]) -> list[str]:
    lines: list[str] = []
    lines.append("")
    lines.append("@dataclass")
    lines.append(f"class {inp.name}:")
    if inp.description:
        lines.extend(_format_docstring(inp.description, 4))
    if inp.is_one_of:
        lines.append("    # @oneOf: exactly one field must be provided.")
    lines.append("")

    # Split fields into required (non-null, no default) and optional.
    required_fields: list[FieldInfo] = []
    optional_fields: list[FieldInfo] = []
    for f in inp.fields:
        if f.is_non_null and not f.has_default:
            required_fields.append(f)
        else:
            optional_fields.append(f)

    # Emit required fields first (dataclass requires them before defaults).
    for f in required_fields:
        py_name = to_snake_case(f.name)
        py_type = _input_python_type(f.python_type)
        comment = f"  # {f.graphql_type}" if f.graphql_type else ""
        if f.description:
            lines.extend(_format_comment(f.description, 4))
        lines.append(f"    {py_name}: {py_type}{comment}")

    for f in optional_fields:
        py_name = to_snake_case(f.name)
        py_type = _input_python_type(f.python_type)
        comment = f"  # {f.graphql_type}" if f.graphql_type else ""
        if f.description:
            lines.extend(_format_comment(f.description, 4))
        lines.append(f"    {py_name}: {py_type} = None{comment}")

    if not required_fields and not optional_fields:
        lines.append("    pass")

    # __post_init__ for validation (only when there is something to validate)
    if inp.is_one_of or required_fields:
        lines.append("")
        lines.append("    def __post_init__(self) -> None:")
        if inp.is_one_of:
            field_names_str = ", ".join(f'"{to_snake_case(f.name)}"' for f in inp.fields)
            lines.append(f"        _fields = [{field_names_str}]")
            lines.append("        _set = [f for f in _fields if getattr(self, f) is not None]")
            lines.append("        if len(_set) != 1:")
            lines.append("            raise ValueError(")
            lines.append(
                f'                f"Exactly one field must be set on @oneOf input '
                f"{inp.name}, got: {{_set or 'none'}}\""
            )
            lines.append("            )")
        else:
            for f in required_fields:
                py_name = to_snake_case(f.name)
                lines.append(f"        if self.{py_name} is None:")
                lines.append(f'            raise ValueError("{py_name} is required on {inp.name}")')

    # to_dict
    lines.append("")
    lines.append("    def to_dict(self) -> dict[str, Any]:")
    lines.append('        """Serialize to a dict with camelCase keys for GraphQL variables."""')
    lines.append("        return serialize_input(self)")

    return lines


def _input_python_type(python_type: str) -> str:
    """Ensure input type annotation is suitable for dataclass default handling."""
    return python_type


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
