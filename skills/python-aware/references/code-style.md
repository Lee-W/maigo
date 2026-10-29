# Python code-style conventions (imports, naming, validation, docstrings)

Loaded on demand by `skills/python-aware/SKILL.md` — **static** style rules a reader or a
linter can check without running the code, and that hold in any Python repository. Read this
file when writing or reviewing Python and one of the topics below applies. For execution-time
gotchas see
[`runtime-gotchas.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/runtime-gotchas.md);
for test-writing rules see
[`test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md).

---

## Imports

### Default to top-level imports in always-called sites

For runtime imports inside `__init__` or any other always-called function,
default to a **top-level** import. Reserve the lazy / function-body form for:
`TYPE_CHECKING` blocks, breaking a known circular-import cycle, multi-process
worker-isolation paths, or deferred-execution callbacks (e.g., a
`deserialize()` body that is not called at module import time).

Self-check before writing a function-body import: "does this function run on
every public touch of the class?" If yes → top-level. Verify no circular-import
risk with a quick `python -c "from <module> import <symbol>"` before falling
back to lazy.

This applies to test code too — the same default holds even in test files.
Hoist `MagicMock`, codec helpers, and class references to the module import
block unless a real exception (circular cycle, worker isolation, deferred
callback) applies. An inline import inside a test method that exists only out
of habit/locality is not such an exception.

A function-local import that re-imports a name the module already imports at
top level is never allowed — it is pure duplication, with no exception case.
Delete the local line and use the top-level name.

### Annotation-only imports belong under `TYPE_CHECKING`

In a module with `from __future__ import annotations`, an import used
**only** in type annotations belongs under `if TYPE_CHECKING:`, not at module
top level — annotations are not evaluated at runtime, so no runtime import is
needed. "Other methods still use it" is not a justification when those uses
are all annotations, not runtime calls.

When a file is touched only as a side effect of another change, the target is
**zero diff** in that file once the change settles. If a diff remains (e.g.
an import that moved location because a since-removed code path needed it at
runtime), check: is the symbol used at runtime (as a value/call), or only in
annotations? Annotation-only → move to `TYPE_CHECKING`.

This is the companion rule to "default to top-level for eager call sites"
above: runtime use → top level; annotation-only use → `TYPE_CHECKING`.

### Prefer the plain imported name over an alias

When moving an inline import to top level (or otherwise refactoring
imports), don't preserve an `as <alias>` purely to minimize diff churn at the
call sites. If the plain name works, use it and update the call sites too.
Reserve `as` for resolving a real name collision.

An alias kept only to avoid editing the wrapper/call sites is noise — it
leaves a redundant symbol the reader has to decode (e.g.
`get_user as _real_get_user` when nothing else binds `get_user` in that
module). Smaller diff is not worth a permanently noisier name.

Watch for the case where a monkeypatch test patches `module.get_user`, but
a top-level `from x import get_user` in the *test* module keeps pointing at
the original — the alias (or the bare re-import) bought nothing and the test
silently exercises the un-patched symbol.

