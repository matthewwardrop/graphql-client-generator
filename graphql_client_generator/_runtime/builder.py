"""Query builder: typed, tab-completable GraphQL query construction."""

from __future__ import annotations

import inspect
from typing import Any

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
    ) -> None:
        self._graphql_name = graphql_name
        self._target_cls = target_cls
        self._arg_types = arg_types or {}
        self._arg_doc = arg_doc
        self._input_arg = input_arg
        self._input_cls = input_cls
        self._args: dict[str, Any] = {}
        self._sub_selections: list[FieldSelector] = []
        self._alias: str | None = None

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
        )
        node._args = dict(self._args)
        node._sub_selections = list(self._sub_selections)
        node._alias = self._alias
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
        selections: FieldSelector | tuple[FieldSelector, ...],
    ) -> FieldSelector:
        """Set sub-field selections.

        Raises ``TypeError`` if required arguments have not been provided
        via ``__call__`` first.
        """
        # Validate required args before allowing sub-selections.
        if self._input_arg:
            # Flattened input mode: check the wrapped arg is present.
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
        if not isinstance(selections, tuple):
            selections = (selections,)
        node = self._clone()
        node._sub_selections = list(selections)
        return node

    # -- aliasing via .as_() ---------------------------------------------------

    def as_(self, alias: str) -> FieldSelector:
        """Set an alias for this field.  Can be called before or after ``[]``."""
        node = self._clone()
        node._alias = alias
        return node

    # -- child field access (tab completion) -----------------------------------

    def __getattr__(self, name: str) -> FieldSelector:
        if name.startswith("_"):
            raise AttributeError(name)
        target = self._resolve_target()
        if target is not None:
            for klass in target.__mro__:
                desc = klass.__dict__.get(name)
                if isinstance(desc, SchemaField):
                    return desc._make_selector()
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
        return self._make_selector()

    def _make_selector(self) -> FieldSelector:
        return FieldSelector(
            self.graphql_name,
            target_cls=self._target_cls,
            arg_types=self._arg_types,
            arg_doc=self._doc,
            input_arg=self._input_arg,
            input_cls=self._input_cls,
        )

    def __repr__(self) -> str:
        return f"SchemaField({self.graphql_name!r})"


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
        children_strs = [to_graphql(s, var_refs) for s in sel._sub_selections]
        children = " ".join(children_strs)
        return f"{prefix}{name}{args_str} {{ __typename {children} }}"

    # No explicit sub-selections but the field is a composite type:
    # auto-expand with all scalar sub-fields.
    target = sel._resolve_target()
    if target is not None:
        scalar_names = _scalar_field_names(target)
        if scalar_names:
            children = " ".join(scalar_names)
            return f"{prefix}{name}{args_str} {{ __typename {children} }}"

    return f"{prefix}{name}{args_str}"


def _scalar_field_names(target_cls: type) -> list[str]:
    """Return the GraphQL names of all scalar fields on *target_cls*."""
    names: list[str] = []
    for klass in target_cls.__mro__:
        for val in klass.__dict__.values():
            if isinstance(val, SchemaField) and val._target_cls is None:
                names.append(val.graphql_name)
    return names


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
