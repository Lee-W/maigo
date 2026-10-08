# Enumeration patterns: five "before you change one site" shapes

Loaded on demand by `skills/change-site-enumeration/SKILL.md`. Each pattern names what to
enumerate **before** editing the one site in front of you. All cases are from apache/airflow PRs.

---

## Extracting shared logic: diff each source's old behaviour against the new helper

When collapsing several similar code paths into one helper, for **every** source run
`git show <base>:<path>` and list its original validations, error messages, and branch order;
confirm each still exists in the helper and in the same order. Two common regressions:

- a check unique to one source is dropped in the move;
- a guard added for one source is placed on the shared path and blocks a combination that used to
  succeed.

Case (apache/airflow #73932): (C6) the agent hook's "raise `ValueError` if account/user is
missing" did not make it into `SnowflakeRestTokenProvider`, producing `NoneType.upper()` and a JWT
whose `sub` was `.USER`; (C7) a new workload-identity guard sat before the private-key load, so
the "WIF + private key" connection that the 6.18.0 SQL API hook accepted began to raise.

---

## Adding a subclass override: scan tests that patch the base method

When adding a subclass override of a base-class method in Airflow, the verification scope must
include tests that **patch the base class's same-named method** — the override bypasses the
patch.

Case (apache/airflow #72934): a `get_authorized_assets` override on `SimpleAuthManager` bypassed
seven route tests (`routes/public/test_assets.py`, `routes/ui/test_assets.py`) that patched
`BaseAuthManager.get_authorized_assets`; CI went red ("Called 0 times" / equality failures) while
local verification had only run the auth-manager and `test_security` suites.

How to apply: before adding the override, grep **separately** for `<BaseClass>.<method>` and for
the bare method name as a patch target across `airflow-core/tests` and `providers/` (first prove
the pattern against a known hit), add every matching test file to the verification, and retarget
the patches to the class that is actually effective in the test environment.

---

## Adding a swallow-and-log wrapper: enumerate every caller of the wrapped operation

When wrapping an operation in `try: op() except Exception as e: log.warning(...)`, first grep
**all call sites of the underlying operation across the package** and decide for each whether it
should use the wrapper. Fixing only the site a reviewer pointed at leaves the same defect in the
bare ones.

These are best-effort / cleanup actions (cancelling remote work, releasing a resource, deleting a
temp file) that run **while another failure is already being handled**. If the cleanup also fails,
its exception **replaces** the one explaining why execution stopped, and the user sees unrelated
downstream noise.

Case (apache/airflow #72149, openai provider): the deferred-timeout path got
`_cancel_batch_quietly`, but `OpenAITriggerBatchOperator.on_kill` and the timeout branch of
`OpenAIHook.wait_for_batch` still called `cancel_batch` bare, so a failing cancel request masked
`OpenAIBatchTimeout`. The reviewer named only `on_kill`; one `grep -rn "cancel_batch" <pkg>/src`
listed all three call sites.

Two side points:

- The wrapper is usually cross-layer. A hook cannot call an operator's private method, so "the
  same fix" has a different shape per layer (one uses the existing helper, one wraps its own
  try/except). That is layering, not duplication; don't promote the helper to a public hook API
  just for a single source.
- The helper's docstring goes stale. With one caller it often explains "why the argument is passed
  in" (e.g. `self.x` is `None` on a resumed task instance); with a second caller that is wrong for
  half the readers. Re-read the helper's docstring whenever you add a caller — in that review it
  was the only must-fix.

Verify with a mutation canary: revert one site to the bare call, the matching test must go red,
and name which assertion goes red.

---

## Porting a mechanism: extract a shared layer rather than leave parallel copies

When porting an existing mechanism to another set of operators/classes, prefer extracting a shared
layer that source and target both use. If the source side is tangled with specifics (durable /
HITL logic), leave the specifics in place and connect through a hook — don't conclude "the overlap
is small, so leave the source alone".

Case (2026-10, common.ai): moving `__commonai_usage__` from `AgentOperator` to the `LLM*`
operators, the planner advised not touching `AgentOperator` (about 6 overlapping lines, durable
logic deeply entangled); the maintainer chose to extract a `UsageBudgetMixin`.

---

## Before building a new abstraction: survey existing coverage and open PRs in the area

Before proposing or building a new operator or abstraction layer in an area (e.g. common.ai),
survey three things:

1. whether existing operator/toolset combinations already cover it;
2. whether a neighbouring (vendor) provider already has the capability;
3. whether a maintainer has an open PR on the same path.

Case (apache/airflow #74026, 2026-10): a `HarnessOperator` was built first; only afterwards did it
turn out that `AgentOperator` + `SandboxToolset`, the `*AgentSessionOperator` family, and a
maintainer's #73962 already covered most of it, and the PR was reshaped into an adapter.

How to apply: before recommending "start a minimal branch", run an Explore pass for coverage plus
`gh pr list --search <path>`, and write the result into the recommendation's premises.
