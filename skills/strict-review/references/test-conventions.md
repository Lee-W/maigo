# Strict Review — Test Conventions (Extended)

Loaded on demand by `skills/strict-review/SKILL.md` — **expanded rationale
and recipes for test-writing / test-review conventions that recur often
enough to be named**. Read this file when reviewing or writing tests and one
of the patterns below applies.

---

## Default new tests to parametrize, and extract repeated setup/cleanup into a fixture

When delivering new tests, self-check two things before calling it done:

- **≥2 tests whose bodies differ only in input/expected value** → merge into
  `@pytest.mark.parametrize`. Write each case's reason for existing (especially a
  regression-guard rationale) above the `pytest.param(...)` line — don't leave it in a
  docstring that disappears once the tests are merged.
- **Repeated setup/cleanup across tests** → extract to a fixture. Look for the repo's
  existing shared helper first (e.g. Airflow's `tests_common.test_utils.db.clear_db_*`)
  rather than writing a fresh `session.execute(delete(...))` per test.

Don't force tests with genuinely different body **structure** (a multi-step sequence,
a mid-test rollback or state change) into the same parametrize — that turns into a pile
of `if`/`else` branches, harder to read than separate tests.

How to apply: this is a delivery self-check, not something to wait for a reviewer to
ask for — apply it before handing the tests over. When reviewing, treat "should this
have been parametrized / had its setup extracted to a fixture" as part of convention
conformance, not an optional nit.

---

## Prefer `.mock_calls` equality over `assert_called_once_with`

Default to comparing `.mock_calls` against a list of `mock.call(...)` objects
rather than using `.assert_called_once_with(...)`. Focus on the specific
child mock (`m.method.mock_calls`) rather than the root (`m.mock_calls`), so
the assertion stays on the call you care about and doesn't drag in unrelated
method dispatch.

```python
# Preferred
assert runner._log.error.mock_calls == [
    mock.call("dag_model.next_dagrun_partition_key is None; expected str", dag_id="x"),
]

# Not preferred
runner._log.error.assert_called_once_with(
    "dag_model.next_dagrun_partition_key is None; expected str", dag_id="x",
)
```

The list-equality form makes the expected and actual values directly
comparable in pytest's diff output and lets you express "called exactly
once, with this exact signature, and nothing else on this child" in one
assertion.

How to apply:

- When writing new tests against a `MagicMock` / `mock.patch` target,
  default to `assert mock_obj.method.mock_calls == [mock.call(args)]`.
- Pick the child-mock form (`m.method.mock_calls`) when the test is about one
  specific method; pick the root form (`m.mock_calls == [mock.call.method(args)]`)
  only when you also want to assert "no other method was called on the
  parent".
- For `LoggingMixin`-derived classes (where `self.log` is a property backed
  by `self._log`), preload the cache instead of patching the property:
  `instance._log = mock.MagicMock()` before the action, then assert on
  `instance._log.<level>.mock_calls` after. See "Log assertion when the log
  IS the observable behaviour" below for the `LoggingMixin` specifics.

---

## Assert on the full sequence, not head + tail

When a test asserts on iterable output (window expansion, generated keys,
list-returning routes), prefer full-sequence equality over head/tail spot
checks:

```python
# Preferred
assert list(HourWindow().to_upstream(period_start)) == [
    datetime(2024, 6, 10, 14, m) for m in range(60)
]

# Not preferred
members = list(HourWindow().to_upstream(period_start))
assert len(members) == 60
assert members[0] == datetime(2024, 6, 10, 14, 0)
assert members[-1] == datetime(2024, 6, 10, 14, 59)
```

The same applies to multi-element response collections — assert across every
element via list comprehension, not on `items[0]`:

```python
# Preferred
assert [a["is_rollup"] for a in assets] == [True, True]

# Not preferred (loses coverage when len(assets) > 1)
assert assets[0]["is_rollup"] is True
```

A head/tail/length check passes a regression that flips any interior value
(e.g. a timezone-arithmetic bug, an off-by-one in window generation).

How to apply:

- When the expected output is a fixed-length sequence, build the full
  expected list (often via comprehension) and use `==`.
- When testing multi-element responses, broaden via list comprehension
  (`[a["field"] for a in items]`) — and use a multi-element fixture so the
  assertion has something to span.
- Order matters: for `frozenset` outputs, compare against a `frozenset(...)`
  comprehension; for ordered iterables, compare against a list. Pick the
  type that pins the contract.

---

## Numeric caps need an at-cap + one-over-cap test pair

A single test on the trip path (e.g. `cap=2`, `fanout=7` → skipped) does not
distinguish `>` from `>=`. A regression that flips the comparator passes the
same test. Pin the boundary explicitly with a pair:

