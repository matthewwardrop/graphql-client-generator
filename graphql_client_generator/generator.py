"""Orchestrates the generation of a complete Python client package from a
GraphQL schema."""

from __future__ import annotations

import shutil
from pathlib import Path

from .codegen.client import generate_client
from .codegen.enums import generate_enums
from .codegen.inputs import generate_inputs
from .codegen.models import generate_models
from .codegen.package import generate_init, generate_pyproject
from .parser import parse_schema


def generate(
    schema_path: str | Path,
    package_name: str,
    output_dir: str | Path,
) -> Path:
    """Generate a complete Python client package from a ``.graphqls`` schema.

    Returns the path to the generated package directory.
    """
    schema_path = Path(schema_path)
    output_dir = Path(output_dir)
    package_dir = output_dir / package_name

    # Parse the schema.
    schema = parse_schema(schema_path)

    # Derive client class name: snake_case package name -> PascalCase + "Client"
    client_class_name = _to_pascal_case(package_name) + "Client"

    # Create the package directory.
    package_dir.mkdir(parents=True, exist_ok=True)

    # Copy _runtime/ into the generated package.
    runtime_src = Path(__file__).parent / "_runtime"
    runtime_dst = package_dir / "_runtime"
    if runtime_dst.exists():
        shutil.rmtree(runtime_dst)
    shutil.copytree(runtime_src, runtime_dst)

    # Generate files.
    _write(package_dir / "enums.py", generate_enums(schema))
    _write(package_dir / "inputs.py", generate_inputs(schema))
    _write(package_dir / "models.py", generate_models(schema))
    _write(package_dir / "client.py", generate_client(schema, client_class_name))
    _write(package_dir / "__init__.py", generate_init(schema, package_name, client_class_name))
    _write(package_dir / "pyproject.toml", generate_pyproject(package_name))

    return package_dir


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _to_pascal_case(name: str) -> str:
    """Convert ``snake_case`` or ``kebab-case`` to ``PascalCase``."""
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts)
