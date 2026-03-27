"""Generate the service-specific client class."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..parser import SchemaInfo


def generate_client(schema: SchemaInfo, client_class_name: str) -> str:
    """Return the contents of ``client.py`` for the generated package."""
    has_query = schema.query_type is not None
    has_mutation = schema.mutation_type is not None

    lines = [
        '"""Generated GraphQL client."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "import requests",
        "",
        "from ._runtime.builder import BuiltQuery, FieldSelector",
        "from ._runtime.client import GraphQLClientBase",
    ]

    # Import the typed result classes.
    imports: list[str] = []
    if has_query:
        imports.append("QueryResult")
    if has_mutation:
        imports.append("MutationResult")
    imports.append("TYPE_REGISTRY")
    lines.append(f"from .outputs import {', '.join(imports)}")

    lines.extend(
        [
            "",
            "",
            f"class {client_class_name}(GraphQLClientBase):",
            '    """GraphQL client for this service."""',
            "",
            "    def __init__(",
            "        self,",
            "        endpoint: str,",
            "        session: requests.Session | None = None,",
            "        auto_fetch: bool = True,",
            "    ) -> None:",
            "        super().__init__(",
            "            endpoint=endpoint,",
            "            session=session or requests.Session(),",
            "            auto_fetch=auto_fetch,",
            "        )",
            "        self._type_registry = TYPE_REGISTRY",
        ]
    )

    # query() method
    if has_query:
        lines.extend(
            [
                "",
                "    def query(",
                "        self,",
                "        *args: str | BuiltQuery | FieldSelector,",
                "        variables: dict[str, Any] | None = None,",
                "        operation_name: str | None = None,",
                "    ) -> QueryResult:",
                '        """Execute a GraphQL query and return typed result objects."""',
                "        return self._execute(",
                "            *args, variables=variables, operation_name=operation_name,",
                '            operation_type="query", result_cls=QueryResult,',
                "        )",
            ]
        )

    # mutate() method (only when the schema defines mutations)
    if has_mutation:
        lines.extend(
            [
                "",
                "    def mutate(",
                "        self,",
                "        *args: str | BuiltQuery | FieldSelector,",
                "        variables: dict[str, Any] | None = None,",
                "        operation_name: str | None = None,",
                "    ) -> MutationResult:",
                '        """Execute a GraphQL mutation and return typed result objects."""',
                "        return self._execute(",
                "            *args, variables=variables, operation_name=operation_name,",
                '            operation_type="mutation", result_cls=MutationResult,',
                "        )",
            ]
        )

    lines.append("")

    return "\n".join(lines)
