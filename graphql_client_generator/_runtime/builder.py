"""Query builder: typed, tab-completable GraphQL query construction."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Callable

    from .model import GraphQLUnion

# ---------------------------------------------------------------------------
# Variable placeholders
# ---------------------------------------------------------------------------


class _VariableNamespace:
    """Singleton namespace for query variable placeholders.

    Access any attribute to create a :class:`VariableRef`::

        Variable.user_id  # -> VariableRef("user_id")
    """

    def __getattr__(self, name: str) -> VariableRef:
        if name.startswith("_"):
            raise AttributeError(name)
        return VariableRef(name)

    def __repr__(self) -> str:
        return "Variable"


Variable = _VariableNamespace()


class VariableRef:
    """A reference to a named query variable (``$name``)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"${self.name}"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, VariableRef) and self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)


# ---------------------------------------------------------------------------
# FieldSelector
# ---------------------------------------------------------------------------


class FieldSelector:
    """A field selection in a GraphQL query.

    Created by accessing attributes on schema classes.  Supports:

    - ``selector(arg=val)`` to set field arguments
    - ``selector[field1, field2]`` to set sub-field selections
    - ``selector.as_("alias")`` to set an alias
    - ``selector.child_field`` to chain into child fields (tab-completable)
    """

    def __init__(
        self,
        graphql_name: str,
        target_cls: Any = None,
        arg_types: dict[str, str] | None = None,
        arg_doc: str = "",
        input_arg: str | None = None,
        input_cls: Any = None,
        source_type: type | None = None,
    ) -> None:
        self._graphql_name = graphql_name
        self._target_cls = target_cls
        self._arg_types = arg_types or {}
        self._arg_doc = arg_doc
        self._input_arg = input_arg
        self._input_cls = input_cls
        self._source_type = source_type
        self._parent: FieldSelector | None = None
        self._args: dict[str, Any] = {}
        self._sub_selections: list[FieldSelector] = []
        self._alias: str | None = None
        self._expansion_mode: str | None = None

        # Build a proper __signature__ so notebooks show typed parameters.
        if self._arg_types:
            params = [
                inspect.Parameter(
                    name,
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=gql_type,
                )
                for name, gql_type in self._arg_types.items()
            ]
            self.__signature__ = inspect.Signature(
                params,
                return_annotation=FieldSelector,
            )
            arg_sig = ", ".join(f"{n}: {t}" for n, t in self._arg_types.items())
            self.__doc__ = f"{graphql_name}({arg_sig})"

    def _clone(self) -> FieldSelector:
        node = FieldSelector(
            self._graphql_name,
            self._target_cls,
            self._arg_types,
            self._arg_doc,
            self._input_arg,
            self._input_cls,
            source_type=self._source_type,
        )
        node._parent = self._parent
        node._args = dict(self._args)
        node._sub_selections = list(self._sub_selections)
        node._alias = self._alias
        node._expansion_mode = self._expansion_mode
        return node

    # -- arguments via __call__ ------------------------------------------------

    def __call__(self, **kwargs: Any) -> FieldSelector:
        """Set field arguments.

        When the field has a detected input type, keyword arguments are
        forwarded to the Input class constructor for validation, then
        stored as a single GraphQL argument.

        Raises ``TypeError`` if the field accepts no arguments or if an
        unknown argument name is provided.
        """
        if not self._arg_types:
            raise TypeError(f"Field '{self._graphql_name}' takes no arguments")
        for key in kwargs:
            if key not in self._arg_types:
                raise TypeError(
                    f"Unknown argument '{key}' for field "
                    f"'{self._graphql_name}'. "
                    f"Valid arguments: {', '.join(self._arg_types)}"
                )
        # Check that all required arguments (non-null types ending with !)
        # are provided.
        missing = [
            name
            for name, gql_type in self._arg_types.items()
            if gql_type.endswith("!") and name not in kwargs
        ]
        if missing:
            raise TypeError(
                f"Missing required argument(s) for field "
                f"'{self._graphql_name}': {', '.join(missing)}"
            )
        node = self._clone()
        if self._input_arg and self._input_cls:
            # Flatten mode: forward kwargs to Input constructor, wrap result.
            input_obj = self._input_cls(**kwargs)
            node._args = {self._input_arg: input_obj}
        else:
            node._args = dict(kwargs)
        return node

    # -- sub-selections via __getitem__ ----------------------------------------

    def __getitem__(
        self,
        selections: (
            FieldSelector
            | tuple[FieldSelector, ...]
            | list[FieldSelector]
            | Callable[[FieldSelector], Any]
        ),
    ) -> FieldSelector:
        """Set sub-field selections.

        Accepts a single ``FieldSelector``, a tuple/list of them, any
        iterable yielding them, or a **callable** (lambda shorthand)
        that receives ``self`` and returns selections::

            Query.user[lambda u: (u.name, u.address.street)]

        Deep dotted paths are automatically flattened into nested
        sub-selections.  Paths are validated against the receiver.

        Raises ``TypeError`` if required arguments have not been provided
        via ``__call__`` first, or if a selection path does not match.
        """
        # Validate required args before allowing sub-selections.
        if self._input_arg:
            if self._input_arg not in self._args:
                raise TypeError(
                    f"Missing required argument(s) for field "
                    f"'{self._graphql_name}'. "
                    f"Call the field with arguments before selecting sub-fields."
                )
        else:
            missing = [
                name
                for name, gql_type in self._arg_types.items()
                if gql_type.endswith("!") and name not in self._args
            ]
            if missing:
                raise TypeError(
                    f"Missing required argument(s) for field "
                    f"'{self._graphql_name}': {', '.join(missing)}. "
                    f"Call the field with arguments before selecting sub-fields."
                )

        # Normalize input to a flat list.
        raw: list[FieldSelector]
        if callable(selections) and not isinstance(selections, FieldSelector):
            result = selections(self)
            raw = [result] if isinstance(result, FieldSelector) else list(result)
        elif isinstance(selections, FieldSelector):
            raw = [selections]
        else:
            raw = list(selections)

        normalized = _flatten_selections(self, raw)
        node = self._clone()
        node._sub_selections = normalized
        return node

    # -- aliasing via .as_() ---------------------------------------------------

    def as_(self, alias: str) -> FieldSelector:
        """Set an alias for this field.  Can be called before or after ``[]``."""
        node = self._clone()
        node._alias = alias
        return node

    # -- child field access (tab completion) -----------------------------------

    def __getattr__(self, name: str) -> FieldSelector | _InlineFragmentProxy:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in _EXPANSION_MODES:
            if self._target_cls is None:
                raise AttributeError(f"Cannot use .{name} on scalar field '{self._graphql_name}'")
            node = self._clone()
            node._expansion_mode = name
            return node
        target = self._resolve_target()
        if target is not None:
            if _is_union(target):
                for member in target.__member_types__():
                    if member.__name__ == name:
                        return _InlineFragmentProxy(member)
                member_names = ", ".join(m.__name__ for m in target.__member_types__())
                raise AttributeError(
                    f"Field '{self._graphql_name}' is a union type "
                    f"({target.__name__}). "
                    f"Select a member type first: {member_names}"
                )
            for klass in target.__mro__:
                desc = klass.__dict__.get(name)
                if isinstance(desc, SchemaField):
                    child = desc._make_selector()
                    child._parent = self
                    return child
        raise AttributeError(f"No field '{name}' on '{self._graphql_name}'")

    def _resolve_target(self) -> type | None:
        if self._target_cls is None:
            return None
        if isinstance(self._target_cls, type):
            return self._target_cls
        return self._target_cls()  # type: ignore[no-any-return]

    # -- introspection ---------------------------------------------------------

    def __dir__(self) -> list[str]:
        attrs = ["as_"]
        if self._arg_types:
            attrs.append("__call__")
        target = self._resolve_target()
        if target is not None:
            attrs.extend(_EXPANSION_MODES)
            if _is_union(target):
                for member in target.__member_types__():
                    attrs.append(member.__name__)
            else:
                for klass in target.__mro__:
                    for attr_name, val in klass.__dict__.items():
                        if isinstance(val, SchemaField) and not attr_name.startswith("_"):
                            attrs.append(attr_name)
        return attrs

    def __repr__(self) -> str:
        return to_graphql(self)