The general form of this rule — don't alias an import unless a
module-qualified reference is genuinely impossible — is in
[`skills/strict-review/references/recurring-patterns.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/recurring-patterns.md)'s
"Don't alias imports" section.

### When a parameter shadows an imported callable it must call, rename the parameter

When a function parameter has the same name as an imported callable the
function body needs to call, rename the parameter (prefer an existing local
name already used nearby) rather than aliasing the import (e.g.
`send_email as _send_email`). The underscore-aliased import is a code smell
signalling the parameter shouldn't have shadowed a well-known function;
renaming the parameter keeps both the import and the call plain. A public API
field name that happens to match stays untouched — only the internal
parameter name and its keyword call sites move.

## Naming and constants

### Name variables for what the object is, not an indirect reference

Avoid a `_def` / `_ref` suffix on a variable that holds the actual runtime
object (`schedule = Schedule(...)`, not `schedule_def = Schedule(...)`) —
reserve those suffixes for genuinely indirect objects (e.g. a `ScheduleRef`).
Don't copy a `_def`-suffixed name from a neighboring test just because it's
already there if the variable in question holds the real object.

### Simple default values don't need a named constant

A trivial default (`0`, `0.0`, `None`) doesn't need a named constant — inline
the value in the signature and put the semantics in the docstring `:param`
block. A named constant for a single-usage trivial default (e.g.
`DEFAULT_GRACE_PERIOD = 0.0`) adds indirection without value. Reserve named
constants for non-obvious values (timeouts, sizes, magic numbers) that appear
in multiple places or whose value itself carries meaning.

### Don't add an underscore prefix to a cross-file-called function just because its callers are in the same package

Functions that get imported and called across files within a package stay
unprefixed when the package declares no `__all__` and follows that pattern
elsewhere. Only functions that are purely internal helpers within a single
module get the underscore.

"All the callers happen to live in the same package" is not, on its own, a
reason to add an underscore prefix — check the existing naming pattern in
the same directory (cross-file-called vs. purely-internal) before deciding,
rather than defaulting toward a leading underscore because the call sites
are nearby.

### Name a threshold constant for why it has that value, and cite the source

Name a threshold-style duration constant after the bound it encodes, not the place it is used: `_MAX_DST_SHIFT = timedelta(hours=2)` says why the value is 2 hours; `_FOLD_DELTA_LIMIT` only says where it is read. Next to it, comment where the number comes from and its known exceptions (here: the largest pure DST shift in tzdata 2020–2030 is Antarctica/Troll's 2 hours; Casey's 3 hours is a standard-time change, not DST).

One constant must not be the threshold for two different things. In apache/airflow #75847 the first version used one 1-hour constant both as a shortcut gate and as the look-back width, and both meanings were wrong. Two meanings, two constants, each named for its own bound.

## Validation and error handling

### Raise at construction instead of documenting a structural footgun

When a helper has a known structural failure mode that would produce
silently-wrong output (not a runtime error — a counter-intuitive result that
still parses/executes), promote it from a "known limitation" docstring
caveat to a hard `ValueError` at construction time, matching the helper's
other eager-validation cases. A helper that already raises for some malformed
inputs is announcing an eager-validation policy; a silent footgun left in the
same helper breaks that contract.

How to apply: when about to write "Known limitation: ..." or "compiles
silently but ..." in a docstring for a structural defect, ask whether it can
be detected at construction and raised instead. If detection is expensive or
the case is genuinely ambiguous, document it. If eager validation would break
existing callers relying on the silent behavior, prefer a migration path
(deprecation warning + future raise + tracking issue) over leaving the
footgun undocumented-but-silent forever.

A parameter inherited from a base class that is **always** a no-op in a
subclass belongs to the same category — reject it at construction, don't
just document "this is ignored." Judge it by precedent: if the class already
rejects other invalid input in `__init__`, an always-no-op inherited
parameter is the same class of problem and should be rejected the same way.
Shape: `__init__` raises `ValueError` on a non-default value, and the
message names **where to set it instead** ("set timeout on each member
instead"), not just "not supported." Update the property docstring and any
usage guide from "ignores" to "rejects" at the same time — leaving even one
of the two in the old wording gives the next review round the same thing to
re-raise. A documentation-only mitigation is a weak fix whenever an existing
validation shape can reject the input outright instead.

### Impossible or partially-given state raises — never warn-and-continue or fall through

For a state that "cannot happen", or one where only part of the required input was given, raise.
Don't warn and return, and don't fall through into a different behaviour that silently changes
identity or target. Examples: a "can't happen" branch (a consumer that is `None`) that logs a
warning and carries on should be a `RuntimeError`; credentials where only some fields were supplied
must not silently switch to a different authentication chain. Same family as "Raise at construction"
above, and the same deprecation exception applies: for unreleased code or internal state raise
directly; for an already-released behaviour, go through the deprecation path described there.

### Direction flags, `except` breadth, and constructor parameters

1. A parameter that uses an int as a direction flag (`sign=±1`) becomes explicitly named
   functions; if the library you wrap has a public API for it, use that (a `sign=` argument
   becomes `add_usage` / `subtract_usage`).
2. Narrow a broad `except`, but align it with the matching catch layering **upstream** so behaviour
   does not change; where upstream already warns, don't warn a second time.
3. Class constructor parameters default to keyword-only.

### `raise X from <expr>` silently suppresses the chain when `<expr>` is `None`

`raise X from <expr>` evaluates `<expr>`; when it evaluates to `None`, Python
treats it exactly like `raise X from None` — the explicit syntax for
suppressing exception chaining. `__cause__` and the implicit context are
dropped, and the traceback stops showing why the original error happened.
This is worse than not chaining at all, because it looks intentional.

Watch for it when re-raising out of a caught object whose payload can be
absent — e.g. tenacity's `RetryError`:
`except RetryError as e: raise MyError(...) from e.last_attempt.exception()`
looks like proper chaining, but `Future.exception()` returns `None` when the
retry stopped for a non-exception reason, quietly suppressing the chain.
Chain `from e` instead — the caught exception object itself is never `None` —
and reserve `e.last_attempt.exception()` for the message text, where a `None`
is merely cosmetic ("last error: None").

Before writing `raise ... from <expr>`, confirm `<expr>` cannot evaluate to
`None` for any code path that reaches the `raise`.

## Concurrency

### Clear a `ContextVar` opened in an async generator with `set(None)`, not `reset(token)`

When an async generator opens a `ContextVar` window before a `yield`
(`token = var.set(x)`) and closes it in a `finally: var.reset(token)`, don't
keep the standard `reset(token)` form if the generator can be resumed from a
different asyncio task than the one that called `set()` — it raises
`ValueError: token created in a different Context`. Use `var.set(None)` to
clear the window instead (only valid when windows don't nest, since clearing
to `None` — not to the prior value — is exactly correct there).

The failure is a runtime context-propagation issue, not something ruff or
mypy will flag: an async generator's `__anext__` runs in whichever task calls
it, and a driver (an `async for` loop, or a test helper resuming past a
`yield`) is often a different task than the one that opened the window.
`ContextVar.reset(token)` requires the token to have been created in the
*current* context, so it rejects the cross-task resume. Confirmed empirically
on a stream-acknowledgement drain: `reset(token)` failed every existing ack
test; `set(None)` fixed all of them.

When writing this pattern, document the invariant in a docstring or comment
("this ContextVar assumes the generator and its consumer share a task /
windows don't nest") so a future refactor that introduces nesting doesn't
silently break it.

## mypy

### Restructure branches so the assignment and the access sit in the same block — don't `assert` past it

When mypy can't narrow an `Optional` from a plain `if` condition, don't reach
for `assert` to silence it — `assert` in production code is not an option
anyway (it disappears under `python -O`). Instead restructure so the
assignment and the access that depends on it live inside the **same**
conditional branch, letting mypy narrow the type at the point of assignment.

Example: a `clear()`-style function that first emits an early guard and only
later resolves a `session` object should instead read
`if has_window: session = get_session(...); if has_start and has_end: ...`
inside one branch, rather than resolving `session` unconditionally and
asserting non-`None` before use several lines later.

### Widening a `Literal` to `str` relocates the mypy error, it doesn't fix it

When a field's declared type is a third-party SDK's `Literal[...]` and you
need it to accept a plain `str` (for example a templated or config-driven
value), widening it to `str` doesn't make mypy pass — it only pushes the
`arg-type` error one layer down: past your wrapper to its call into the SDK
(and further, if that layer is widened too, to the SDK boundary itself,
which still expects the `Literal`).

Only trust `mypy <changed files>` returning exit 0 as evidence the widening
is complete — "both call sites are widened now" from a diff read is not
sufficient, because the same shape of error keeps reappearing one level
lower.

Fix it at the SDK boundary, not by copying the SDK's `Literal` values into
your code — those drift out of date the moment the SDK adds a value. Put a
`# type: ignore[arg-type]` on the exact line of the SDK call, with a
one-line comment explaining why, and split the call across multiple lines so
the ignore covers only the affected argument. `cast(...)` is viable only when
the SDK exports a named type alias for the literal (then
`cast("sdk.module.ModelName", value)` works); a `Literal` inlined in a method
signature has no symbol to cast to, so casting there just recreates the same
copy-and-drift problem.

## Docstrings

### Put `:param` blocks in the class docstring, not `__init__`

Sphinx (and most Python doc tooling) renders class-level `:param` blocks as
constructor parameters. Putting them in `__init__` requires opening a
separate docstring block and can trigger linter issues (e.g. D205) when
there's no summary line.

When documenting constructor parameters, extend the **class** docstring with
`:param name: description` entries. Leave `__init__` without a docstring
unless it has genuinely separate logic to explain beyond the parameters.

### Don't write a boilerplate "Initialize a Foo." lead-in

When an `__init__` docstring is kept (e.g. for genuinely separate logic), drop
a boilerplate first line like `Initialize a ``Foo``.` / `Construct a ...` /
`Create a ...`. It's a pure restatement of the method name and class context —
the `:param` entries are the actual contract. If the only thing the docstring
would say is that boilerplate line, drop the docstring entirely. A one-line
purpose summary is still fine on a **class**-level docstring (right after
`class Foo:`) since there's no `def __init__` name on screen there to restate.

### Document all sibling params in the same pass

When adding a `:param` entry for a new parameter, document **all**
parameters of that class/function in the same pass — don't leave siblings
undocumented. A partial `:param` block looks incomplete and inconsistent: if
the class is worth documenting at all, all its public parameters are worth a
line.

Before writing a new `:param name:` entry, scan the existing parameters and
add brief `:param` lines for any that are missing. Keep each line short — one
sentence is enough.

### Adding a per-item qualifier obliges re-checking sibling entries

In a list of parallel entries (a docstring's `:param:` list, a config table,
a set of flag descriptions), the moment you add a qualifier to **some**
entries ("only used when X", "only supported in version Y"), go back and
re-check whether the unqualified **existing** entries in the same list are
still accurate.

The existing entries may not have been wrong before — they can become
misleading purely because of the new context. Once neighboring entries carry
an explicit scope, a reader treats an entry without one (or with a stale one)
as unconditionally true.

Example: an operator docstring starts qualifying `wait_seconds` ("only used
when `deferrable` is False") and the newly added `poll_interval` ("only used
when `deferrable` is True"), while `timeout` keeps its pre-existing "Only used
when `deferrable` is False" — except the deferred path also passes `timeout`
to the trigger, so both modes are governed by it. Before the qualifiers were
added, that line was merely vague; after, it became a specific falsehood.

When adding a qualifier, trace every entry in the same list against the
source (which branches actually consume each field), not just the one
you're editing.

### User-facing docstrings describe behavior, not internal mechanism

User-facing docstrings and CLI `--help` text should describe the
**observable behavior** a user can act on — not the internal mechanism.
Don't name internal helper functions, don't spell out normalization/conversion
steps, don't reference private functions. Say what the user sees and what to
do about it.

The reader of a command's docstring/help is a user, not a maintainer of that
function. Naming an internal helper or describing "normalized to UTC before
`.date()`" leaks plumbing that (a) the user can't act on and (b) goes stale
when the implementation changes.

How to apply: strip references to internal callables and conversion steps.
Replace "parsed by `<internal helper>`, normalized to UTC before `.date()`"
with the behavioral statement: "any time-of-day or timezone offset in the
value is ignored; only the calendar date is used." Keep the *contract* (what
goes in, what the effect is), drop the *how*. Verify the real behavior before
documenting it — the mechanism you assume may be wrong.

---

## Subprocess

### Check `returncode != 0` before reading `stdout`

After calling a CLI subprocess, check `returncode` first and read `stdout` second. An empty
`stdout` does not mean success: `git status` outside a git repository exits 128 with empty
stdout, so a check that only looks at stdout reads that as "clean".

In a fail-open helper the `returncode` check must come before the stdout check:

```python
result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
if result.returncode != 0:
    return True  # command failed: fail open, don't assume "clean"
return bool(result.stdout.strip())
```

How to apply: when writing or reviewing subprocess code, ask "what does this branch do when the
command itself fails?" and add a test that runs it where the command fails (for example a
`tmp_path` that is not a git repository).
