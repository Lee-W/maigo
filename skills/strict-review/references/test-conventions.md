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

## Tests touching global state must reset themselves

A test that registers or mutates **process-global state** (a secrets masker, logging
config, an environment variable, a module-level cache, a signal handler) is
responsible for resetting that state itself — don't assume a fixture or a sibling test
in the same module will handle it.

Criterion: pull the test out to run alone, or move it to run last in its module — does
the result change? If yes, it's missing a reset.

Why: this class of state is a process-wide singleton, not rebuilt per test function.
Without an explicit reset, pass/fail depends on execution order relative to other tests
in the module — green in isolation, red once something reorders the suite (a new test
added nearby, `-p no:randomly`) — and the test that goes red is often a **sibling**,
not the one missing the reset, which makes it hard to attribute.

How to apply: when a test needs to touch global state, reset it explicitly (before use,
and/or via a local teardown) rather than relying on suite ordering. Match whatever
reset pattern sibling tests in the same file already use.

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

## Prose-guard tests need a bounded window and both directions

Tests that guard "does this documentation section list the right N items"
have three independent gaps — any one of them lets the test look like a
guard while actually passing a broken edit:

1. **Unbounded slice.** Extracting the section via `text[start:]` (no upper
   bound) cuts from the marker to the **end of the file**, not to the end of
   that section. Removing the item under test from that slice, then
   re-adding it anywhere further down the file, passes. If the section under
   test happens to be the last one in the file, this gap produces no visible
   symptom until something reorders the file later.
2. **One-directional assertion.** `all(item in section for item in
   expected)` only catches **under-listing** — an item silently dropped. It
   says nothing about **over-claiming** — the section naming an item it
   shouldn't. For a customer-facing page, over-claiming is usually the worse
   defect (a false claim, not just an omission).
3. **Red-only mutation check.** Confirming the test goes red when the
   guarded content is broken only proves the test isn't a no-op — it does
   not prove the test tolerates unrelated edits, i.e. that it hasn't been
   over-corrected into "any edit turns this red."

How to apply during review:

- For gap 1: the slice must stop at the **next same-level marker**, not run
  to EOF — `end = text.find("\n<next-marker>", start); text[start:] if end
  == -1 else text[start:end]`. Normalize whitespace before comparing
  (`" ".join(chunk.split())`), otherwise a name that wraps across a line
  break produces an unexplained failure.
- For gap 2: require a reverse assertion — `others = full_set - expected_set
  - {self}`; none of `others` may appear in the section. Before trusting a
  substring-based reverse check, verify the full set has no member that's a
  substring of another (e.g. `"AWS Bedrock"` ⊂ `"AWS Bedrock Mantle"`,
  `"OpenAI"` ⊂ `"Azure OpenAI"`) — if it does, require a boundary-aware match
  instead of bare substring.
- For gap 3: every red-mutation case needs a paired should-stay-green case —
  an edit that changes something adjacent but immaterial (reorders the
  section, adds an unrelated same-level item elsewhere) — and that case must
  still pass.
- Check all three independently. Passing two of the three while failing the
  third still leaves the guard useless in that one dimension. Related: the
  "Numeric caps need an at-cap + one-over-cap test pair" entry above is the
  same "pin both directions of a boundary" discipline applied to numeric
  thresholds instead of prose sections.

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

## Verify before aligning a test to new production behavior

When a test goes red because a **production** code path changed behavior (not because
the test itself has a bug), don't accept a code comment or "this looks intentional" as
grounds for realigning the test's expected value. Trace to the actual runtime consumer
and verify the new behavior is genuinely harmless first — **especially for
credential / authentication fallback logic**, where "the test is now wrong" and "the
production change silently broke a fallback" look identical from the test's diff alone.