```python
# At-cap is allowed: cap=7, fanout=7 → all 7 rows queued, no log entry
@conf_vars({("scheduler", "partition_fanout_max_keys"): "7"})
def test_partition_fanout_at_cap_is_allowed(...):
    ...
    assert count(AssetPartitionDagRun) == 7
    assert count(Log, event="partition fanout exceeded") == 0

# One-over-cap trips: cap=6, fanout=7 → 0 rows, 1 log entry
@conf_vars({("scheduler", "partition_fanout_max_keys"): "6"})
def test_partition_fanout_one_over_cap_trips(...):
    ...
    assert count(AssetPartitionDagRun) == 0
    assert count(Log, event="partition fanout exceeded") == 1
```

Applies anywhere a numeric threshold gates behaviour — caps, retry limits,
batch sizes, age cutoffs.

How to apply:

- For any new cap-gated code path, write the trip test plus a same-shape
  "at-cap is allowed" companion.
- If a test uses a cap far below the trip point (e.g. `cap == N - 5`),
  suggest tightening to `cap == fanout` and `cap == fanout - 1` so the
  inequality direction is actually pinned.
- The pattern generalises beyond `>`: for `>=` use `cap=N` (trips) and
  `cap=N+1` (allowed); for `<` use the mirror.
- Same shape for a `max(floor, x)` / `min(ceil, x)` clamp: a single case
  sitting exactly on the floor does not pin the clamp. Pair `x < floor`
  (clamps to `floor`) with `x >= floor` (passes `x` through).

---

## No thin one-use test helpers; assert only the decided value

Don't add thin helper functions to a test for one or two uses — e.g. a
wrapper around a single `datetime(...)` construction, or a builder that
reconstructs the full expected object and is then reused to build the
*input* too. Use module-level constants + inline literals instead. And
assert only the value the function under test actually decides, not a fully
reconstructed object — derived fields are often already covered by sibling
tests, so rebuilding them in the new test just adds an indirection that
obscures what's being pinned.

How to apply: default to module constants + inline literals in
`pytest.param`; in the assertion, pin the one field the branch logic
produces (e.g. `assert info.run_after == expected`) plus the `None` /
not-applicable case. Let sibling tests own the derived-field / round-trip
coverage. Reach for a helper only when it removes real, repeated complexity
— not to shave one line.

---

## Minimize forced churn on an existing test; add a new test for new behavior

When a behavior change forces an existing test to change, keep that
existing test's diff to the **forced minimum** — stay as close to the
original form as possible (same assertion style, only the values the change
actually moves) — and add a **separate, focused new test** for the new
behavior. Don't rework the existing test's assertions into a more elaborate
version "while you're in there."

A large rewrite of an existing test is easy to challenge in review and hides
what actually changed — a reviewer can't tell which part of the diff is
"forced by the behavior change" versus "opportunistic cleanup."

How to apply: diff the existing test against its prior form; revert any
assertion restructuring back to the original shape and change only the
forced values; put the genuinely-new behavior in a new named test (e.g.
`test_..._uses_timetable_timezone`) that asserts it directly.

---

## A missing fixture is not "can't test" — build one

A test/QA case that merely lacks a shipped example fixture (e.g. an example
Dag) is **not** "can't-test" or "deferred" by default. The default action is
to build the smallest purpose-built fixture and actually run it.

"Needs a fixture" and "cannot be verified" are two different things —
collapsing the former into the latter reads as giving up before trying the
straightforward option.

