"""Base model, response wrapper, and lazy-loading for generated GraphQL clients."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .builder import SchemaField
from .serialization import to_snake_case


class FieldNotLoadedError(AttributeError):
    """Raised when accessing a field that was not included in the query."""


@dataclass
class PathSegment:
    """One hop in the path from query root to a nested object."""

    field_name: str  # name as it appeared in the query (may be an alias)
    actual_name: str  # the real schema field name
    arguments: dict[str, Any] | None = None
    index: int | None = None  # position inside a list, if applicable


@dataclass
class QueryContext:
    """Carries everything needed for lazy-loading back to the server."""

    client: Any  # GraphQLClientBase (forward ref to avoid circular import)
    query_string: str  # original query text
    variables: dict[str, Any] | None = None
    operation_name: str | None = None
    path: list[PathSegment] = field(default_factory=list)
    operation_type: str = "query"  # "query" or "mutation"


class GraphQLModel:
    """Base class for generated GraphQL schema types.

    Subclasses declare fields via :class:`SchemaField` descriptors.
    These classes serve as schema metadata and query-builder namespaces;
    response data is wrapped in :class:`GraphQLResponse` instead.
    """

    __typename__: str = ""
    __type_registry__: dict[str, type[GraphQLModel]] = {}


# ---------------------------------------------------------------------------
# GraphQLResponse -- dynamic wrapper for response data
# ---------------------------------------------------------------------------

class GraphQLResponse:
    """Dynamic wrapper around a GraphQL response object.

    Attributes come directly from the response data (including aliases).
    The associated *model_cls* is used only for type resolution, repr,
    and lazy loading of unqueried fields.
    """

    def __init__(
        self,
        data: dict[str, Any],
        model_cls: type[GraphQLModel] | None,
        context: QueryContext | None = None,
        type_registry: dict[str, type[GraphQLModel]] | None = None,
    ) -> None:
        self.__dict__["_data"] = data
        self.__dict__["_model_cls"] = model_cls
        self.__dict__["_context"] = context
        self.__dict__["_type_registry"] = type_registry or {}

        # Eagerly coerce all response fields into attributes.
        # Store under snake_case keys for Pythonic access.
        for key, raw in data.items():
            if key != "__typename":
                py_key = to_snake_case(key)
                self.__dict__[py_key] = _coerce_response_value(
                    raw, self._type_registry, context, key,
                )

    def __getattr__(self, name: str) -> Any:
        # Field not in response data -> try lazy loading via model_cls.
        if name.startswith("_"):
            raise AttributeError(name)
        desc = _find_descriptor(self._model_cls, name)
        if desc is not None:
            ctx = self._context
            if ctx is not None and ctx.client is not None and ctx.client.auto_fetch:
                value = _lazy_load_response_field(self, desc)
                self.__dict__[name] = value
                return value
        raise FieldNotLoadedError(
            f"Field '{name}' was not included in the query"
        )

    # -- serialization ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize loaded fields to a plain dict."""
        return {k: _serialize_value(v) for k, v in self._data.items()}

    def to_json(self, **kwargs: Any) -> str:
        """Serialize loaded fields to a JSON string."""
        return json.dumps(self.to_dict(), **kwargs)

    # -- dunder ----------------------------------------------------------------

    def __repr__(self) -> str:
        return _format_response(self, indent=0)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GraphQLResponse):
            return NotImplemented
        return self._model_cls is other._model_cls and self._data == other._data

    def __hash__(self) -> int:
        return id(self)


# ---------------------------------------------------------------------------
# Response coercion helpers
# ---------------------------------------------------------------------------

