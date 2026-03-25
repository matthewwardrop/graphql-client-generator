"""Command-line interface for the GraphQL client generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .generator import generate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="graphql-client-generator",
        description="Generate a typed Python client from a GraphQL schema.",
    )
    parser.add_argument(
        "schema",
        help="Path to the .graphqls schema file.",
    )
    parser.add_argument(
        "-n", "--name",
        help="Package name for the generated client (default: schema filename stem).",
        default=None,
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory (default: current working directory).",
        default=".",
    )

    args = parser.parse_args(argv)

    schema_path = Path(args.schema)
    if not schema_path.exists():
        print(f"Error: schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    package_name = args.name or schema_path.stem
    output_dir = Path(args.output)

    result_path = generate(schema_path, package_name, output_dir)
    print(f"Generated package: {result_path}")