# ---------------------------------------------------------------------------
# SchemaField descriptor
# ---------------------------------------------------------------------------


class SchemaField:
    """Descriptor on generated schema classes.

    Accessing on the class returns a :class:`FieldSelector` for query
    building.  Also carries type metadata used by ``GraphQLResponse``
    for lazy loading.
    """

    def __init__(
        self,
        graphql_name: str,
        graphql_type: str = "",
        target_cls: Any = None,
        arg_types: dict[str, str] | None = None,
        doc: str = "",
        input_arg: str | None = None,
        input_cls: Any = None,
    ) -> None:
        self.graphql_name = graphql_name
        self.graphql_type = graphql_type
        self.attr_name: str | None = None
        self._target_cls = target_cls
        self._arg_types = arg_types or {}
        self._doc = doc
        self._input_arg = input_arg
        self._input_cls = input_cls

    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = name

    def __get__(self, obj: Any, objtype: type | None = None) -> FieldSelector:
        return self._make_selector(source_type=objtype)

    def _make_selector(self, source_type: type | None = None) -> FieldSelector:
        return FieldSelector(
            self.graphql_name,
            target_cls=self._target_cls,
            arg_types=self._arg_types,
            arg_doc=self._doc,
            input_arg=self._input_arg,
            input_cls=self._input_cls,
            source_type=source_type,
        )

    def __repr__(self) -> str:
        return f"SchemaField({self.graphql_name!r})"


