"""Query manipulation utilities: parsing, __typename insertion, and lazy-load
query modification."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from graphql import (
    DocumentNode,
    FieldNode,
    NameNode,
    OperationDefinitionNode,
    SelectionSetNode,
    parse as gql_parse,
    print_ast,
)

if TYPE_CHECKING:
    from .model import PathSegment

# ---------------------------------------------------------------------------
# __typename insertion
# ---------------------------------------------------------------------------

_TYPENAME_FIELD = FieldNode(name=NameNode(value="__typename"))


def ensure_typenames(query: str) -> str:
    """Return *query* with ``__typename`` inserted into every selection set
    that doesn't already have it."""
    doc = gql_parse(query)
    doc = _insert_typenames_doc(doc)
    return print_ast(doc)


def _insert_typenames_doc(doc: DocumentNode) -> DocumentNode:
    """Walk the AST and inject __typename where missing."""
    new_definitions = []
    for defn in doc.definitions:
        if isinstance(defn, OperationDefinitionNode) and defn.selection_set:
            new_ss = _insert_typenames_ss(defn.selection_set)
            defn = OperationDefinitionNode(
                operation=defn.operation,
                name=defn.name,
                variable_definitions=defn.variable_definitions,
                directives=defn.directives,
                selection_set=new_ss,
            )
        new_definitions.append(defn)
    return DocumentNode(definitions=tuple(new_definitions))


def _insert_typenames_ss(ss: SelectionSetNode) -> SelectionSetNode:
    """Recursively inject ``__typename`` into a selection set."""
    has_typename = any(
        isinstance(sel, FieldNode) and sel.name.value == "__typename"
        for sel in ss.selections
    )
    new_selections = list(ss.selections)
    if not has_typename:
        new_selections.insert(0, _TYPENAME_FIELD)

    # Recurse into child selection sets.
    processed: list[Any] = []
    for sel in new_selections:
        if isinstance(sel, FieldNode) and sel.selection_set:
            child_ss = _insert_typenames_ss(sel.selection_set)
            sel = FieldNode(
                alias=sel.alias,
                name=sel.name,
                arguments=sel.arguments,
                directives=sel.directives,
                selection_set=child_ss,
            )
        processed.append(sel)

    return SelectionSetNode(selections=tuple(processed))


# ---------------------------------------------------------------------------
# Lazy-load query modification
# ---------------------------------------------------------------------------

def add_field_to_query(
    query: str,
    path: list[PathSegment],
    field_name: str,
    sub_fields: list[str] | None = None,
) -> str:
    """Return a modified version of *query* that also selects *field_name*
    at the position described by *path*.

    For example, if the original query is::

        { book(id: 1) { title } }

    and we need ``author`` on the book, path would be
    ``[PathSegment("book", "book", ...)]`` and field_name ``"author"``.
    The result would be::

        { book(id: 1) { title author { __typename ... } } }

    If *sub_fields* is non-empty the field is composite and we add
    ``__typename`` plus those sub-fields.  Otherwise we add the bare name.
    """
    doc = gql_parse(query)
    doc = _add_field_to_doc(doc, path, field_name, sub_fields or [])
    return print_ast(doc)


def _add_field_to_doc(
    doc: DocumentNode,
    path: list[PathSegment],
    field_name: str,
    sub_fields: list[str],
) -> DocumentNode:
    new_definitions = []
    for defn in doc.definitions:
        if isinstance(defn, OperationDefinitionNode) and defn.selection_set:
            new_ss = _add_field_at_path(
                defn.selection_set, list(path), field_name, sub_fields,
            )
            defn = OperationDefinitionNode(
                operation=defn.operation,
                name=defn.name,
                variable_definitions=defn.variable_definitions,
                directives=defn.directives,
                selection_set=new_ss,
            )
        new_definitions.append(defn)
    return DocumentNode(definitions=tuple(new_definitions))


def _add_field_at_path(
    ss: SelectionSetNode,
    path: list[PathSegment],
    field_name: str,
    sub_fields: list[str],
) -> SelectionSetNode:
    """Walk the selection set along *path*, then add *field_name* to the
    deepest selection set."""
    if not path:
        return _add_field_to_selection_set(ss, field_name, sub_fields)

    segment = path[0]
    remaining = path[1:]

    new_selections: list[Any] = []
    for sel in ss.selections:
        if isinstance(sel, FieldNode):
            sel_name = sel.alias.value if sel.alias else sel.name.value
            if sel_name == segment.field_name and sel.selection_set:
                child_ss = _add_field_at_path(
                    sel.selection_set, remaining, field_name, sub_fields,
                )
                sel = FieldNode(
                    alias=sel.alias,
                    name=sel.name,
                    arguments=sel.arguments,
                    directives=sel.directives,
                    selection_set=child_ss,
                )
        new_selections.append(sel)

    return SelectionSetNode(selections=tuple(new_selections))


def _add_field_to_selection_set(
    ss: SelectionSetNode,
    field_name: str,
    sub_fields: list[str],
) -> SelectionSetNode:
    """Add *field_name* to the selection set if not already present."""
    for sel in ss.selections:
        if isinstance(sel, FieldNode) and sel.name.value == field_name:
            return ss  # already there

    if sub_fields:
        child_selections = [_TYPENAME_FIELD] + [
            FieldNode(name=NameNode(value=sf)) for sf in sub_fields
        ]
        new_field = FieldNode(
            name=NameNode(value=field_name),
            selection_set=SelectionSetNode(selections=tuple(child_selections)),
        )
    else:
        new_field = FieldNode(name=NameNode(value=field_name))

    return SelectionSetNode(selections=tuple(list(ss.selections) + [new_field]))
