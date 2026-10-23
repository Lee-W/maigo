# Airflow runtime gotchas (attrs, serialization, sessions)

Loaded on demand by `skills/airflow-aware/SKILL.md` and
[`references/code-style.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/code-style.md) —
execution-time defects that pass a type checker and a casual read but fail
against a specific SQLAlchemy version, Python version, or session lifecycle.
Read this file when writing or reviewing code that touches attrs eq/hash
conventions, (de)serialization field reads, or a `create_session`/scoped-session
boundary. Python/pydantic version-skew type-system pitfalls (`Annotated`
constraints, nested enums, subscripted generics, `Decimal`→`int`) live in
[`python-aware`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/runtime-gotchas.md).

---

## SDK definitions' attrs eq/hash convention: value objects vs key/ref types

In `task-sdk/src/airflow/sdk/definitions/`, the attrs eq/hash convention is
purposeful per-class, not uniform:

- **Value objects** (`Variable`, `Connection`, `AssetWatcher`, …) use plain
  `@attrs.define` — value-eq, and `__hash__ = None` (unhashable, since
  `@define` defaults to `eq=True, frozen=False`).
- **Key / ref types** used as dict keys or set members opt into hashability
  explicitly: `@attrs.define(frozen=True)` (`AssetUniqueKey`,
  `AssetAliasUniqueKey`) or `@attrs.define(hash=True)` (`AssetNameRef`,
  `AssetUriRef`, `AssetAlias`).
- **Special cases** define their own `__eq__`/`__hash__` — `Asset` hashes by
  its unique key via `@attrs.define(init=False, unsafe_hash=False)` plus
  custom dunders.
- **`eq=False` has zero precedent** across the SDK definitions — don't
  reach for it.

Decide first whether the type is a value object (→ plain `@attrs.define`,
accept unhashable) or a key/ref (→ `frozen=True` / `hash=True`) before
picking a decorator. This is also how the partition-mapper subclasses ended
up on plain `@attrs.define`: they're value objects, never used as keys (no
test or code hashes them). The corresponding core mappers are plain classes
(identity-eq) rather than attrs — that asymmetry with the SDK's value-eq is
accepted in this codebase (`Variable`/`Connection` aren't unified either);
symmetry here is about behavior, not mechanism.

A related attrs mechanic worth knowing: a class can keep a hand-written
variadic `__init__` while still being attrs, via `@attrs.define(init=False)`
plus a declared field and a call to `self.__attrs_init__(...)` inside the
custom `__init__` — so "attrs can't do `*args`" only means attrs can't
*generate* such an init, not that the class can't be attrs at all.

## Serialize side writes unconditionally → decode side reads with `data[key]`, not `.get()`

A field the **serialize side always emits** is read on the **decode side**
with direct `data["key"]` — a missing key then raises `KeyError`, i.e. fails
loud. Only fields the encoder writes **conditionally** are read with
`var.get("key", default)`.

Examples from the codebase: `decode_asset` reads `name`/`uri`/`group`/`extra`
directly but `watchers`/`access_control` with `.get(...)`, matching
`encode_asset_like` writing the first four unconditionally in the dict
literal and the latter two only inside `if` branches. `decode_deadline_alert`
reads the required structural fields (`REFERENCE`/`INTERVAL`/`CALLBACK`)
directly, and on a missing `interval` raises a `ValueError` that names the
downgrade cause explicitly — it does **not** silently substitute a default;
only the genuinely optional `name` uses `.get`. Core `serialized_objects.py`
follows the same pattern: `dag_id`, `task_type`, `_task_module`,
`_operator_name` are all direct `encoded[...]` reads.

**Don't add a defensive `else <default>` fallback for a field the serialize
side guarantees to write** (e.g. `RollupMapper.__init__` normalizes
`wait_policy=None` → `WaitForAll()`, so `serialize()` always emits it) — the
fallback masks data corruption as a valid value instead of surfacing it. If
a required field can genuinely go missing, fail loud with a clear error
message (see `decode_deadline_alert`'s `interval` case above), rather than
documenting the gap as a known limitation — the same posture as
[`python-aware/references/code-style.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/code-style.md)'s
"Raise at construction instead of documenting a structural footgun."

## Scheduler session lifecycle: scoped sessions, an escaping exception, and a per-tick event-listener trap