def _coerce_response_value(
    raw: Any,
    type_registry: dict[str, type[GraphQLModel]],
    context: QueryContext | None,
    key: str,
) -> Any:
    """Coerce a raw JSON value into a ``GraphQLResponse`` or scalar."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        typename = raw.get("__typename")
        model_cls = type_registry.get(typename) if typename else None
        child_context = _child_context(context, key) if context else None
        return GraphQLResponse(raw, model_cls, child_context, type_registry)
    if isinstance(raw, list):
        return [
            _coerce_response_value(item, type_registry, context, key)
            for item in raw
        ]
    return raw


def _child_context(
    parent_ctx: QueryContext,
    key: str,
    index: int | None = None,
) -> QueryContext:
    """Build a child ``QueryContext`` one level deeper."""
    child_path = list(parent_ctx.path) + [
        PathSegment(field_name=key, actual_name=key, index=index)
    ]
    return QueryContext(
        client=parent_ctx.client,
        query_string=parent_ctx.query_string,
        variables=parent_ctx.variables,
        operation_name=parent_ctx.operation_name,
        path=child_path,
        operation_type=parent_ctx.operation_type,
    )


# ---------------------------------------------------------------------------
# Lazy loading helpers (for GraphQLResponse)
# ---------------------------------------------------------------------------

def _find_descriptor(
    model_cls: type[GraphQLModel] | None,
    attr_name: str,
) -> SchemaField | None:
    """Find a ``SchemaField`` descriptor on *model_cls* matching *attr_name*."""
    if model_cls is None:
        return None
    for klass in model_cls.__mro__:
        desc = klass.__dict__.get(attr_name)
        if isinstance(desc, SchemaField):
            return desc
    return None


def _resolve_subfields_for(
    desc: SchemaField,
    type_registry: dict[str, type[GraphQLModel]],
) -> list[str]:
    """Resolve scalar sub-field names for the target type of *desc*."""
    target_type = _unwrap_type_name(desc.graphql_type)
    target_cls = type_registry.get(target_type)
    if target_cls is None:
        return []  # scalar type
    result: list[str] = []
    for klass in target_cls.__mro__:
        for val in klass.__dict__.values():
            if isinstance(val, SchemaField):
                inner = _unwrap_type_name(val.graphql_type)
                if type_registry.get(inner) is None:
                    result.append(val.graphql_name)
    return result


def _lazy_load_response_field(
    obj: GraphQLResponse,
    desc: SchemaField,
) -> Any:
    """Lazy-load a field on a ``GraphQLResponse`` using descriptor metadata."""
    from .query import add_field_to_query

    ctx = obj._context
    if ctx is None or ctx.client is None:
        raise FieldNotLoadedError(
            f"Cannot lazy-load '{desc.attr_name}': no client context available"
        )

    sub_fields = _resolve_subfields_for(desc, obj._type_registry)

    new_query = add_field_to_query(
        ctx.query_string,
        ctx.path,
        desc.graphql_name,
        sub_fields,
    )

    response_data = ctx.client._execute_raw(
        new_query,
        variables=ctx.variables,
        operation_name=ctx.operation_name,
    )

    # Walk the response along our path to find the relevant sub-object.
    current: Any = response_data
    for segment in ctx.path:
        if current is None:
            break
        if isinstance(current, dict):
            current = current.get(segment.field_name)
        if segment.index is not None and isinstance(current, list):
            current = current[segment.index] if segment.index < len(current) else None

    if current is None or not isinstance(current, dict):
        return None

    raw_value = current.get(desc.graphql_name)
    obj._data[desc.graphql_name] = raw_value
    return _coerce_response_value(raw_value, obj._type_registry, ctx, desc.graphql_name)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _unwrap_type_name(graphql_type: str) -> str:
    """Extract the base type name from a GraphQL type string like ``[Foo!]!``."""
    return graphql_type.replace("!", "").replace("[", "").replace("]", "").strip()


def _serialize_value(value: Any) -> Any:
    """Recursively serialize a value for to_dict()."""
    if isinstance(value, GraphQLResponse):
        return value.to_dict()
    if isinstance(value, GraphQLModel):
        return {k: _serialize_value(v) for k, v in value.__dict__.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


# -- repr helpers ----------------------------------------------------------

def _format_response(obj: GraphQLResponse, indent: int) -> str:
    """Format a GraphQLResponse with its model type name."""
    name = obj._model_cls.__name__ if obj._model_cls else "GraphQLResponse"
    # Use coerced values from __dict__ with snake_case keys.
    items = []
    for k in obj._data:
        if k == "__typename":
            continue
        py_key = to_snake_case(k)
        val = obj.__dict__.get(py_key)
        if val is not None:
            items.append((py_key, val))
    if not items:
        return f"{name}()"

    # Try compact (single-line) first.
    compact_parts = [
        f"{k}={_repr_value(v, 0)}" for k, v in items
    ]
    compact = f"{name}({', '.join(compact_parts)})"
    if len(compact) <= 80:
        return compact

    # Multi-line with indentation.
    child_indent = indent + 4
    pad = " " * child_indent
    lines = [f"{name}("]
    for k, v in items:
        val_str = _repr_value(v, child_indent)
        lines.append(f"{pad}{k}={val_str},")
    lines.append(" " * indent + ")")
    return "\n".join(lines)


def _repr_value(value: Any, indent: int) -> str:
    """Format a single value for repr."""
    if value is None:
        return "None"
    if isinstance(value, GraphQLResponse):
        return _format_response(value, indent)
    if isinstance(value, list):
        if not value:
            return "[]"
        parts = [_repr_value(item, indent + 4) for item in value]
        compact = f"[{', '.join(parts)}]"
        if len(compact) <= 80:
            return compact
        pad = " " * (indent + 4)
        inner = ",\n".join(f"{pad}{p}" for p in parts)
        return f"[\n{inner},\n{' ' * indent}]"
    return repr(value)
