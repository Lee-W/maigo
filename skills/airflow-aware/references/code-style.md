# Airflow code-style conventions (repo-specific)

Loaded on demand by `skills/airflow-aware/SKILL.md` — style conventions that
only hold inside an Airflow checkout (optional-extra import guard, naming,
provider hooks, maintainer preferences, Dag authoring). Read this file when
writing or reviewing Python in an Airflow checkout and one of the topics below
applies.

General Python style (import placement, aliasing, validation posture, mypy
narrowing, docstrings, `ContextVar` in async generators) is in
[`python-aware/references/code-style.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/code-style.md);
this file only adds what Airflow does differently or on top.

This file covers **static** style — conventions a reader or a linter can
check without running the code. For **execution-time** gotchas (attrs
eq/hash conventions, serialization field-read conventions, scheduler/session
lifecycle traps), see
[`references/runtime-gotchas.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/runtime-gotchas.md);
for Python/pydantic version-skew type-system pitfalls, see
[`python-aware/references/runtime-gotchas.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/runtime-gotchas.md).

## Imports

### An optional-extra import guard goes first, and takes that SDK's type imports with it

Scope: a provider module that depends on an optional extra, i.e. the import is wrapped
in `try: ... except ImportError as e: raise AirflowOptionalProviderFeatureException(e)`.

Put the whole `try` block directly under `from __future__ import annotations`, before the
stdlib and `airflow` imports, so a missing extra fails at the very start of the module
instead of after unrelated imports load. Put that SDK's type-only names (config / message
types) inside the same `try` rather than splitting them into a `TYPE_CHECKING` block —
one place to look for everything the extra provides. An example Dag that depends on the
extra imports it at the top of the file too, not inside the task function. ruff's
E402 and isort do not flag this ordering.

## Naming and constants

### Sphinx `#:` attribute-doc comments aren't a repo idiom

Use a plain `#` comment, not Sphinx's `#:` variable-documentation syntax, on
module-level constants too — especially `_`-prefixed private ones — not just
class attributes. `#:` exists to make autodoc pick up the following variable
as a documented public attribute; internal/private constants are never
collected by autodoc in the first place, so `#:` has no actual effect there
and only leaves two comment styles coexisting in the same file. Case: within
one PR, in the same hook file, two private constants used `#:` while a third
one added later used plain `#`. The only exception is when you've actually
confirmed a public attribute/constant should be picked up by autodoc.

### Name functions and methods with action verbs — private helpers too

AGENTS.md requires an action-verb prefix on every function and method name
(`get_`, `extract_`, `find_`, `compute_`, `build_`, etc.) — a noun-only name
reads as an attribute, not a callable. The rule applies to `_`-prefixed
private helpers exactly as much as public ones: AGENTS.md's own
counter-example, `_serialize_keys`, is itself private. `_model_key(step)` →
`_build_model_key(step)` is the same defect — the name states *what the
return value is*, not *what the function does*.

The only exception is a predicate (`is_`, `has_`), which correctly reads as
an attribute-shaped boolean. Dunder methods (`__init__`, `__eq__`) and
pytest test functions (`test_*`) sit outside this rule's scope entirely,
not inside it as an exception.

When reviewing, check every `def` in the diff's new/changed lines — inner
functions and test helpers included, not just top-level module functions. A
private helper introduced deep inside a larger diff is the easiest place
for a noun-only name to slip past review; don't grant private names a free
pass just because they're private.

**When delegating the work**: copy this rule verbatim into the implementer's brief and add "check every added or copied method name against it; a sibling file that already uses a noun-style name is not precedent". The same sibling files often violate the rule themselves, and copying them reproduces the violation (apache/airflow #74695: new `_tool_name` methods copied from `ObjectStorageToolset` and `SandboxToolset`, which the reviewer also missed). In the reviewer's brief, make the naming item scan **every `def` the diff adds**, and keep the exemption list to names a framework really dictates (for example a pydantic-ai property such as `tool_name_conflict_hint`), so the reviewer does not end up checking only the exempt names. When a sibling file turns out to violate the rule as well, ask the user whether to rename it in the same change.

### Provider module names don't repeat the provider prefix (AIP-21)

AIP-21 dropped the provider prefix from module names inside a provider package:
`providers/snowflake/.../hooks/cortex_model.py`, not `snowflake_cortex_model.py`. Name new modules
this way from the start. If the module is still unreleased, a plain `git mv` fixes it (carry the
rename through `provider.yaml`, `get_provider_info.py`, and test imports / `mock.patch` paths);
once released, the rename needs a deprecation cycle. (apache/airflow #73932, where the maintainer
cited the same review given on `snowflake_cortex_agent.py` in #73815.)

The same sweep applies when you delete, rename, or stop importing any module-level name: before
removing it, grep the whole of `providers/` for a `mock.patch("<dotted.path>.<name>")` that targets
it (`grep -rn '<name>\b' providers --include='*.py'`, glob quoted). Tests in a *different* provider
often patch it, and running only the owning provider's tests will not show it; the failure
(`AttributeError` on patch) surfaces only in the Non-DB providers and LowestDeps CI jobs.

### A new helper module that isn't public gets a `_` prefix

A new module that only the same provider imports (e.g. `utils/_rest_auth.py`) is named `_xxx.py`
so it is neither public interface nor a compatibility commitment. Precedent:
`elasticsearch/_compat.py`, `common/compat/_retry_policy.py`; its test file is `test__xxx.py`.

Once private, change other docstrings that point at it from `:class:` to a literal
``` ``ClassName`` ```: sphinx-autoapi without `private-members` generates no page for a
`_`-prefixed module, so `:class:` becomes an unresolvable reference (docs are not nitpicky, so
nothing errors — the link just silently isn't there). (apache/airflow #73932.)

## Provider hooks

### A hook must not fetch credentials while building a model

`PydanticAIHook.get_conn()` (common.ai) eagerly builds a model for every fallback in
`_resolve_fallback_models`. If a subclass's `_get_provider_kwargs` does network token fetching, a
broken token endpoint on a *fallback* fails the task before the healthy primary is even called; on
the *primary* the failure lands outside `FallbackModel`'s `ModelAPIError` path, so the fallback
chain cannot catch it.

How to apply: when the provider constructor needs a non-empty token, pass a placeholder and put
the real token in per-request auth (e.g. overriding `Authorization` in an httpx
`Auth.auth_flow`); prove credential validity by overriding `test_connection` (call `super()`, then
fetch a token once). For lazily initialised cached attributes, build them in locals and assign all
of them only after every one succeeded — otherwise a half-initialised state is reused by the next
call. (apache/airflow #73932, `PydanticAISnowflakeHook`.)

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
breaking change instead. **"Shipped" is decided by PyPI, not by local tags**:
`curl https://pypi.org/pypi/<dist>/json` and read `releases` / `upload_time`
(local tags can stop at `1.0.0rc3` while `1.0.0` is already published). For a
stable-listed toolset/operator, deleting a deprecated alias or changing a
type/default after the stable release is breaking — keep it until the next
major. Case: #74695 removed `HookToolset.tool_name_prefix` and described it under
the 1.0.0 changelog section; a maintainer pointed out 1.0.0 was already on PyPI,
and the removal was reverted entirely. When moving the code, carry over every
`why` from the original docstring to its new home — don't leave bare logic
behind.

### Adopting a core/task-sdk symbol: verify it exists at the provider's declared floor

A provider must support the **oldest** core version declared in its own
`pyproject.toml`. Before adopting any core or task-sdk symbol —
**especially one a reviewer suggests** — verify it exists at that floor
version; otherwise it raises `AttributeError`/`ImportError` only when a user
runs the provider against an old core, with an error far removed from the
actual cause. Local tests don't catch this (the local environment has the
newer core installed).

Three checks, all required:

1. `git log -S '<symbol>' --oneline -- <path>` — find the commit that
   introduced it.
2. `git tag --contains <commit> | sort -V | head` — find its earliest tag.
   **Insufficient alone** — the earliest tag can be a pre-release like
   `3.3.0b1`.
3. `git show <floor-tag>:<path> | grep '<symbol>'` — confirm presence or
   absence **at the actual floor tag**.

Read the floor from the provider's own `pyproject.toml` (e.g.
`apache-airflow>=3.0.0`) — don't assume a provider tracks the same version
as core.

A reviewer suggesting a symbol read source on `main`; that doesn't mean the
floor has it. If the floor genuinely lacks it and the capability is worth
the cost, gate behind an existing version-compat flag pattern (e.g.
`providers/common/compat/.../version_compat.py`'s `AIRFLOW_V_3_3_PLUS`) —
but ask whether the version branch is worth it before defaulting to the
reviewer's literal suggestion. A second signal worth flagging on its own:
adopting an underscore-private cross-package symbol (a provider reaching
into task-sdk's `_foo`) swaps one private dependency for another even when
the version check passes — if the original motivation was avoiding a hook's
private members, reaching into a class's own private cache is usually
cleaner than reaching into another package's private internals.

Case: apache/airflow #72156 — a reviewer suggested `_preset_connections`;
`git log -S` traced it to a commit first tagged at `3.3.0b1`, and
`git show` against `3.1.0`/`3.2.0` confirmed it absent — but the provider's
floor was `apache-airflow>=3.0.0`. The fix seeded the hook's own cache
instead, which cut the same query count without a version gate.

For **provider tests and code that branch on a 3.3-only symbol** (and for the
rule that a test importing one must gate with `skipif(not AIRFLOW_V_3_3_PLUS)`
and keep the import out of module top level), see
[`verification-tooling.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/verification-tooling.md)
("Code that branches on a 3.3-only SDK symbol …").

## Validation and enforcement

### A fixed override of a base `@property` is a class attribute; "get or raise" is walrus + early return

Two maintainer-review preferences for Airflow code (the property one from #74695):

- **Overriding a base-class `@property` with a constant**: write a class attribute
  (`name: str = (...)`), not `@property def name(self)`. Follow the same file's
  existing `agent_template_fields: Sequence[str] = (...)` form, no `ClassVar`. A
  maintainer asked "does this need to be a property? one attribute is enough" about
  `tool_name_conflict_hint` on `SQLToolset`/`DataFusionToolset`, which return a fixed
  string. Before changing it, confirm the base only *reads* the attribute
  (pydantic-ai's `combined.py` does), and keep sibling classes consistent. Whether
  mypy accepts an attribute overriding a property is unverified — if in doubt, check
  with `uvx mypy` or CI.
- **"Fetch a value, raise if missing"**: success path as an early `return`, the
  `raise` at the tail, with a single walrus —

  ```python
  if command and (log_path := json.loads(command).get("log_path")):
      return log_path
  raise HTTPException(status.HTTP_404_NOT_FOUND, f"No log path found for callback {task.task_id}")
  ```

  not `log_path = ... if command else None` + `if not log_path: raise` + `return
  log_path`. It drops a `None` intermediate and one inverted check. Single walrus,
  single-level condition only; don't force it onto nested or multiple walruses.

## mypy

### Airflow note: widening a `template_fields` `Literal` to `str`

The general rule is in `python-aware/references/code-style.md` ("Widening a `Literal` to `str`
relocates the mypy error"). In Airflow the trigger is adding an operator field to
`template_fields` whose declared type is an SDK `Literal[...]`, so a Jinja-templated Dag value
type-checks. The only evidence that the widening is complete is
`uv run --project providers/<provider> mypy <changed files>` returning exit 0. The repo
convention is the `# type: ignore[arg-type]` at the SDK call (15+ existing sites under
`providers/*/src/airflow/providers/*/hooks/*.py`, e.g. `slack.py`, `docker.py`); `cast(...)` is
used only where the SDK exports a named alias (e.g. `anthropic.py`'s
`cast("agent_create_params.Model", ...)`).

## Tests

### Airflow note: `template_fields` is verified by rendering

The general rule is in `python-aware/references/test-conventions.md` ("Don't assert a class
attribute equals a literal"). For `template_fields`, assert the fields render as expected after
`operator.render_template_fields(context=...)` instead of comparing the tuple. If the deleted
literal assertion covered something the render test doesn't and that gap is pre-existing behavior,
leave it untested per this repo's "don't backfill tests for existing logic" convention; if the PR
introduced it, add a behavior test first.

Airflow reviewers push back on literal-equality assertions. Distinct from
[`references/docs-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/docs-conventions.md)'s
`.rst` spell-check entry — that one is about coined nouns in doc prose; the codespell trap for
deliberate misspellings in `.py` test values is in `python-aware/references/test-conventions.md`.

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
