"""Serialization helpers shared across generated models and inputs."""

from __future__ import annotations

from dataclasses import fields as dc_fields
from enum import Enum
from typing import Any


def to_camel_case(name: str) -> str:
    """Convert a snake_case name to camelCase."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def to_snake_case(name: str) -> str:
    """Convert a camelCase name to snake_case."""
    result: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            result.append("_")
        result.append(ch.lower())
    return "".join(result)


def serialize_input(obj: Any) -> Any:
    """Serialize a dataclass input value to a dict suitable for GraphQL
    variables.  Keys are converted to camelCase."""
    if obj is None:
        return None
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [serialize_input(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize_input(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        result: dict[str, Any] = {}
        for f in dc_fields(obj):
            value = getattr(obj, f.name)
            # Use the camelCase version of the field name for the GraphQL key.
            # If the field has a metadata entry for graphql_name, use that.
            gql_name = f.metadata.get("graphql_name", to_camel_case(f.name))
            result[gql_name] = serialize_input(value)
        return result
    return obj
