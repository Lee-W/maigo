# Python runtime gotchas (type-system and version-skew pitfalls)

Loaded on demand by `skills/python-aware/SKILL.md` — execution-time defects that pass a
type checker and a casual read but fail against a specific Python version, pydantic version, or
library runtime behavior.
Read this file when writing or reviewing a type- or version-sensitive construct:
`Annotated` constraints, nested enums, subscripted generics, `Decimal` → `int`, chained
`.append()` on an ORM query result.

---

## pydantic `Annotated` field constraints: bare `= None` default, not `Field(default=None)`

When a pydantic v2 field carries its validation constraints in the type via
`Annotated[str, StringConstraints(...)] | None`, the default assignment is
separate from the constraints — `= Field(default=None)` is then a pure
redundant wrapper: with no other `Field()` args, it behaves identically to
a bare `= None`. Verified empirically (pydantic 2.13.4): both forms accept
and reject the same inputs, store the same value, and generate the same
JSON schema (`{'anyOf': [...], 'default': None, ...}`). Because the schema
is identical, switching between the two forms needs **no** OpenAPI/UI/client
codegen regeneration.

Prefer bare `= None` to match sibling optional fields
(`owner: str | None = None`); only reach for `Field(...)` when
actually using one of its args (alias, description, default_factory, etc.).
Example: `label: Annotated[str, StringConstraints(pattern=r"\S",
max_length=64)] | None = None`.

## Nested-enum annotation needs the qualified name; the default value can stay bare

When an enum (or any class) is nested inside another class — e.g. `class
Outer:` with `class Direction(str, Enum): ...` inside it — a method
annotation written as the bare nested name **fails `typing.get_type_hints`**:

```python
def __init__(self, *, direction: Direction = Direction.FORWARD) -> None:  # BAD annotation
```

Under `from __future__ import annotations` the annotation is the *string*
`"Direction"`, resolved later against the function's **module globals** —
where only `Outer` exists, not bare `Direction`.
`get_type_hints(Outer.__init__)` raises `NameError: name 'Direction' is
not defined`, breaking anything that introspects the signature
(serialization frameworks, pydantic, docs tooling).

Fix — qualify the **annotation**, keep the **default** bare:

```python
def __init__(self, *, direction: Outer.Direction = Direction.FORWARD) -> None:
    self.direction = self.Direction(direction)
```

The two resolve at different times: the annotation string
`"Outer.Direction"` resolves against module globals (`Outer` is a
module-level name, `.Direction` is its attribute) ✓. The default
*expression* `Direction.FORWARD` evaluates at class-body execution time,
where bare `Direction` **is** in scope (the nested class is defined before
the method) — writing `Outer.Direction.FORWARD` there would `NameError`
instead, since `Outer` isn't bound yet during its own class-body
execution. In method bodies use `self.Direction(...)` /
`cls.Direction(...)`; at module level (helpers outside the class) use the
full `Outer.Direction.X` (runtime, `Outer` is bound by call time).

Verify empirically with `typing.get_type_hints(Cls.__init__)` before
trusting either form.

## `isinstance(list[int], type)` is `True` on Python 3.10, `False` on 3.11+

`isinstance(list[int], type)` returns `True` on **Python 3.10** and only
changed to `False` on 3.11+ via
[gh-101162](https://github.com/python/cpython/issues/101162). Any
type-introspection gate that uses `isinstance(x, type)` to mean "this is not
a subscripted generic" is silently ineffective on 3.10 — running tests only
on 3.11+ gives a false green when the project still supports 3.10.

Case: a field-type resolver receives `list[int] | None`; the top-level origin
is a union, so it passes the top-level check and reduces to `list[int]` —
`isinstance(resolved, type)` then fails to reject it, and the container field
gets treated as coercible. The fix is to check `typing.get_origin(resolved)
is not None` again **after** the union reduction, rather than relying on
`isinstance`.

Same-family risk: `typing.get_args()`'s **argument count** alone doesn't
distinguish a union from any other subscripted generic (`list[int]` also
has exactly one argument) — check `get_origin` instead. See also
`references/test-conventions.md`, "Reject-path tests need one case per shape,
not one representative value" — a type-introspection gate like this one needs
a 3.10-shaped test case, not just a 3.11+ one.

## `int(Decimal(...))` bypasses CPython's digit-count limit

CPython bounds `int(str)` and `str(int)` to 4300 digits (the
CVE-2020-10735 mitigation; tunable via `sys.set_int_max_str_digits`), but
**`int(Decimal)` has no such limit**. Switching a coercion path from
string parsing to `Decimal` parsing then `int()` silently removes that
language-level protection.

Case: an integer coercion helper added a `Decimal` fallback so a rendered
value like `"5.0"` would also be accepted; `"1E+100000"` then first burns
CPU building a six-digit-count integer, and only blows up when the
error-message formatter does `{value!r}` on it — raising CPython's own
`Exceeds the limit (4300 digits)` instead of the module's intended, named
`ValueError`. Fix: guard it yourself — `parsed.adjusted() >= 4300` raises a
named error before it ever reaches `int()`.

Two transferable lessons:

1. **Switching conversion paths can silently drop a language-level
   guard** — `int(str)` / `int(Decimal)` / `int(float)` don't share the
   same constraints; verify the specific path actually being used, not
   "int() is protected" in general.
2. **The error-handling path itself can throw** — `repr()`-ing a huge
   integer isn't free. Confirm a value can actually be formatted before
   interpolating it into an error message; when the value is unbounded,
   bound and order it first (same reasoning as bounding and ordering any
   unbounded collection rendered into a DB row or log).

## Chaining `.append()` onto a query result can raise `ObjectDereferencedError`

Writing `session.scalar(select(Parent).where(...)).children.append(Child(...))` in one
expression intermittently fails with `sqlalchemy.orm.exc.ObjectDereferencedError: Can't emit change
event for attribute 'Parent.children' - parent object ... has been garbage collected`.

Why: the session's identity map holds only a **weak reference** to a clean (unmodified) ORM
object. If nothing binds the queried object to a name, the garbage collector may reclaim it before
`.append` emits its change event. It depends on GC timing, so it is intermittent, not red on every
run. Case (apache/airflow #75404, an asset-orphaning test): the chained form failed sporadically;
binding the result to a local first (`shared = session.scalar(...)`, then
`shared.aliases.append(...)`) made the whole test group green.

How to apply: before any relationship operation (append, remove, assignment) on an object returned
by `session.scalar()` / `session.get()` / a query, bind it to a local variable first; never chain
`.relationship.xxx` directly onto the return value. When writing or reviewing tests and fixtures,
rewrite this chained shape on sight. It is a language-level convention, valid in any SQLAlchemy repo.
