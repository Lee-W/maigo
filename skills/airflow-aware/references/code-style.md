# Airflow code-style conventions (imports, docstrings, authoring)

Loaded on demand by `skills/airflow-aware/SKILL.md` — style conventions that
recur often enough across implementer / reviewer tasks to warrant a shared
reference. Read this file when writing or reviewing Python in an Airflow
checkout and one of the topics below applies.

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
`get_db_dag as _real_get_db_dag` when nothing else binds `get_db_dag` in that
module). Smaller diff is not worth a permanently noisier name.

Watch for the case where a monkeypatch test patches `module.get_db_dag`, but
a top-level `from x import get_db_dag` in the *test* module keeps pointing at
the original — the alias (or the bare re-import) bought nothing and the test
silently exercises the un-patched symbol.

### When a parameter shadows an imported callable it must call, rename the parameter

When a function parameter has the same name as an imported callable the
function body needs to call, rename the parameter (prefer an existing local
name already used nearby) rather than aliasing the import (e.g.
`clear_task_instances as _clear_task_instances`). The underscore-aliased
import is a code smell signalling the parameter shouldn't have shadowed a
well-known function; renaming the parameter keeps both the import and the
call plain. A public API field name that happens to match stays untouched —
only the internal parameter name and its keyword call sites move.

## Naming and constants

### Name variables for what the object is, not an indirect reference

Avoid a `_def` / `_ref` suffix on a variable that holds the actual runtime
object (`asset = Asset(...)`, not `asset_def = Asset(...)`) — reserve those
suffixes for genuinely indirect objects (e.g. an `AssetRef`). Don't copy a
`_def`-suffixed name from a neighboring test just because it's already there
if the variable in question holds the real object. Also avoid Sphinx `#:`
attribute-doc comments on class attributes — they aren't an idiom this repo
uses; a plain `#` comment is the convention.

### Simple default values don't need a named constant

A trivial default (`0`, `0.0`, `None`) doesn't need a named constant — inline
the value in the signature and put the semantics in the docstring `:param`
block. A named constant for a single-usage trivial default (e.g.
`DEFAULT_GRACE_PERIOD = 0.0`) adds indirection without value. Reserve named
constants for non-obvious values (timeouts, sizes, magic numbers) that appear
in multiple places or whose value itself carries meaning.

## Validation and enforcement

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

### Once a check enforces an invariant, drop the comment that manually enumerates it

When a prek hook / test / linter rule starts **enforcing** an invariant that a
prose comment previously described by hand (e.g. a comment listing which
fields two sibling classes must keep in sync), delete the manual enumeration
from the comment once the check covers it. Keep only the part the check
cannot convey — typically *why* the constraint exists. A hand-written
enumeration of an enforced invariant drifts from the enforcement over time
(the check gets updated, the comment doesn't); the check is the authoritative
spec, so a comment duplicating it is a maintenance liability, not a safety
net.

## mypy Optional narrowing

### Restructure branches so the assignment and the access sit in the same block — don't `assert` past it

When mypy can't narrow an `Optional` from a plain `if` condition, don't reach
for `assert` to silence it — under this repo's "no `assert` in production
code" rule that's not an option anyway. Instead restructure so the assignment
and the access that depends on it live inside the **same** conditional branch,
letting mypy narrow the type at the point of assignment.

Example: a `clear()`-style function that first emits an early guard and only
later resolves a `dag` object should instead read
`if has_date_window: dag = get_db_dag(...); if has_start and has_end: ...`
inside one branch, rather than resolving `dag` unconditionally and asserting
non-`None` before use several lines later.

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

## CI / prek hook scripts

### New `scripts/ci/prek/*.py` hooks: `requires-python = ">=3.10"`, keep the shebang

For a new prek hook script, write the PEP 723 inline metadata as
`# requires-python = ">=3.10"` — **no `<3.11` upper cap** — and keep the
`#!/usr/bin/env python` shebang as the first line. An upper cap pins the
hook's venv to exactly one Python version, which is unnecessary for a plain
AST/text hook and hurts portability; `>=3.10` ("3.10 or newer") is what's
actually meant. The shebang matters because prek execs the entry file
directly — a file with no shebang gets run under `/bin/sh`, which chokes on
Python syntax.

## Authoring

### No `dag_run.logical_date` in Airflow 3 examples

In Airflow 3 prose, example Dags, and docs, do **not** reach for
`dag_run.logical_date` to derive a run's date/period anchor. Prefer the
modern timing attribute — `dag_run.run_after` (the scheduling anchor), or
`data_interval_start` / `data_interval_end` when an interval is meant.

`logical_date` is nullable in Airflow 3 (it is `None` for asset- and
manually-triggered runs) and is being de-emphasized; teaching it in an
example propagates a deprecated pattern and breaks for non-scheduled runs.

When an example needs "the period this run is for," write
`dag_run.run_after` rather than `dag_run.logical_date`. Verify the exact
field for the context before asserting it.
