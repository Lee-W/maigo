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
`get_ui_field_behaviour()` entirely"); this entry only adds the tripwire angle.

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
