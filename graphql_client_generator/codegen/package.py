"""Generate package scaffolding: __init__.py and pyproject.toml."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..parser import SchemaInfo


def generate_init(
    schema: SchemaInfo,
    package_name: str,
    client_class_name: str,
    schema_class_name: str,
) -> str:
    """Return the contents of ``__init__.py`` for the generated package."""
    lines = [
        f'"""Generated GraphQL client package: {package_name}."""',
        "",
        f"from .client import {client_class_name}",
        "from .models import *  # noqa: F401,F403",
        "from .enums import *  # noqa: F401,F403",
        "from .inputs import *  # noqa: F401,F403",
        "from ._runtime.builder import Variable",
        "",
        f"__all__ = [{client_class_name!r}, {schema_class_name!r}, 'Variable']",
        "",
    ]
    return "\n".join(lines)


def generate_pyproject(package_name: str) -> str:
    """Return the contents of ``pyproject.toml`` for the generated package."""
    return f"""\
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "0.1.0"
description = "Generated GraphQL client for {package_name}"
requires-python = ">=3.10"
dependencies = [
    "requests",
    "graphql-core>=3.2",
]
"""
