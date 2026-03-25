"""Runtime library for generated GraphQL clients.

This package is copied into each generated client package so that it is
fully standalone."""

from .client import GraphQLClientBase, GraphQLError, _ResultRoot
from .model import (
    FieldNotLoadedError,
    GraphQLModel,
    PathSegment,
    QueryContext,
    graphql_field,
)
from .serialization import serialize_input, to_camel_case, to_snake_case

__all__ = [
    "GraphQLModel",
    "QueryContext",
    "PathSegment",
    "FieldNotLoadedError",
    "graphql_field",
    "GraphQLClientBase",
    "GraphQLError",
    "serialize_input",
    "to_camel_case",
    "to_snake_case",
    "_ResultRoot",
]
