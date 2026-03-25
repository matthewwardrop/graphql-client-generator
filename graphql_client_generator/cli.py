"""Command-line interface for the GraphQL client generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .generator import generate_from_file, generate_from_text
from .introspection import fetch_schema_sdl


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="graphql-client-generator",
        description="Generate a typed Python client from a GraphQL schema.",
    )
    parser.add_argument(
        "schema",
        help="Path to a .graphqls schema file, or an http(s):// URL to fetch via introspection.",
    )
    parser.add_argument(
        "-n", "--name",
        help="Package name for the generated client (default: schema filename stem or 'client').",
        default=None,
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory (default: current working directory).",
        default=".",
    )
    parser.add_argument(
        "--module",
        action="store_true",
        help=(
            "Emit Python source files only (no pyproject.toml). "
            "Use this when embedding the generated client inside an existing package."
        ),
    )
    parser.add_argument(
        "-H", "--header",
        action="append",
        dest="headers",
        metavar="NAME:VALUE",
        help=(
            "Extra HTTP header for introspection requests, e.g. "
            '-H "Authorization: Bearer $TOKEN". '
            "May be repeated."
        ),
        default=[],
    )

    args = parser.parse_args(argv)

    output_dir = Path(args.output)

    if args.schema.startswith(("http://", "https://")):
        # Remote endpoint - fetch schema via introspection.
        headers = _parse_headers(args.headers)
        try:
            schema_text = fetch_schema_sdl(args.schema, headers=headers or None)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        package_name = args.name or "client"
        result_path = generate_from_text(schema_text, package_name, output_dir, as_package=not args.module)
    else:
        # Local file.
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"Error: schema file not found: {schema_path}", file=sys.stderr)
            sys.exit(1)

        package_name = args.name or schema_path.stem
        result_path = generate_from_file(schema_path, package_name, output_dir, as_package=not args.module)

    print(f"Generated: {result_path}")


def _parse_headers(raw: list[str]) -> dict[str, str]:
    """Parse a list of ``"Name: Value"`` strings into a dict."""
    headers: dict[str, str] = {}
    for item in raw:
        if ":" not in item:
            print(
                f"Warning: ignoring malformed header (expected 'Name: Value'): {item!r}",
                file=sys.stderr,
            )
            continue
        name, _, value = item.partition(":")
        headers[name.strip()] = value.strip()
    return headers
