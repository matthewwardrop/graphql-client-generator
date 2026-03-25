"""Base model and descriptor for generated GraphQL client types."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T", bound="GraphQLModel")

_SENTINEL = object()


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
    schema_info: Any = None  # SchemaInfo for the generated package


class graphql_field:
    """Descriptor that provides typed access to GraphQL response data.

    Usage in generated code::

        class Test(GraphQLModel):
            id: int = graphql_field("id", graphql_type="Int!")

    Behaviour:
    - If the field was populated in the query response, returns the coerced value.
    - If not populated and *auto_fetch* is enabled on the client, triggers a
      lazy fetch and caches the result.
    - Otherwise raises ``FieldNotLoadedError``.
    """

    def __init__(self, graphql_name: str, graphql_type: str = "") -> None:
        self.graphql_name = graphql_name
        self.graphql_type = graphql_type
        self.attr_name: str | None = None

    # -- descriptor protocol ---------------------------------------------------

    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = name

    def __get__(self, obj: GraphQLModel | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self  # class-level access returns the descriptor itself

        # Fast path: value already resolved and cached in instance dict.
        cached = obj.__dict__.get(self.attr_name, _SENTINEL)
        if cached is not _SENTINEL:
            return cached

        # Check raw response data.
        raw = obj._data.get(self.graphql_name, _SENTINEL)
        if raw is not _SENTINEL:
            value = obj._coerce_value(self.attr_name, self.graphql_name, raw)
            obj.__dict__[self.attr_name] = value
            return value

        # Not in data -- try lazy loading.
        ctx = obj._context
        if ctx is not None and ctx.client is not None and ctx.client.auto_fetch:
            value = obj._lazy_load_field(self.graphql_name, self.attr_name)
            obj.__dict__[self.attr_name] = value
            return value

        raise FieldNotLoadedError(
            f"Field '{self.attr_name}' (GraphQL: '{self.graphql_name}') was not "
            f"included in the query and auto_fetch is disabled"
        )

    def __set__(self, obj: GraphQLModel, value: Any) -> None:
        obj.__dict__[self.attr_name] = value

    def __repr__(self) -> str:
        return f"graphql_field({self.graphql_name!r}, graphql_type={self.graphql_type!r})"


class GraphQLModel:
    """Base class for all generated GraphQL result types.

    Subclasses declare fields via :class:`graphql_field` descriptors and set
    ``__typename__`` to the corresponding GraphQL type name.
    """

    __typename__: str = ""

    # Populated by generated code: maps GraphQL field name -> (python_attr, type_info)
    __field_map__: dict[str, str] = {}  # graphql_name -> attr_name
    __type_registry__: dict[str, type[GraphQLModel]] = {}  # typename -> class

    def __init__(self, _data: dict[str, Any], _context: QueryContext | None = None) -> None:
        self._data = _data
        self._context = _context

    # -- coercion --------------------------------------------------------------

    def _coerce_value(self, attr_name: str, graphql_name: str, raw: Any) -> Any:
        """Coerce a raw JSON value into the appropriate Python type.

        The base implementation handles:
        - None (pass through)
        - dicts with ``__typename`` -> look up concrete model class
        - lists -> recurse
        - scalars -> pass through

        Generated subclasses may override for tighter typing.
        """
        if raw is None:
            return None
        if isinstance(raw, dict):
            return self._coerce_object(raw)
        if isinstance(raw, list):
            return [self._coerce_value(attr_name, graphql_name, item) for item in raw]
        return raw

    def _coerce_object(self, data: dict[str, Any]) -> GraphQLModel:
        """Turn a raw dict into the right ``GraphQLModel`` subclass."""
        typename = data.get("__typename")
        cls = self.__type_registry__.get(typename) if typename else None
        if cls is None:
            # Fallback: return a generic GraphQLModel
            cls = GraphQLModel
        child_context = None
        if self._context is not None:
            child_context = QueryContext(
                client=self._context.client,
                query_string=self._context.query_string,
                variables=self._context.variables,
                operation_name=self._context.operation_name,
                path=list(self._context.path),  # will be extended by caller if needed
                operation_type=self._context.operation_type,
                schema_info=self._context.schema_info,
            )
        return cls(data, child_context)

    # -- lazy loading ----------------------------------------------------------

    def _lazy_load_field(self, graphql_name: str, attr_name: str) -> Any:
        """Fetch a missing field by modifying the original query and re-executing."""
        from .query import add_field_to_query

        ctx = self._context
        if ctx is None or ctx.client is None:
            raise FieldNotLoadedError(
                f"Cannot lazy-load '{attr_name}': no client context available"
            )

        new_query = add_field_to_query(
            ctx.query_string,
            ctx.path,
            graphql_name,
            ctx.schema_info,
        )

        response_data = ctx.client._execute_raw(
            new_query,
            variables=ctx.variables,
            operation_name=ctx.operation_name,
        )

        # Walk the response along our path to find the relevant sub-object.
        current = response_data
        for segment in ctx.path:
            if current is None:
                break
            if isinstance(current, dict):
                current = current.get(segment.field_name)
            if segment.index is not None and isinstance(current, list):
                current = current[segment.index] if segment.index < len(current) else None

        if current is None or not isinstance(current, dict):
            return None

        raw_value = current.get(graphql_name)
        # Cache in _data so the next descriptor access hits the fast path.
        self._data[graphql_name] = raw_value
        return self._coerce_value(attr_name, graphql_name, raw_value)

    # -- serialization ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize loaded fields to a plain dict (camelCase keys)."""
        result: dict[str, Any] = {}
        for graphql_name, raw in self._data.items():
            result[graphql_name] = _serialize_value(raw)
        return result

    def to_json(self, **kwargs: Any) -> str:
        """Serialize loaded fields to a JSON string."""
        return json.dumps(self.to_dict(), **kwargs)

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        """Construct a model from a plain dict (no client context)."""
        return cls(data)

    @classmethod
    def from_json(cls: type[T], json_str: str) -> T:
        """Construct a model from a JSON string (no client context)."""
        return cls(json.loads(json_str))

    @classmethod
    def _from_response(cls: type[T], data: dict[str, Any], context: QueryContext) -> T:
        """Construct a model from a server response dict with client context."""
        return cls(data, context)

    # -- dunder ----------------------------------------------------------------

    def __repr__(self) -> str:
        loaded = {k: v for k, v in self._data.items() if v is not None}
        fields_str = ", ".join(f"{k}={v!r}" for k, v in list(loaded.items())[:5])
        name = type(self).__name__
        if len(loaded) > 5:
            fields_str += ", ..."
        return f"{name}({fields_str})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GraphQLModel):
            return NotImplemented
        return type(self) is type(other) and self._data == other._data

    def __hash__(self) -> int:
        return id(self)


def _serialize_value(value: Any) -> Any:
    """Recursively serialize a value for to_dict()."""
    if isinstance(value, GraphQLModel):
        return value.to_dict()
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value
