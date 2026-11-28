# Airflow test cases (instances of the python-aware test conventions)

Loaded on demand by `skills/airflow-aware/SKILL.md` — **Airflow instances and
Airflow-specific facts** behind the language-level rules in
[`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md).
Each `##` heading below repeats the heading of the python-aware rule it
belongs to; read the rule first, then the case here. Read this file when
writing or reviewing Airflow tests.

---

## Verify before aligning a test to new production behavior

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#verify-before-aligning-a-test-to-new-production-behavior) — "Verify before aligning a test to new production behavior".

An Airflow remote-logging provider-dispatch migration dropped a conn-id
fallback; a test asserting the old fallback started failing, and rewriting it
to match the new (fallback-free) expectation looked like the obvious fix.
Confirmed correct only after tracing `AwsGenericHook.conn_config`'s truthiness
check — `aws_conn_id=""` is equivalent to `None` there (both fall through to
boto3's default credential chain), so dropping the fallback was actually safe.
Without that trace, "the test is green" would have been mistaken for "the
change is verified."

---

## Log assertion when the log IS the observable behaviour

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#log-assertion-when-the-log-is-the-observable-behaviour) — "Log assertion when the log IS the observable behaviour".

- **The repo rule**: Airflow's `AGENTS.md` says "Do not use `caplog` in tests,
  prefer checking logic and not log output" — a preference for behaviour
  checks over log scraping, not a blanket ban. When a code path's stated
  purpose is "skip and explain to the operator," the log entry is the
  observable behaviour.
- **`LoggingMixin`**: `LoggingMixin.log` is a `@property` backed by `self._log`
  with no setter, so `mock.patch.object(instance, "log")` fails with
  "property has no deleter". Preload the cache instead:

  ```python
  runner._log = mock.MagicMock()
  with mock.patch.object(runner, "_get_current_dag") as mock_get_dag:
      runner._create_dag_runs([dag_model], session)

  mock_get_dag.assert_not_called()
  assert runner._log.error.mock_calls == [
      mock.call("dag_model.next_dagrun_partition_key is None; expected str", dag_id="..."),
  ]
  ```

  The same `instance._log = mock.MagicMock()` form applies to any
  `LoggingMixin`-derived class when you want a `.mock_calls` assertion (see
  "Prefer `.mock_calls` equality over `assert_called_once_with`" in the rule
  file).
- **Structlog `caplog` is an exact match**: `StructlogCapture.__contains__`
  (`devel-common/src/tests_common/test_utils/logs.py`) compares strings with
  `e["event"] == target`. So `"only the prefix" not in caplog` is always true
  and the assertion is decorative (apache/airflow #71072: a reviewer caught
  three of these). Extract the full log message into one module-level
  constant and reuse it in every `in` / `not in` / `e.get("event") ==` check.
  Before writing or reviewing any `not in caplog`, confirm the string is the
  whole event, then run one mutation (make the log actually fire) to confirm
  the assertion turns red.
- **`"event" in caplog` breaks the compat jobs of a provider that supports
  older Airflow** (apache/airflow #76381): the structured assertion that
  `AGENTS.md` prefers works in `airflow-core` and `task-sdk`, but a provider
  is also tested against released Airflow versions (the 2.11.1 and 3.0.6
  compat jobs). Without `airflow.sdk._shared` the `caplog` override returns
  pytest's stock `LogCaptureFixture`, which has no `in`, so the test raises
  `TypeError` there while the local run on `main` stays green. When writing
  or reviewing a provider test whose code path runs on Airflow versions
  before that override, do not accept `in caplog`: assert through a mocked
  logger built with `spec`, or drop the log assertion when `pytest.raises`
  already pins the behaviour. Check the compat jobs in CI before treating a
  green local run as evidence. Does not apply to `airflow-core`, `task-sdk`,
  or a code path that only exists on the newer versions.

---

## Mocking the resolver removes the guard entirely

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#mocking-the-resolver-removes-the-guard-entirely) — "Mocking the resolver removes the guard entirely".

Airflow instance of "the drift tripwire must read the source runtime actually
consults": the connection UI's runtime source is `provider.yaml`'s
`conn-fields`. When that is present, the hook's `get_ui_field_behaviour()` is
never called (`providers_manager.py`'s `ui_metadata_loaded` gate — that path
is deprecated since 3.2.0), so a tripwire built on
`get_ui_field_behaviour()["placeholders"]` guards a string nobody's form ever
shows. The gate itself is written up in
[`registry-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/registry-conventions.md)
("`provider.yaml`'s `ui-field-behaviour`/`conn-fields` override the hook's
`get_ui_field_behaviour()` entirely"); this entry only adds the tripwire angle. That section also
records that a repo-level check (`check_ui_field_behaviour_matches_hook`) already compares the hook
with `provider.yaml`, so a new unit test asserting the same thing is a duplicate.

---

## Parity tests need a one-sided mutation, not just "break both"

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#parity-tests-need-a-one-sided-mutation-not-just-break-both) — "Parity tests need a one-sided mutation, not just "break both"".

In apache/airflow #71477, `test_readers_agree_on_which_pages_are_guides`
(working-tree reader vs git-tag reader) was only shown to discriminate by two
one-sided mutations: dropping the filter on the `extract_parameters` side
only (worktree gains 3 keys, tag side unchanged), then on the
`extract_versions` side only. The "shared predicate always returns `True`"
mutation only proves the predicate is used.

---

## Wire-contract tests keep string literals

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#wire-contract-tests-keep-string-literals) — "Wire-contract tests keep string literals".

Airflow's serde (`task-sdk/src/airflow/sdk/serde/__init__.py`) takes `.value`
explicitly, so the DB stores a plain string and reads back a plain `str`;
existing tests keep passing after a `str` Enum is introduced.
Case: apache/airflow #72149, `TerminationReason` in the openai provider.

---

## A key that decides resource sharing needs one test per component

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#a-key-that-decides-resource-sharing-needs-one-test-per-component) — "A key that decides resource sharing needs one test per component".

In apache/airflow #68625 the shared stream key could lose `kafka_config_id`
with all tests still green; the fix was
`test_shared_stream_key_separates_topics_and_connections`. (Single-PR
evidence so far.)

---

## Tests for "old behaviour removed" must use the real value from the previous release

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#tests-for-old-behaviour-removed-must-use-the-real-value-from-the-previous-release) — "Tests for "old behaviour removed" must use the real value from the previous release".

A test Dag used `pydantic-ai-azure` as the "old conn_type", but the previous
release's `provider.yaml` actually said `pydanticai-azure`; the negative half
returned `Unknown hook type` on every version and even passed one
fresh-context verification round before being caught.

---

## Paired fetch + count queries share one predicate helper, with a decoy test per predicate

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#paired-fetch--count-queries-share-one-predicate-helper-with-a-decoy-test-per-predicate) — "Paired fetch + count queries share one predicate helper, with a decoy test per predicate".

apache/airflow #71072: the scheduler's partitioned-asset count omitted
`is_paused` / `is_draining`, so paused Dags inflated the backlog and raised
false alarms. The fix extracted one verb-named helper returning the predicate
tuple (`_build_pending_partitioned_apdr_filters`) used with `.where(*...)` in
both queries, plus one decoy test per predicate. Mind DB constraints when
flipping the flags — `is_paused` and `is_draining` cannot both be set
(`CHECK NOT (is_paused AND is_draining)`). The same PR's capped, row-locked
fetch is covered in `review-checks.md` (10.16 / 10.17).

---

## Inserting a new test class between a decorator and its class steals the decorator

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#inserting-a-new-test-class-between-a-decorator-and-its-class-steals-the-decorator) — "Inserting a new test class between a decorator and its class steals the decorator".

apache/airflow #74396: new classes were inserted between a
`skipif(not AIRFLOW_V_3_1_PLUS)` and the class it guarded; the local run
(Airflow 3.3+) was fully green, and only the old-version compat jobs went red
(`module 'airflow' has no attribute 'sdk'`), 18 tests across two jobs. See
also the `<3.3` compatibility note in `verification-tooling.md` (#74396,
#74695).

---

## Asserting on a very large string: split into short assertions that never diff the big object

Rule: [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md#asserting-on-a-very-large-string-split-into-short-assertions-that-never-diff-the-big-object) — "Asserting on a very large string: split into short assertions that never diff the big object".

apache/airflow #74026 (reviewer measurement): with the surrogate guard under
test removed, the whole-string comparison took about 8 minutes under breeze to
fail (CI's limit is 60 seconds), because pytest diffed two ~250,000-character
strings; after the split, removing the guard turned the `set(kept[1:])` line
red in 2.5 seconds.

---

## Tests expecting a model to be dumped to a dict must gate on the deserialization walker

Airflow-only case (no python-aware counterpart).

After changing how `providers/common/ai` dumps structured output to XCom (`serialize_output`, `output_type`), a test that expects a **nested or unregistered** model to become a dict must carry `requires_typed_xcom` (or that file's `requires_walker`).

Why: Airflow 3.1 / 3.2 task-sdk has `airflow.sdk.serde` but **no deserialization walker** (`iter_pydantic_models`), so the operators there deliberately push the instance. 2.11 / 3.0 have no serde at all, so every existing gate skips on them — a green 2.11 / 3.0 job says nothing about 3.1 / 3.2.

Do not over-gate: a **top-level** model is still `model_dump()`ed there because `_serialize_model_output=True`, so a test expecting a dict for it is correct without the gate.

apache/airflow #74695: Compat 3.1.8 / 3.2.2 went red on the `list-in-output-marker` parameter of the HITL tests in `test_agent.py`, which expected a dict for a nested model.

---

## DST / fold tests must include non-whole-hour zones (Lord_Howe, Troll)

Scope gate: only when the diff touches `airflow-core/src/airflow/timetables/` or other DST / fold logic.

A DST test suite built only from whole-hour-shift zones (Europe/Berlin, America/Chicago) cannot catch a threshold written as "a wall-clock gap under one hour never crosses a DST change". Add at least:

- `Australia/Lord_Howe` — a 30-minute DST shift, so sub-hour gaps do cross it.
- `Antarctica/Troll` — a 2-hour fold; per tzdata 2020–2030 it is the largest pure DST shift (Casey's 3-hour change is a standard-time re-definition, not DST).

apache/airflow #75847: a maintainer review caught the "gap under one hour never crosses DST" threshold with Lord_Howe, which the existing whole-hour zones had all passed.

---

## DB tests: no hard-coded primary keys, and all three backends run the whole file

Airflow-only case (no python-aware counterpart). Applies when a change touches SQL semantics,
primary-key or sequence numbering, or rows that a test leaves behind. Source: apache/airflow #69849,
where the first CI failure was MySQL-only and the fix then failed on Postgres.

### Do not hard-code primary keys or depend on other rows in the table

- A scheduler test hard-coded event ids 1000 and 2000, while the code under test used a table-wide
  `max(id)` as its upper bound. Earlier tests in the same module committed events that their cleanup
  could not delete; on a backend whose auto-numbering never goes back, the leftover ids passed 2000,
  the bound rose, and the test failed only in the MySQL job while local SQLite stayed green. The
  reviewer asked for both sides to change: the test must not depend on a fixed id, and the code
  must not scan the whole table.
- When writing or reviewing a DB test, for every hard-coded primary key ask: "if the table already
  holds a row with a larger id, does this assertion still hold?" Module-level tests have no
  class-level table-clearing fixture, so they pick up leftovers most easily.
- Fix such a test by letting it create the foreign condition itself (for example insert an unrelated
  row with the largest id), so it pins the behaviour deterministically on every backend instead of
  passing by luck.
- Do not read the current `max(id)` and add to it either. An explicit id larger than anything the DB
  has handed out does not advance a Postgres sequence, so when the table is not cleared, a later test
  that relies on auto-numbering collides on the primary key. (This is how the Postgres job failed
  after the first fix; MySQL and SQLite did not.) When the test needs an id that is "smaller but
  inserted later", insert a placeholder row so the DB assigns a number, note its id, delete the
  placeholder once the larger id exists, and reuse that id.
- `session.scalar(select(func.max(...)))` is typed as possibly `None`, so arithmetic on it fails
  mypy; use `session.scalars(...).one()`.
- The production side follows the same rule: an aggregate such as `max()` over a user-data table is
  limited to the rows this operation concerns, not the whole table.

### Verify on SQLite, Postgres and MySQL, running the whole test file

- Before pushing a change in this area, run each backend:
  `breeze run --backend <sqlite|postgres|mysql> --python 3.11 pytest <the whole test file> -p no:randomly`
  (add `--mysql-version 8.0` for MySQL). Run them one after another, not in parallel, so two breeze
  instances never start at once.
- Run the whole file, not only the target test: in #69849 the tests that broke were two later tests
  in the same file, which a target-only run cannot show. Checking only the backend that failed moves
  the problem to the next backend.
- A backend marked "not verified" is not a state to push in. If a backend cannot run, tell the user
  before pushing.
- When delegating the verification, write the acceptance condition as one line per backend, judged
  by breeze's outer exit code and pytest's summary line. Case: #69849's first fix was pushed with
  Postgres marked "not verified", and the Postgres CI job then failed; all three supported
  databases have to be checked.
