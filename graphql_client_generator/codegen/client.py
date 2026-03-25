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
        "from ._runtime.builder import BuiltQuery, FieldSelector, build_query_string",
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
    query_return = "QueryResult" if has_query else "_ResultRoot"
    query_cls_arg = ", result_cls=QueryResult" if has_query else ""

    lines.extend([
        "",
        "    def query(",
        "        self,",
        "        *args: str | BuiltQuery | FieldSelector,",
        "        variables: dict[str, Any] | None = None,",
        "        operation_name: str | None = None,",
        "        **aliases: FieldSelector,",
        f"    ) -> {query_return}:",
        '        """Execute a GraphQL query and return typed result objects.',
        "",
        "        Accepts a raw GraphQL string, a ``BuiltQuery``, or one or more",
        "        ``FieldSelector`` objects (with optional keyword aliases).",
        '        """',
        '        query_str = _resolve_query(args, aliases, "query")',
        f'        return self._execute(query_str, variables, operation_name, operation_type="query"{query_cls_arg})',
    ])

    # mutate() method
    mutate_return = "MutationResult" if has_mutation else "_ResultRoot"
    mutate_cls_arg = ", result_cls=MutationResult" if has_mutation else ""

    lines.extend([
        "",
        "    def mutate(",
        "        self,",
        "        *args: str | BuiltQuery | FieldSelector,",
        "        variables: dict[str, Any] | None = None,",
        "        operation_name: str | None = None,",
        "        **aliases: FieldSelector,",
        f"    ) -> {mutate_return}:",
        '        """Execute a GraphQL mutation and return typed result objects."""',
        '        query_str = _resolve_query(args, aliases, "mutation")',
        f'        return self._execute(query_str, variables, operation_name, operation_type="mutation"{mutate_cls_arg})',
        "",
        "",
        "def _resolve_query(",
        "    args: tuple[str | BuiltQuery | FieldSelector, ...],",
        "    aliases: dict[str, FieldSelector],",
        "    operation_type: str,",
        ") -> str:",
        '    """Convert flexible query arguments into a GraphQL query string."""',
        "    if len(args) == 1 and isinstance(args[0], str):",
        "        return args[0]",
        "    if len(args) == 1 and isinstance(args[0], BuiltQuery):",
        "        return args[0].to_graphql()",
        "    # FieldSelector args (possibly with keyword aliases)",
        "    selections = [a for a in args if isinstance(a, FieldSelector)]",
        "    return build_query_string(selections, aliases, operation_type)",
        "",
    ])

    return "\n".join(lines)
