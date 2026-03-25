"""Base GraphQL client that handles HTTP transport, query execution, and
response-to-model conversion."""

from __future__ import annotations

from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

from .model import (
    GraphQLModel,
    GraphQLResponse,
    QueryContext,
    _coerce_response_value,
    _format_response,
    _serialize_value,
)
from .query import ensure_typenames


class GraphQLError(Exception):
    """Raised when the GraphQL server returns errors in the response."""

    def __init__(self, errors: list[dict[str, Any]], data: Any = None) -> None:
        self.errors = errors
        self.data = data
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        super().__init__(f"GraphQL errors: {messages}")


class GraphQLClientBase:
    """Base client extended by each generated ``{Service}Client``."""

    # Populated by generated subclasses with the package's type registry.
    _type_registry: dict[str, type[GraphQLModel]] = {}

    def __init__(
        self,
        endpoint: str,
        session: requests.Session | None = None,
        auto_fetch: bool = True,
    ) -> None:
        self.endpoint = endpoint
        self.session = session or requests.Session()
        self.auto_fetch = auto_fetch

    # -- public API ------------------------------------------------------------

    def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> _ResultRoot:
        """Execute a GraphQL **query** and return a typed result tree."""
        return self._execute(query, variables, operation_name, operation_type="query")

    def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> _ResultRoot:
        """Execute a GraphQL **mutation** and return a typed result tree."""
        return self._execute(mutation, variables, operation_name, operation_type="mutation")

    # -- internals -------------------------------------------------------------

    def _execute(
        self,
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
        operation_type: str,
        result_cls: type[_ResultRoot] | None = None,
    ) -> _ResultRoot:
        """Parse, enhance, execute, and convert a GraphQL operation."""
        enhanced_query = ensure_typenames(query)
        data = self._execute_raw(enhanced_query, variables, operation_name)
        return self._build_result_tree(
            data, enhanced_query, variables, operation_name, operation_type,
            result_cls=result_cls,
        )

    def _execute_raw(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """Send the query over HTTP and return the ``data`` portion of the
        response.  Raises :class:`GraphQLError` if errors are present."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        resp = self.session.post(self.endpoint, json=payload)
        resp.raise_for_status()
        body = resp.json()

        if "errors" in body:
            raise GraphQLError(body["errors"], body.get("data"))

        return body.get("data", {})

    def _build_result_tree(
        self,
        data: dict[str, Any],
        query_string: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
        operation_type: str,
        result_cls: type[_ResultRoot] | None = None,
    ) -> _ResultRoot:
        """Convert raw response data into a tree of result objects."""
        root_context = QueryContext(
            client=self,
            query_string=query_string,
            variables=variables,
            operation_name=operation_name,
            path=[],
            operation_type=operation_type,
        )
        cls = result_cls or _ResultRoot
        return cls(data, root_context, self._type_registry)


class _ResultRoot:
    """Wrapper around the top-level ``data`` dict returned by a GraphQL
    operation.  Each top-level key becomes an attribute that returns a
    ``GraphQLResponse``."""

    def __init__(
        self,
        data: dict[str, Any],
        context: QueryContext,
        type_registry: dict[str, type[GraphQLModel]],
    ) -> None:
        self._data = data
        self._context = context
        self._type_registry = type_registry

        # Eagerly coerce all top-level fields.
        for key, raw in data.items():
            self.__dict__[key] = _coerce_response_value(
                raw, type_registry, context, key,
            )

    def __getattr__(self, name: str) -> Any:
        # Try camelCase conversion for snake_case attribute access.
        camel = _to_camel_case(name)
        if camel in self.__dict__:
            return self.__dict__[camel]
        raise AttributeError(f"No field '{name}' in query result")

    def __repr__(self) -> str:
        # Use coerced values from __dict__.
        items = [
            (k, self.__dict__[k]) for k in self._data
            if k in self.__dict__ and self.__dict__[k] is not None
        ]
        if not items:
            return "QueryResult()"
        compact_parts = [f"{k}={_repr_top(v)}" for k, v in items]
        compact = f"QueryResult({', '.join(compact_parts)})"
        if len(compact) <= 80:
            return compact
        pad = "    "
        lines = ["QueryResult("]
        for k, v in items:
            lines.append(f"{pad}{k}={_repr_top(v)},")
        lines.append(")")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {k: _serialize_value(v) for k, v in self._data.items()}


def _repr_top(value: Any) -> str:
    """Repr a top-level value in a _ResultRoot."""
    if isinstance(value, GraphQLResponse):
        return _format_response(value, indent=4)
    if isinstance(value, list):
        parts = [_repr_top(v) for v in value]
        return f"[{', '.join(parts)}]"
    return repr(value)


def _to_camel_case(snake: str) -> str:
    """Convert snake_case to camelCase."""
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])