# ---------------------------------------------------------------------------
# Union helpers
# ---------------------------------------------------------------------------


def _is_union(target: type | None) -> TypeGuard[type[GraphQLUnion]]:
    """Return True if *target* is a ``GraphQLUnion`` subclass."""
    from .model import GraphQLUnion

    return (
        target is not None
        and isinstance(target, type)
        and issubclass(target, GraphQLUnion)
        and target is not GraphQLUnion
    )


class _InlineFragmentProxy:
    """Proxy exposing fields of a specific union member type.

    Created when accessing a member type name on a union-typed
    ``FieldSelector`` (e.g. ``Query.search.User``).  Attribute access
    on the proxy returns ``FieldSelector`` instances tagged with
    ``source_type`` so that ``to_graphql()`` can group them into inline
    fragments.
    """

    def __init__(self, member_cls: type) -> None:
        self._member_cls = member_cls

    def __getattr__(self, name: str) -> FieldSelector:
        if name.startswith("_"):
            raise AttributeError(name)
        for klass in self._member_cls.__mro__:
            desc = klass.__dict__.get(name)
            if isinstance(desc, SchemaField):
                return desc._make_selector(source_type=self._member_cls)
        raise AttributeError(f"No field '{name}' on '{self._member_cls.__name__}'")

    def __dir__(self) -> list[str]:
        attrs: list[str] = []
        for klass in self._member_cls.__mro__:
            for attr_name, val in klass.__dict__.items():
                if isinstance(val, SchemaField) and not attr_name.startswith("_"):
                    attrs.append(attr_name)
        return attrs

    def __repr__(self) -> str:
        return f"<{self._member_cls.__name__} fragment>"


def _all_graphql_field_names(target_cls: type) -> set[str]:
    """Return the set of all GraphQL field names on *target_cls*."""
    names: set[str] = set()
    for klass in target_cls.__mro__:
        for val in klass.__dict__.values():
            if isinstance(val, SchemaField):
                names.add(val.graphql_name)
    return names


def _build_inline_fragments(
    sub_selections: list[FieldSelector],
    union_target: type[GraphQLUnion],
    var_refs: dict[str, str],
) -> str:
    """Build ``... on TypeName { ... }`` fragments for union sub-selections.

    Sub-selections are grouped by their ``_source_type``.  If a selector
    has no source type, it is assigned to every member type that contains
    a field with the same GraphQL name.
    """
    members = union_target.__member_types__()

    # Group selections by typename.
    groups: dict[str, list[FieldSelector]] = {}
    for member in members:
        groups[member.__typename__] = []

    for sub_sel in sub_selections:
        if sub_sel._source_type is not None:
            typename = getattr(sub_sel._source_type, "__typename__", sub_sel._source_type.__name__)
            if typename in groups:
                groups[typename].append(sub_sel)
            # If source_type doesn't match any member, skip it.
        else:
            # No source type: assign to every member that has this field.
            for member in members:
                if sub_sel._graphql_name in _all_graphql_field_names(member):
                    groups[member.__typename__].append(sub_sel)

    parts: list[str] = []
    for typename, sels in groups.items():
        if sels:
            children = " ".join(to_graphql(s, var_refs) for s in sels)
            parts.append(f"... on {typename} {{ {children} }}")
    return " ".join(parts)


