"""Orchestrates the generation of a complete Python client package from a
GraphQL schema."""

from __future__ import annotations

import shutil
from pathlib import Path

from .codegen.client import generate_client
from .codegen.enums import generate_enums
from .codegen.inputs import generate_inputs
from .codegen.outputs import generate_outputs
from .codegen.schema import generate_schema
from .codegen.package import generate_init, generate_pyproject
from .introspection import fetch_schema_sdl
from .parser import parse_schema_from_text


def generate_from_file(
    schema_path: str | Path,
    package_name: str,
    output_dir: str | Path = ".",
    as_package: bool = True,
) -> Path:
    """Generate a Python client from a ``.graphqls`` schema file.

    Returns the path to the generated directory.
    """
    schema_path = Path(schema_path)
    flags = "" if str(output_dir) == "." else f" -o {output_dir}"
    if not as_package:
        flags += " --module"
    regen_command = f"python -m graphql_client_generator {schema_path} -n {package_name}{flags}"
    return generate_from_text(schema_path.read_text(), package_name, output_dir, as_package, regen_command=regen_command)


def generate_from_text(
    schema_text: str,
    package_name: str,
    output_dir: str | Path = ".",
    as_package: bool = True,
    regen_command: str = "",
) -> Path:
    """Generate a Python client from SDL text.

    When *as_package* is ``True`` (the default) a standalone ``pyproject.toml``
    is written alongside the Python sources, producing a complete installable
    package.  Pass ``as_package=False`` to emit only the Python files, suitable
    for embedding inside an existing package.

    Returns the path to the generated directory.
    """
    output_dir = Path(output_dir)
    # Normalise: distribution name uses hyphens, Python module name uses underscores.
    dist_name = package_name.replace("_", "-")
    python_name = package_name.replace("-", "_")

    if as_package:
        project_dir = output_dir / dist_name
        module_dir = project_dir / python_name
    else:
        project_dir = output_dir / python_name
        module_dir = project_dir

    # Parse the schema.
    schema = parse_schema_from_text(schema_text)

    # Derive class names from the package name.
    pascal = _to_pascal_case(package_name)
    client_class_name = pascal + "Client"
    schema_class_name = pascal + "Schema"

    # Create the module directory (and any parents).
    module_dir.mkdir(parents=True, exist_ok=True)

    # Copy _runtime/ into the module directory.
    runtime_src = Path(__file__).parent / "_runtime"
    runtime_dst = module_dir / "_runtime"
    if runtime_dst.exists():
        shutil.rmtree(runtime_dst)
    shutil.copytree(runtime_src, runtime_dst)

    # Generate Python source files.
    _write(module_dir / "enums.py", generate_enums(schema))
    _write(module_dir / "inputs.py", generate_inputs(schema))
    _write(module_dir / "outputs.py", generate_outputs(schema))
    _write(module_dir / "schema.py", generate_schema(schema, schema_class_name))
    _write(module_dir / "client.py", generate_client(schema, client_class_name))
    _write(
        module_dir / "__init__.py",
        generate_init(schema, python_name, client_class_name, schema_class_name, regen_command),
    )
    if as_package:
        _write(project_dir / "pyproject.toml", generate_pyproject(dist_name))

    return project_dir


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def generate_from_endpoint(
    endpoint: str,
    name: str,
    output_dir: str | Path = ".",
    session: object | None = None,
    headers: dict[str, str] | None = None,
    as_package: bool = True,
) -> Path:
    """Generate a typed Python client package by introspecting a live GraphQL endpoint.

    This is the recommended entry point for notebook-driven workflows where a
    ``requests.Session`` with auth, cookies, or custom TLS settings is already
    configured.

    Parameters
    ----------
    endpoint:
        The GraphQL HTTP endpoint URL.
    name:
        Package name for the generated client directory.
    output_dir:
        Directory in which to create the package (default: current directory).
    session:
        An optional ``requests.Session``.  When supplied its auth/headers are
        used for the introspection request.
    headers:
        Extra HTTP headers to add to the introspection request, e.g.
        ``{"Authorization": "Bearer <token>"}``.

    Returns
    -------
    pathlib.Path
        The path to the generated package directory.

    Examples
    --------
    >>> import requests
    >>> import graphql_client_generator as gcg
    >>> s = requests.Session()
    >>> s.headers["Authorization"] = "Bearer <token>"
    >>> gcg.generate_from_endpoint("https://api.example.com/graphql", "my_client", session=s)
    PosixPath('my_client')
    """
    schema_text = fetch_schema_sdl(endpoint, session=session, headers=headers)
    flags = "" if str(output_dir) == "." else f" -o {output_dir}"
    if not as_package:
        flags += " --module"
    regen_command = f"python -m graphql_client_generator {endpoint} -n {name}{flags}"
    return generate_from_text(schema_text, name, output_dir, as_package, regen_command=regen_command)


def _to_pascal_case(name: str) -> str:
    """Convert ``snake_case`` or ``kebab-case`` to ``PascalCase``."""
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts)
