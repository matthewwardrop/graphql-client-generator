"""Command-line interface for the GraphQL client generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .generator import generate_from_endpoint, generate_from_file


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
        "-n",
        "--name",
        help="Package name for the generated client (default: schema filename stem or 'client').",
        default=None,
    )
    parser.add_argument(
        "-o",
        "--output",
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
        "-H",
        "--header",
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

    try:
        if args.schema.startswith(("http://", "https://")):
            # Remote endpoint - fetch schema via introspection.
            headers = _parse_headers(args.headers)
            package_name = args.name or "client"
            result_path = generate_from_endpoint(
                args.schema,
                package_name,
                output_dir,
                headers=headers or None,
                as_package=not args.module,
            )
        else:
            # Local file.
            schema_path = Path(args.schema)
            package_name = args.name or schema_path.stem
            result_path = generate_from_file(
                schema_path,
                package_name,
                output_dir,
                as_package=not args.module,
            )
    except (RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

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
