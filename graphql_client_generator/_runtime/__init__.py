"""Runtime library for generated GraphQL clients.

This package is copied into each generated client package so that it is
fully standalone."""

from .builder import (
    BuiltQuery,
    FieldSelector,
    SchemaField,
    Variable,
    VariableRef,
)
from .client import GraphQLClientBase, GraphQLError, _ResultRoot
from .model import (
    FieldNotLoadedError,
    GraphQLModel,
    GraphQLResponse,
    GraphQLUnion,
    PathSegment,
    QueryContext,
)
from .serialization import serialize_input, to_camel_case, to_snake_case

__all__ = [
    "BuiltQuery",
    "FieldNotLoadedError",
    "FieldSelector",
    "GraphQLClientBase",
    "GraphQLError",
    "GraphQLModel",
    "GraphQLResponse",
    "GraphQLUnion",
    "PathSegment",
    "QueryContext",
    "SchemaField",
    "Variable",
    "VariableRef",
    "_ResultRoot",
    "serialize_input",
    "to_camel_case",
    "to_snake_case",
]