How to apply: only classify a case as deferred when it is genuinely
unit-level-unreachable, parse-time-only with no observable hook otherwise,
or requires infrastructure that doesn't exist yet. Otherwise build the
fixture: behaviour cases can share one importable file; parse-time negative
cases each need their own file (since the test is "does this fail to
import"). Verify the fixture actually parses/runs before claiming it's
ready.

---

## Log assertion when the log IS the observable behaviour

Airflow's `AGENTS.md` guidance ("Do not use `caplog` in tests, prefer
checking logic and not log output") is a *preference for behaviour checks
over log scraping*, not a blanket ban on log assertions. When a code path's
stated purpose is "skip and explain to the operator," the log entry **is**
the observable behaviour, and dropping the log assertion drops the test's
value.

The cleanest way to verify it: mock the logger directly and assert on the
call signature via `.mock_calls` (see "Prefer `.mock_calls` equality" above),
instead of substring-matching `caplog.text`.

```python
# LoggingMixin.log is a @property backed by self._log — preload the cache to mock.
runner._log = mock.MagicMock()
with mock.patch.object(runner, "_get_current_dag") as mock_get_dag:
    runner._create_dag_runs([dag_model], session)

mock_get_dag.assert_not_called()
assert runner._log.error.mock_calls == [
    mock.call("dag_model.next_dagrun_partition_key is None; expected str", dag_id="..."),
]
```

Dropping a `caplog.text` assertion outright — reading "no caplog" as "don't
assert on logs at all" — is a misreading of the rule. If the test exists to
prove a scheduler (or other component) tells the operator *why* it skipped,
a mock-only check that never inspects the log call leaves the
operator-visibility invariant unverified. The fix is structural (mock the
logger, assert on call args), not deletion.

How to apply:

- Ask "is this log entry part of the contract this test exists to defend?"
  before dropping a `caplog`-style assertion. If yes, replace it with logger
  mocking — don't delete it.
- For `LoggingMixin` (where `.log` is a `@property` with no setter), set
  `instance._log = mock.MagicMock()` directly —
  `mock.patch.object(instance, "log")` fails with "property has no
  deleter".
- Use the `.mock_calls` form: `assert instance._log.error.mock_calls == [mock.call(msg, kw=v)]`.
- The blanket "no caplog" rule still applies to the common case where a test
  scrapes log text to verify behaviour that could be verified directly (a
  state change, a return value, a side-effect on a model). The exception is
  operator-visibility — diagnostic logs that have no other observable
  channel.

---

## Prefer pytest style over `unittest.TestCase`

Write tests in pytest style — module-level functions with plain `assert`,
not classes inheriting `unittest.TestCase` with `assertEqual`/`assertTrue`/
`assertIn` methods.

Why: the user explicitly asked for tests to be written in pytest style
(plain `assert` + fixtures), not `unittest.TestCase` / `assertEqual` and
friends — this is a stated preference, not a house style invented for this
guide.

```python
# Preferred
def test_parses_valid_config():
    result = parse_config(SAMPLE)
    assert result.name == "x"

# Not preferred
class TestConfig(unittest.TestCase):
    def test_parses_valid_config(self):
        result = parse_config(SAMPLE)
        self.assertEqual(result.name, "x")
```

How to apply:

- Assert with plain `assert x == y` / `assert cond`, not `assertEqual` /
  `assertTrue` / `assertIn` and friends.
- Use fixtures (`tmp_path`, `monkeypatch`, `@pytest.fixture`) instead of
  `setUp`/`tearDown` and `mock.patch` context managers.
- Write tests as module-level functions, not `unittest.TestCase` subclasses.
- If the repo's runner is still `unittest discover`, migrating requires more
  than the test files themselves: add pytest as a dev dependency, set
  `[tool.pytest.ini_options]` (usually `pythonpath = ["."]` so imports
  resolve — `unittest discover` relies on cwd for that instead), and switch
  CI from `unittest discover` to `uv run pytest` (or the repo's equivalent).

---

## `MagicMock(spec=[])` does not guarantee attribute absence

`MagicMock(spec=[])` means "mimic an empty list's interface" — it does not
mean "no attributes." `dir([])` is what `MagicMock` actually consults to
decide which attributes are allowed, so `spec=[]` behaves like "the full set
of `list` attributes," not an empty spec. Relying on it to make
`getattr(mock, "attr", default)` fall back to `default` is unreliable across
mock versions.

How to apply: to make a specific attribute genuinely absent from a mock, use
`MagicMock(spec=["allowed_attr_1", "allowed_attr_2"])` — list the attributes
that **should** be present. `hasattr(mock, "missing_attr")` then reliably
returns `False` for anything not in that list.

---

## Tests must not fire real external side effects

Tests must never trigger real external side effects — system notifications,
subprocess calls, writes to the user's home directory / config files. Any
code path in the system under test that can cause a side effect must be
mocked or no-op'd, with an **autouse fixture** as the module-level backstop
so the whole test module defaults to hermetic.

Why: an integration-style test (one that constructs an app object and drives
a reload/refresh path) is the easiest place to accidentally hit a real side
effect, because the code path that fires it usually isn't the thing being
directly tested — it's incidental to building the test fixture. A test that
builds an app and calls its reload path, without mocking the notification
call inside it, can end up sending a real OS-level notification on every
test run; running the failing test repeatedly during debugging multiplies
into a pile of real notifications with no test-level indication anything is
wrong.

How to apply:

- Integration-style tests (constructing/mounting/reloading an app object) are
  the highest-risk spot for incidental real side effects — add an autouse
  fixture in that test module that no-ops the side-effect entry point (e.g.
  `monkeypatch.setattr(app_module, "send_notification", lambda *a, **kw: None)`).
- Don't let tests depend on the machine's real config file (`~/.config/...`);
  inject a default config object via an autouse fixture instead, otherwise
  test behavior drifts whenever the local user's config changes.
- An unexplained side effect outside the test itself (a stray notification, a
  file that changed) is a signal to suspect the test suite hit a real code
  path — check for a missing mock before assuming the environment is at
  fault.
