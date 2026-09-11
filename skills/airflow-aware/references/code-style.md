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

The general form of this rule — don't alias an import unless a
module-qualified reference is genuinely impossible — is in
[`skills/strict-review/references/recurring-patterns.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/recurring-patterns.md)'s
"Don't alias imports" section.

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

### Don't add an underscore prefix to a cross-file-called function just because its callers are in the same package

In `providers/common/ai/src/airflow/providers/common/ai/utils/`, functions
that get imported and called across files within the package (e.g. from
`operators/*.py`) stay unprefixed — `build_file_analysis_request`,
`log_run_summary`, `resolve_sqlglot_dialect`, `validate_prompt`,
`coerce_usage_limits` all follow this, and the package declares no
`__all__`. Only functions that are purely internal helpers within a single
module (e.g. `usage.py`'s `_coerce_value`, `_validate_range`) get the
underscore.

"All the callers happen to live in the same package" is not, on its own, a
reason to add an underscore prefix — check the existing naming pattern in
the same directory (cross-file-called vs. purely-internal) before deciding,
rather than defaulting toward a leading underscore because the call sites
are nearby (apache/airflow PR #71403).

## Provider hooks

### Keep only connection-backed calls on the hook

Before adding a `@staticmethod` to a provider hook, ask whether it touches
`self.conn`. A staticmethod that doesn't — e.g. a one-line `model_dump()`
call that flattens an SDK response into an XCom-safe dict — becomes part of
the hook's public API the moment the provider releases, which means the
provider carries it as a back-compat surface for years. That's not worth it
for a pure data-transform helper; inline it into the operator's `execute`
instead, and keep the hook to connection-related calls only.

Exception: the helper stays on the hook if another **connection-backed**
method on the same hook reuses it. Contrast
`providers/anthropic/.../hooks/anthropic.py:709` `summarize_usage` — staying
is correct, since the connection method `get_session_usage` (:706) calls it
internally — against the removed
`providers/openai/.../hooks/openai.py` `summarize_response_usage`, which had
no hook-internal caller and was only ever called once from an operator
(inlined in apache/airflow PR #72151). A neighboring provider putting the
same shape of helper on its hook is not, by itself, a reason to follow suit —
check whether it has an internal caller first.

Before removing such a method, confirm it hasn't shipped yet (check the
provider's `pyproject.toml` version and `docs/changelog.rst`, and whether the
commit that added it is already on `main`). Unreleased means it isn't a
breaking change and needs no changelog entry or newsfragment (providers never
use newsfragments). If it has already released, treat the removal as a
breaking change instead. When moving the code, carry over every `why` from
the original docstring to its new home — don't leave bare logic behind.

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

### `raise X from <expr>` silently suppresses the chain when `<expr>` is `None`

`raise X from <expr>` evaluates `<expr>`; when it evaluates to `None`, Python
treats it exactly like `raise X from None` — the explicit syntax for
suppressing exception chaining. `__cause__` and the implicit context are
dropped, and the traceback stops showing why the original error happened.
This is worse than not chaining at all, because it looks intentional.

Watch for it when re-raising out of a caught object whose payload can be
absent — e.g. tenacity's `RetryError`:
`except RetryError as e: raise AirflowException(...) from e.last_attempt.exception()`
looks like proper chaining, but `Future.exception()` returns `None` when the
retry stopped for a non-exception reason, quietly suppressing the chain
(apache/airflow PR #69238, databricks hook). Chain `from e` instead — the
caught exception object itself is never `None` — and reserve
`e.last_attempt.exception()` for the message text, where a `None` is merely
cosmetic ("last error: None").

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
on apache/airflow's `shared_stream.py` `_ack_drain` (PR #67523):
`reset(token)` failed 20 existing ack tests; `set(None)` fixed all of them.

When writing this pattern, document the invariant in a docstring or comment
("this ContextVar assumes the generator and its consumer share a task /
windows don't nest") so a future refactor that introduces nesting doesn't
silently break it.

## mypy

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

### Widening a `Literal` to `str` for templating relocates the mypy error, it doesn't fix it

Adding an operator field to `template_fields` when its declared type is a
third-party SDK's `Literal[...]` requires widening it to `str` so a
Jinja-templated Dag value type-checks. That widening doesn't make mypy pass —
it only pushes the `arg-type` error one layer down: past the operator to the
hook's call into the SDK (and further, if the hook is widened too, to the
SDK boundary itself, which still expects the `Literal`).

Only trust `uv run --project providers/<provider> mypy <changed files>`
returning exit 0 as evidence the widening is complete — "both call sites are
widened now" from a diff read is not sufficient, because the same shape of
error keeps reappearing one level lower.

Fix it at the SDK boundary, not by copying the SDK's `Literal` values into
the provider — those drift out of date the moment the SDK adds a value (e.g.
a provider hard-coding 3 endpoint names when the installed SDK already
accepts 8). The repo convention (15+ existing sites under
`providers/*/src/airflow/providers/*/hooks/*.py`, e.g.
`providers/slack/.../hooks/slack.py`, `providers/docker/.../hooks/docker.py`)
is a `# type: ignore[arg-type]` on the exact line of the SDK call, with a
one-line comment explaining why, and the call split across multiple lines so
the ignore covers only the affected argument. `cast(...)` is viable only when
the SDK exports a named type alias for the literal (e.g.
`providers/anthropic/.../hooks/anthropic.py`'s
`cast("agent_create_params.Model", ...)`); a `Literal` inlined in a method
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

Case in point: `OpenAITriggerBatchOperator`'s docstring started qualifying
`wait_seconds` ("only used when `deferrable` is False") and the newly added
`poll_interval` ("only used when `deferrable` is True"), while `timeout`
kept its pre-existing "Only used when `deferrable` is False" — except the
deferred path also passes `timeout` to the trigger, so both modes are
governed by it. Before the qualifiers were added, that line was merely
vague; after, it became a specific falsehood (apache/airflow PR #72051).

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

## Tests

### Don't assert a class attribute equals a literal

Don't write `assert SomeOperator.template_fields == ("a", "b")` (or the same
pattern for any other class attribute / constant). It only fails when
someone edits the attribute and the assertion separately — it restates the
source line rather than testing behavior, and Airflow reviewers will push
back on it.

Test the behavior instead: for `template_fields`, that means asserting the
fields actually render as expected after
`operator.render_template_fields(context=...)`.

The diagnostic question is "under what circumstances does this assertion
fail?" — if the only answer is "someone changed the source without updating
the test," it has no discriminating power.

Before deleting an existing literal-equality assertion in favor of a
behavior test, check whether it covers something the new behavior test
doesn't (e.g. `template_fields == ("file_id", "endpoint", "metadata")`
asserts `file_id` is present, which a render test might not exercise). If
that gap is pre-existing behavior, leave it untested per this repo's
"don't backfill tests for existing logic" convention; if the PR introduced
it, add a behavior test for it before deleting the literal-equality
assertion.

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

### Template a Variable reference with `.get(name, default)`, never the bare `var.value.<name>` form

When an example Dag templates an Airflow Variable, write
`{{ var.value.get('my_var', 'default') }}`, not `{{ var.value.my_var }}`. The
bare `var.value.<name>` form raises if the Variable isn't set — it does not
fall back to an empty string — so anyone who copies the example verbatim
gets an immediate crash. `.get()` with a default keeps the example runnable
out of the box while still demonstrating the Variable-driven templating
pattern.

Found in `example_llm.py`'s `{{ var.value.llm_cost_cap_per_task }}` (PR
#71403) — the repo defines that Variable nowhere, and no other provider's
example Dags use the bare form (0 hits). When writing or reviewing an
example Dag, treat any bare `{{ var.value.<name> }}` reference as a defect
unless that Variable is demonstrably defined elsewhere in the same example.