def _build_auto_expand_fragments(union_target: type[GraphQLUnion]) -> str:
    """Build inline fragments auto-expanding each member's scalar fields."""
    members = union_target.__member_types__()
    parts: list[str] = []
    for member in members:
        scalar_names = _scalar_field_names(member)
        if scalar_names:
            typename = member.__typename__
            fields_str = " ".join(scalar_names)
            parts.append(f"... on {typename} {{ {fields_str} }}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# BuiltQuery
# ---------------------------------------------------------------------------


class BuiltQuery:
    """A fully constructed query ready for execution by a client."""

    def __init__(
        self,
        selections: list[FieldSelector],
        aliases: dict[str, FieldSelector],
        operation_type: str = "query",
    ) -> None:
        self.selections = selections
        self.aliases = aliases
        self.operation_type = operation_type

    def to_graphql(self) -> str:
        """Convert to a GraphQL query string."""
        return build_query_string(
            self.selections,
            self.aliases,
            self.operation_type,
        )

    def __repr__(self) -> str:
        return self.to_graphql()


# ---------------------------------------------------------------------------
# Query string generation
# ---------------------------------------------------------------------------


def build_query_string(
    selections: list[FieldSelector],
    aliases: dict[str, FieldSelector],
    operation_type: str = "query",
) -> str:
    """Convert field selectors into a GraphQL query string."""
    var_refs: dict[str, str] = {}

    parts: list[str] = []
    for sel in selections:
        parts.append(to_graphql(sel, var_refs))
    for alias_name, sel in aliases.items():
        parts.append(f"{alias_name}: {to_graphql(sel, var_refs)}")

    fields_str = " ".join(parts)

    if var_refs:
        decls = ", ".join(f"${n}: {t}" for n, t in var_refs.items())
        return f"{operation_type}({decls}) {{ {fields_str} }}"
    return f"{operation_type} {{ {fields_str} }}"


def to_graphql(
    sel: FieldSelector,
    var_refs: dict[str, str] | None = None,
) -> str:
    """Convert a single ``FieldSelector`` to a GraphQL fragment."""
    if var_refs is None:
        var_refs = {}

    name = sel._graphql_name
    prefix = f"{sel._alias}: " if sel._alias else ""

    # Arguments
    args_str = ""
    if sel._args:
        arg_parts: list[str] = []
        for k, v in sel._args.items():
            if isinstance(v, VariableRef):
                var_refs[v.name] = sel._arg_types.get(k, "String")
                arg_parts.append(f"{k}: ${v.name}")
            else:
                arg_parts.append(f"{k}: {_to_literal(v)}")
        args_str = f"({', '.join(arg_parts)})"

    # Sub-selections
    if sel._sub_selections:
        target = sel._resolve_target()
        if _is_union(target):
            assert target is not None
            fragments = _build_inline_fragments(sel._sub_selections, target, var_refs)
            return f"{prefix}{name}{args_str} {{ __typename {fragments} }}"
        children_strs = [to_graphql(s, var_refs) for s in sel._sub_selections]
        children = " ".join(children_strs)
        return f"{prefix}{name}{args_str} {{ __typename {children} }}"

    # Expansion mode (explicit .ALL / .ALL_SCALAR / .ALL_SHALLOW) or
    # implicit default (ALL) for composite types without sub-selections.
    mode = sel._expansion_mode
    target = sel._resolve_target()
    if target is not None and not mode:
        mode = "ALL_SCALAR"  # default expansion
    if mode and target is not None:
        expanded = _expand_by_mode(target, mode)
        if expanded:
            return f"{prefix}{name}{args_str} {{ __typename {expanded} }}"

    return f"{prefix}{name}{args_str}"


def _expand_by_mode(target: type, mode: str) -> str:
    """Dispatch to the appropriate expansion function for *mode*."""
    if _is_union(target):
        if mode == "ALL":
            return _auto_expand_all_union(target, set())
        # ALL_SCALAR and ALL_SHALLOW both use scalar-only fragments for unions
        return _build_auto_expand_fragments(target)
    if mode == "ALL":
        return _auto_expand_all(target)
    if mode == "ALL_SCALAR":
        return _auto_expand_all_scalar(target)
    return _auto_expand_shallow(target)


def _scalar_field_names(target_cls: type) -> list[str]:
    """Return the GraphQL names of all scalar fields on *target_cls*."""
    names: list[str] = []
    for klass in target_cls.__mro__:
        for val in klass.__dict__.values():
            if isinstance(val, SchemaField) and val._target_cls is None:
                names.append(val.graphql_name)
    return names


# ---------------------------------------------------------------------------
# Expansion helpers
# ---------------------------------------------------------------------------

_EXPANSION_MODES = frozenset({"ALL", "ALL_SCALAR", "ALL_SHALLOW"})


def _has_required_args(sf: SchemaField) -> bool:
    """Return True if *sf* has any non-null arguments (type ending with ``!``)."""
    return any(t.endswith("!") for t in sf._arg_types.values())


def _resolve_schema_field_target(sf: SchemaField) -> type | None:
    """Resolve a SchemaField's ``_target_cls`` to an actual type or *None*."""
    if sf._target_cls is None:
        return None
    if isinstance(sf._target_cls, type):
        return sf._target_cls
    return sf._target_cls()  # type: ignore[no-any-return]


def _iter_eligible_fields(target_cls: type) -> list[tuple[SchemaField, type | None]]:
    """Yield ``(SchemaField, resolved_target)`` for fields without required args.

    Fields are deduplicated by GraphQL name (first occurrence in MRO wins).
    """
    seen_names: set[str] = set()
    results: list[tuple[SchemaField, type | None]] = []
    for klass in target_cls.__mro__:
        for val in klass.__dict__.values():
            if (
                isinstance(val, SchemaField)
                and val.graphql_name not in seen_names
                and not _has_required_args(val)
            ):
                seen_names.add(val.graphql_name)
                results.append((val, _resolve_schema_field_target(val)))
    return results


# -- ALL (recursive) --------------------------------------------------------


def _auto_expand_all(target_cls: type, seen: set[type] | None = None) -> str:
    """Recursively expand all fields without required args."""
    if seen is None:
        seen = set()
    if target_cls in seen:
        return ""
    seen = seen | {target_cls}

    parts: list[str] = []
    for sf, field_target in _iter_eligible_fields(target_cls):
        if field_target is None:
            parts.append(sf.graphql_name)
        elif _is_union(field_target):
            frag = _auto_expand_all_union(field_target, seen)
            if frag:
                parts.append(f"{sf.graphql_name} {{ __typename {frag} }}")
        else:
            child = _auto_expand_all(field_target, seen)
            if child:
                parts.append(f"{sf.graphql_name} {{ __typename {child} }}")
    return " ".join(parts)


def _auto_expand_all_union(
    union_target: type[GraphQLUnion],
    seen: set[type],
) -> str:
    """Build inline fragments recursively expanding each member's fields."""
    parts: list[str] = []
    for member in union_target.__member_types__():
        fields_str = _auto_expand_all(member, seen)
        if fields_str:
            parts.append(f"... on {member.__typename__} {{ {fields_str} }}")
    return " ".join(parts)


# -- ALL_SCALAR (flat scalar fields only) -----------------------------------


def _auto_expand_all_scalar(target_cls: type) -> str:
    """Return a space-separated list of scalar field names on *target_cls*."""
    return " ".join(_scalar_field_names(target_cls))


# -- ALL_SHALLOW (one level, no recursion into composites) ------------------


def _auto_expand_shallow(target_cls: type) -> str:
    """Expand all fields without required args; composites get scalar-only children."""
    parts: list[str] = []
    for sf, field_target in _iter_eligible_fields(target_cls):
        if field_target is None:
            parts.append(sf.graphql_name)
        elif _is_union(field_target):
            frag = _build_auto_expand_fragments(field_target)
            if frag:
                parts.append(f"{sf.graphql_name} {{ __typename {frag} }}")
        else:
            scalar_names = _scalar_field_names(field_target)
            if scalar_names:
                children = " ".join(scalar_names)
                parts.append(f"{sf.graphql_name} {{ __typename {children} }}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Path flattening helpers
# ---------------------------------------------------------------------------


def _get_ancestor_path(sel: FieldSelector) -> list[FieldSelector]:
    """Walk ``_parent`` chain and return ``[root, ..., sel]``."""
    path: list[FieldSelector] = []
    node: FieldSelector | None = sel
    while node is not None:
        path.append(node)
        node = node._parent
    path.reverse()
    return path


def _validate_source_type(sel: FieldSelector, receiver: FieldSelector) -> None:
    """Validate that *sel*'s ``_source_type`` is compatible with *receiver*'s target."""
    if sel._source_type is None:
        return
    target = receiver._resolve_target()
    if target is None:
        return
    if _is_union(target):
        # For unions, check that source_type is one of the member types.
        members = target.__member_types__()
        if sel._source_type not in members:
            member_names = ", ".join(m.__name__ for m in members)
            raise TypeError(
                f"Field '{sel._graphql_name}' belongs to "
                f"'{sel._source_type.__name__}', which is not a member of "
                f"union '{target.__name__}' (members: {member_names})"
            )
    elif not issubclass(target, sel._source_type) and not issubclass(sel._source_type, target):
        raise TypeError(
            f"Field '{sel._graphql_name}' belongs to "
            f"'{sel._source_type.__name__}', not '{target.__name__}'"
        )


def _resolve_remaining(
    sel_path: list[FieldSelector],
    receiver_path: list[FieldSelector],
    receiver_depth: int,
    receiver: FieldSelector,
) -> list[FieldSelector]:
    """Compute the remaining path of *sel_path* relative to the receiver.

    Tries receiver-path matching first (the path shares a common ancestor
    chain with the receiver).  Falls back to descriptor-rooted matching
    (the root came from a class descriptor and has ``_source_type``).
    """
    root = sel_path[0]

    # 1) Try receiver-path matching: does the prefix match?
    if len(sel_path) > receiver_depth:
        match = all(
            sel_path[i]._graphql_name == receiver_path[i]._graphql_name
            for i in range(receiver_depth)
        )
        if match:
            return sel_path[receiver_depth:]

    # 2) Descriptor-rooted: root has _source_type (came from a class descriptor).
    if root._parent is None and root._source_type is not None:
        _validate_source_type(root, receiver)
        return sel_path

    # 3) Nothing matched — build a useful error.
    if len(sel_path) <= receiver_depth:
        raise TypeError(
            f"Selection '{sel_path[-1]._graphql_name}' is not a descendant of "
            f"'{receiver._graphql_name}'"
        )
    sel_path_str = ".".join(s._graphql_name for s in sel_path)
    recv_path_str = ".".join(s._graphql_name for s in receiver_path)
    raise TypeError(
        f"Selection path '{sel_path_str}' does not start with receiver path '{recv_path_str}'"
    )


def _flatten_selections(
    receiver: FieldSelector,
    selections: list[FieldSelector],
) -> list[FieldSelector]:
    """Normalize flat path-based selections into a nested tree.

    - Selections without ``_parent``: validated via ``_source_type``,
      then passed through.
    - Selections with ``_parent``: path validated against *receiver*'s
      ancestor path, prefix stripped, deep paths grouped by immediate
      child and recursively nested.
    """
    receiver_path = _get_ancestor_path(receiver)
    receiver_depth = len(receiver_path)

    direct: list[FieldSelector] = []
    # graphql_name -> (intermediate FieldSelector, list of remaining-path tails)
    groups: dict[str, tuple[FieldSelector, list[list[FieldSelector]]]] = {}

    for sel in selections:
        if sel._parent is None:
            _validate_source_type(sel, receiver)
            direct.append(sel)
            continue

        sel_path = _get_ancestor_path(sel)
        remaining = _resolve_remaining(sel_path, receiver_path, receiver_depth, receiver)

        if len(remaining) == 1:
            direct.append(remaining[0])
        else:
            # Deep path: group by immediate child's graphql_name.
            child = remaining[0]
            key = child._graphql_name
            if key not in groups:
                groups[key] = (child, [])
            groups[key][1].append(remaining[1:])

    # Build nested selectors for each group.
    for _key, (child_sel, tails) in groups.items():
        node = child_sel._clone()
        node._parent = None
        node._sub_selections = _nest_paths(tails)
        direct.append(node)

    return direct


def _nest_paths(paths: list[list[FieldSelector]]) -> list[FieldSelector]:
    """Recursively group remaining-path tails into nested sub-selections."""
    direct: list[FieldSelector] = []
    groups: dict[str, tuple[FieldSelector, list[list[FieldSelector]]]] = {}

    for path in paths:
        if len(path) == 1:
            direct.append(path[0])
        else:
            key = path[0]._graphql_name
            if key not in groups:
                groups[key] = (path[0], [])
            groups[key][1].append(path[1:])

    for _key, (child_sel, tails) in groups.items():
        node = child_sel._clone()
        node._parent = None
        node._sub_selections = _nest_paths(tails)
        direct.append(node)

    return direct


def _to_literal(value: Any) -> str:
    """Convert a Python value to a GraphQL literal."""
    if isinstance(value, VariableRef):
        return f"${value.name}"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        inner = ", ".join(_to_literal(v) for v in value)
        return f"[{inner}]"
    if isinstance(value, dict):
        inner = ", ".join(f"{k}: {_to_literal(v)}" for k, v in value.items())
        return f"{{{inner}}}"
    if value is None:
        return "null"
    if hasattr(value, "to_dict"):
        return _to_literal(value.to_dict())
    return str(value)
