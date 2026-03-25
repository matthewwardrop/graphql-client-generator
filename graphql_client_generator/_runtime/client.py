"""Base GraphQL client that handles HTTP transport, query execution, and
response-to-model conversion."""

from __future__ import annotations

from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

from .model import GraphQLModel, PathSegment, QueryContext
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
    ) -> GraphQLModel:
        """Execute a GraphQL **query** and return a typed result tree."""
        return self._execute(query, variables, operation_name, operation_type="query")

    def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> GraphQLModel:
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
    ) -> GraphQLModel:
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
    ) -> GraphQLModel:
        """Convert raw response data into a tree of ``GraphQLModel`` instances."""
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


class _ResultRoot(GraphQLModel):
    """Wrapper around the top-level ``data`` dict returned by a GraphQL
    operation.  Each top-level key becomes an attribute."""

    def __init__(
        self,
        data: dict[str, Any],
        context: QueryContext,
        type_registry: dict[str, type[GraphQLModel]],
    ) -> None:
        super().__init__(data, context)
        self._type_registry_local = type_registry

    def __getattr__(self, name: str) -> Any:
        # Allow accessing top-level response fields by name.
        # Try camelCase first (GraphQL convention), then the name as-is.
        for key in (name, _to_camel_case(name)):
            if key in self._data:
                raw = self._data[key]
                value = self._coerce_top_level(key, raw)
                # Cache for future access.
                self.__dict__[name] = value
                return value
        raise AttributeError(f"No field '{name}' in query result")

    def _coerce_top_level(self, key: str, raw: Any) -> Any:
        """Coerce a top-level response value, attaching path context."""
        if raw is None:
            return None
        if isinstance(raw, dict):
            return self._coerce_object_with_path(key, raw)
        if isinstance(raw, list):
            return [
                self._coerce_object_with_path(key, item, index=i)
                if isinstance(item, dict) else item
                for i, item in enumerate(raw)
            ]
        return raw

    def _coerce_object_with_path(
        self, key: str, data: dict[str, Any], index: int | None = None,
    ) -> GraphQLModel:
        """Construct a child model with correct path context."""
        typename = data.get("__typename")
        cls = self._type_registry_local.get(typename, GraphQLModel) if typename else GraphQLModel

        child_path = list(self._context.path) + [
            PathSegment(field_name=key, actual_name=key, index=index)
        ]
        child_context = QueryContext(
            client=self._context.client,
            query_string=self._context.query_string,
            variables=self._context.variables,
            operation_name=self._context.operation_name,
            path=child_path,
            operation_type=self._context.operation_type,
        )
        obj = cls(data, child_context)
        # Give the child access to the type registry for nested coercion.
        obj.__type_registry__ = self._type_registry_local
        return obj

    def to_dict(self) -> dict[str, Any]:
        return {k: _serialize(v) for k, v in self._data.items()}


def _serialize(value: Any) -> Any:
    if isinstance(value, GraphQLModel):
        return value.to_dict()
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def _to_camel_case(snake: str) -> str:
    """Convert snake_case to camelCase."""
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])