Case study: an Airflow remote-logging provider-dispatch migration dropped a
conn-id fallback; a test asserting the old fallback started failing, and rewriting it to
match the new (fallback-free) expectation looked like the obvious fix. Confirmed correct
only after tracing `AwsGenericHook.conn_config`'s truthiness check — `aws_conn_id=""` is
equivalent to `None` there (both fall through to boto3's default credential chain), so
dropping the fallback was actually safe. Without that trace, "the test is green" would
have been mistaken for "the change is verified."

How to apply: when a test failure traces back to a recent production commit (not a bug
in the test itself), find that value's actual runtime consumer and verify the behavior
change has no real user impact **before** changing the test's expected value — treat
credential/auth fallback paths as the highest-scrutiny case of this pattern.

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

## A test double gated by a value it can't produce should emit that value directly

When the code under test is gated by a computed value the test double
doesn't know how to produce — a cost/usage figure looked up from a
real-world pricing table by model name, a checksum, a signature — don't try
to make the double satisfy the real computation. Make the double emit the
gating value directly in its response.

Case study: pydantic-ai's `UsageLimits(cost_limit=...)` checks
`RunUsage.cost`, normally computed by `genai-prices` from the model's *name*
against a pricing table. A test's `FunctionModel` isn't in that table, so
its cost is always `0` — "set a tiny `cost_limit` and confirm it trips"
never triggers, no matter how small the limit is. The fix is having the
fake model's response report its own cost directly, bypassing the pricing
table:

```python
def _priced_model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(
        parts=[TextPart(content="the answer")],
        usage=RequestUsage(input_tokens=100, output_tokens=50, cost=Decimal("0.10")),
    )
```

`Agent(FunctionModel(_priced_model_fn)).run_sync(..., usage_limits=UsageLimits(cost_limit=Decimal("0.05")))`
then raises `UsageLimitExceeded` as expected; `run_sync` and async `run` share
the same graph path, so no separate recipe is needed for either.

Two adjacent traps when writing this kind of test: pydantic-ai's comparison
is strict `>`, so `cost_limit` exactly equal to the actual cost is
*allowed*, not tripped — don't write a boundary test expecting a trip at
equality. And match the assertion message against something that
identifies *which* limit fired (e.g. `r"cost_limit.*0\.05"`), not just the
number (`r"0\.05"`), since a bare-number match can't distinguish which kind
of limit tripped when a test exercises more than one.

How to apply: before reaching for a fake object's "real" computation to
satisfy a gating check, ask whether the fake can just declare the gating
value in its own output instead — this generalizes beyond pydantic-ai to
any test double blocked by a value it would otherwise have to genuinely
compute.

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

---

## Mocking the resolver removes the guard entirely

Tests that mock the resolver/factory (`infer_model`, `infer_provider_class`,
plugin loaders, URI dispatchers) only prove kwargs were assembled and
forwarded — not that the string values themselves are valid. Under a mock, a
string is an opaque token; swapping in any value produces the same assertion
result. A docstring/placeholder that advertises a value the installed
library no longer accepts can go unnoticed indefinitely, because no test in
that mocked suite will ever turn red.

One layer deeper, the same failure shows up in the data source a drift
tripwire reads: it must be the source runtime actually consults, not
whichever is easiest to parse. A source that's never read at runtime
produces a tripwire that stays green forever while the value users actually
see is wrong. Airflow provider example: the connection UI's runtime source
is `provider.yaml`'s `conn-fields`; when that's present, the hook's
`get_ui_field_behaviour()` is never called (`providers_manager.py`'s
`ui_metadata_loaded` gate — that path is deprecated since 3.2.0), so a
tripwire built on `get_ui_field_behaviour()["placeholders"]` guards a string
nobody's form ever shows.

Discriminating power must be verified **per source**, not once combined:
flip each source back to a bad value independently and name which assertion
turns red for each. If only one source's mutation moves an assertion, the
other source isn't wired in — that's a test defect, not a coincidence.

Asserting what a mocked hook's downstream call (e.g. `run_sync`) received
only proves "the argument was forwarded" — not that the code consuming it
actually honors the value. An upstream reviewer has pushed back on exactly
this pattern before, on the grounds that passing the assertion establishes
nothing about what happens once that value reaches the code that actually
consumes it. Give behavioral evidence instead — swap in a real object (e.g.
wire a real agent/model into the same patched constructor) so the assertion
exercises real downstream logic, not a mock's echo.

Why: all three are the same shape — the mock or the wrong data source
removes the one thing the test was supposed to guard, while the test suite
keeps reporting green.

How to apply during review:

- A resolver/factory mock in the test under review → ask "what proves the
  *string values* are valid, not just forwarded?" No answer → push back for
  an unmocked drift tripwire.
- Any drift tripwire → ask "which source does runtime actually read?" before
  trusting it; a deprecated or shadowed source guards nothing.
- Demand a mutation check **per data source**, not one combined pass.
- A test that only asserts `mock.call_args` on a mocked hook/dependency is
  not behavioral evidence; ask for a real-object substitution or an
  integration path.
