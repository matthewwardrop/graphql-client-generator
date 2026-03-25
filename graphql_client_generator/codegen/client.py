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
        "from ._runtime.client import GraphQLClientBase",
    ]

    # Import the typed result classes.
    imports: list[str] = []
    if has_query:
        imports.append("QueryResult")
    if has_mutation:
        imports.append("MutationResult")
    imports.append("TYPE_REGISTRY")
    lines.append(f"from .models import {', '.join(imports)}")

    lines.extend([
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
    ])

    # query() method
    if has_query:
        query_return = "QueryResult"
        query_cls_arg = ", result_cls=QueryResult"
    else:
        query_return = "GraphQLModel"
        query_cls_arg = ""
        lines.insert(
            next(i for i, l in enumerate(lines) if "from ._runtime.client" in l) + 1,
            "from ._runtime.model import GraphQLModel",
        )

    lines.extend([
        "",
        "    def query(",
        "        self,",
        "        query: str,",
        "        variables: dict[str, Any] | None = None,",
        "        operation_name: str | None = None,",
        f"    ) -> {query_return}:",
        '        """Execute a GraphQL query and return typed result objects."""',
        f'        return self._execute(query, variables, operation_name, operation_type="query"{query_cls_arg})',
    ])

    # mutate() method
    if has_mutation:
        mutate_return = "MutationResult"
        mutate_cls_arg = ", result_cls=MutationResult"
    else:
        mutate_return = "GraphQLModel"
        mutate_cls_arg = ""
        # Ensure GraphQLModel import exists for fallback
        if not has_query:
            pass  # already inserted above
        elif not any("from ._runtime.model import GraphQLModel" in l for l in lines):
            lines.insert(
                next(i for i, l in enumerate(lines) if "from ._runtime.client" in l) + 1,
                "from ._runtime.model import GraphQLModel",
            )

    lines.extend([
        "",
        "    def mutate(",
        "        self,",
        "        mutation: str,",
        "        variables: dict[str, Any] | None = None,",
        "        operation_name: str | None = None,",
        f"    ) -> {mutate_return}:",
        '        """Execute a GraphQL mutation and return typed result objects."""',
        f'        return self._execute(mutation, variables, operation_name, operation_type="mutation"{mutate_cls_arg})',
        "",
    ])

    return "\n".join(lines)
