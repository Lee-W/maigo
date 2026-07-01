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

## Docstrings

### Put `:param` blocks in the class docstring, not `__init__`

Sphinx (and most Python doc tooling) renders class-level `:param` blocks as
constructor parameters. Putting them in `__init__` requires opening a
separate docstring block and can trigger linter issues (e.g. D205) when
there's no summary line.

When documenting constructor parameters, extend the **class** docstring with
`:param name: description` entries. Leave `__init__` without a docstring
unless it has genuinely separate logic to explain beyond the parameters.

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