Three facts chain together into one story (all from the same audit-log
case, apache/airflow PR #64571 — logging a misconfigured rollup mapper):

**1. `create_session(scoped=True)` (the default) hands back the thread-local
shared session — an inner write can commit/close the outer caller's
session too.** `airflow.utils.session.create_session(scoped=True)` returns
the same session a scheduler tick's outer caller is already using; a
`with create_session() as s:` block nested inside that tick gets the
*same* session object, and committing/closing it commits/closes the outer
one too — any APDR/DagRun attached to the outer session can become
detached, raising `InvalidRequestError: Instance '<...>' is not persistent
within this Session`. When a write must land even if the outer
`@retry_db_transaction` rolls back (an audit-log row is the motivating
shape), pass `scoped=False` to get `settings.NonScopedSession()` — a
genuinely separate session on its own connection. Pair it with eagerly
extracting any ORM attributes the new session needs
(`target_dag_id = apdr.target_dag_id`) so it never lazy-loads through the
outer session's instance.

**2. That extra connection can raise an exception your `except` clause
doesn't catch.** `sqlalchemy.exc.TimeoutError` (raised on pool exhaustion —
`QueuePool limit ... connection timed out`) inherits directly from
`SQLAlchemyError`, **not** from `DBAPIError` or `OperationalError`
(verified MRO: `['TimeoutError', 'SQLAlchemyError', 'HasDescriptionCode',
'Exception', 'BaseException', 'object']`). So `except OperationalError:`
does not catch it, and neither does Airflow's `@retry_db_transaction`
(`airflow/utils/retries.py`), which only catches `(DBAPIError,
StaleDataError)` — a pool-exhaustion error from an independent
`create_session(scoped=False)` write propagates all the way out of the
scheduler tick unless caught explicitly:

```python
from sqlalchemy import exc
from sqlalchemy.exc import OperationalError
...
except (OperationalError, exc.TimeoutError):
```

Qualify it as `exc.TimeoutError` — a bare import would shadow the builtin
`TimeoutError`, and aliasing it is the wrong fix (don't alias an import
unless a module-qualified reference is genuinely impossible — see
[`skills/strict-review/references/recurring-patterns.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/recurring-patterns.md)'s
"Don't alias imports" section). `from sqlalchemy import exc` is the
established form in airflow-core (`assets/manager.py:97`).

**3. The scheduler's session is one object reused for the whole job — not
per tick — so a `once=True` session-event listener silently stops firing
after its first registration.** `airflow.settings.Session` is a
`scoped_session`, and `SchedulerJobRunner` calls `Session.remove()` only
once, when the whole scheduler job ends — not per tick. Every
`with create_session() as session:` inside `_do_scheduling` therefore hands
back the **same underlying Session object** for the process's lifetime.
Two traps follow: `event.listen(session, ..., once=True)` de-duplicates by
*callable equality*, and a bound method (`self._some_handler`) compares
equal across registrations — on the same session object the first
registration fires, every later re-registration is accepted
(`event.contains()` returns `True`) but **never invoked** (verified with a
standalone `create_engine("sqlite://")` PoC and reproduced in
`test_scheduler_job.py`; no listener leak — `dispatch.after_rollback.listeners`
stays at length 1, this is purely a correctness trap, not a resource leak).
And anything keyed to "this session's lifetime" is actually keyed to "this
scheduler process's lifetime."

**How to apply**: don't reach for session events to make per-tick state
survive a rollback — use an independently-committed session instead
(point 1), and if that extra connection must not take down the tick, catch
both exception types (point 2). There is then no rollback coupling left to
compensate for with an event listener (point 3).

## `dict(session.execute(stmt))` raises `TypeError` on SQLAlchemy 2.0.51 — `Result` has `.keys()`

Turning a two-column `select()` into a dict with
`dict(session.execute(stmt))` fails on the SQLAlchemy version pinned in
apache/airflow (2.0.51): `TypeError: 'ChunkedIteratorResult' object is not
subscriptable`. Cause: `Result` exposes `.keys()`, so Python's `dict()`
constructor takes the **mapping** protocol path and tries `obj[key]`
instead of iterating `(key, value)` pairs.

Fixes, in repo-preference order:

1. Dict comprehension unpacking the `Row` — the shape already used across
   this repo (`jobs/scheduler_job_runner.py`, `models/dagrun.py`):
   `{k: v for k, v in session.execute(stmt)}`.
2. `dict(session.execute(stmt).all())` — works, but the comprehension reads
   better and passes mypy without an extra annotation (a bare `dict(...)`
   trips `var-annotated` + `arg-type`).

**A reviewer's suggested code snippet can carry this exact bug too** — it
appeared verbatim in a committer's suggested code on PR #71072, so copying
a `suggestion` block wholesale isn't safe; run it before trusting it (same
posture as
[`skills/harness-discipline`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/SKILL.md)'s
guidance on verifying per target rather than trusting a conclusion).
