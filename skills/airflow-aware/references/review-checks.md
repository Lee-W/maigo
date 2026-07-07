# Airflow review-time checks (strict-review items 10+)

Loaded on demand by `skills/airflow-aware/SKILL.md` §10 — **review tasks only**
(🟡 Soyo running `strict-review` on an Airflow diff). Each sub-check below becomes
an item 10+ in the checklist output, with the stated Block / Request-changes severity.
Outside of a review context (quick-fix / refactor), do not gate tasks on these.

## 10.1 Execution API wire-format gate *(Block-level)*

If the diff touches any of:

- `airflow-core/src/airflow/api_fastapi/execution_api/datamodels/*.py`
- `task-sdk/src/airflow/sdk/api/datamodels/_generated.py`
- `task-sdk/src/airflow/sdk/execution_time/comms.py` payload schemas
- `airflow-core/src/airflow/api_fastapi/execution_api/routes/*.py` (new endpoints)

then there **must** be a corresponding new (or updated in-progress) version file under
`airflow-core/src/airflow/api_fastapi/execution_api/versions/v2026_XX_XX.py`
registering `instructions_to_migrate_to_previous_version` for old clients.
Missing version file → **Block**, point at
[`contributing-docs/19_execution_api_versioning.rst`](https://github.com/apache/airflow/blob/main/contributing-docs/19_execution_api_versioning.rst).

Reason: server `StrictBaseModel` payloads default to `extra="forbid"` and 422 unknown
fields, so mixed-version rollouts break silently otherwise.

## 10.2 Multi-PR split: wire-format symbol cross-check

If the PR body says "PR N of M", "split from #NNNNN", "consumes what was added in
#NNNNN", or `cc:` mentions the same reviewer across sibling PRs, fetch the sibling
PR's diff (`gh pr diff <sibling> --repo apache/airflow`) and compare wire-format /
API field names character-for-character (singular vs plural, underscore placement,
casing, type — e.g. `list[str]` vs `str`).

Mismatches are typically **Block-level**: silent end-to-end breakage that the PR's
own tests will not catch because they're self-consistent against the wrong shape.
Past examples: #66699 renamed `retention_days` → `expires_at` in prod but not tests;
#66782 consumer reads `partition_key` while #65447 producer emits `partition_keys`.

## 10.3 Top-level imports of Unix-only modules

Top-level imports of `fcntl`, `pwd`, `grp`, or `resource` break Windows.
Flag as **Block** unless the whole file is Unix-gated (e.g., `sys.platform != "win32"`
guard at module top, or the file lives under a `_unix` / `_posix` submodule).

## 10.4 `TYPE_CHECKING` guards for heavy type-only imports

In multi-process code paths (scheduler, Dag File Processor, triggerer, worker), heavy
type-only imports (e.g., `kubernetes.client`, `boto3`, `google.cloud.*`) must be
guarded by `if TYPE_CHECKING:` — pulling them into every fork balloons memory and
startup time. Flag as **Request changes**.

## 10.5 Security finding classification

When flagging a security concern, classify it as exactly one of three before
reporting:

- **Actual vulnerability** — code violates the documented security model
  (e.g., a worker gaining direct DB access, scheduler executing user code,
  unauthenticated user reaching a protected endpoint). Report as Block.
- **Known documented limitation** — gap in the current implementation that's
  already tracked (Dag File Processor / triggerer DB access, shared Execution API
  resources, multi-team not enforcing task-level isolation). Do **not** re-report
  as a new finding; reference the existing tracking.
- **Deployment hardening opportunity** — improvement a Deployment Manager can make
  beyond what Airflow enforces natively (per-component config, asymmetric JWT
  keys, network policies). Belongs in deployment guidance, not a code-level issue.

Authority:
[`airflow-core/docs/security/security_model.rst`](https://github.com/apache/airflow/blob/main/airflow-core/docs/security/security_model.rst).

## 10.6 Newsfragment file presence

If the diff modifies code under `airflow-core/`, `chart/`, or `dev/mypy/` and is
user-visible (feature / bugfix / breaking change / doc change with user impact),
look for a matching
`<distribution>/newsfragments/{PR_NUMBER}.{bugfix|feature|improvement|doc|misc|significant}.rst`
file in the diff. Missing → flag as **Request changes** (not Block).
**Do not** require newsfragments for changes under `providers/` or `airflow-ctl/`
— their release managers regenerate the changelog from `git log`.

## Don't proliferate example Dags — fold into an existing one

When a PR demonstrates a new trigger / operator / scheduling pattern,
**extend an existing example Dag** (more watchers / more tasks / more
schedule entries in the same Dag) instead of adding new Dag files or new
`with DAG(...)` blocks in the same file. Airflow's "Examples Refurbish"
effort actively tries to reduce the total number of example Dags; adding new
ones works against that, even when the new Dag is scoped tightly to the
feature.

How to apply:

- For an opt-in feature on an existing class (e.g. a new trigger variant),
  keep the same example Dag id and same `with DAG(...)` block; add
  additional `Asset` / `AssetWatcher` / trigger instances alongside the
  original ones. A single Dag scheduled by `[asset_old, asset_new1,
  asset_new2]` fires on any.
- Update the file's module docstring to explain both patterns in one place.
- Update any doc references (e.g. `event-scheduling.rst`) to point at the
  single consolidated example, not "alongside the X case".
- Only add a brand-new example file when the feature genuinely cannot be
  shown alongside an existing example — and even then, confirm first.

**When NOT to flag in review:** only raise this when the new Dag is
**clearly duplicative** of an existing demo. Skip it when the new feature's
semantics make folding impossible — e.g. a fan-out (1→N) pattern needs a
coarser-cadence producer than any existing hourly producer, so it cannot be
attached as a watcher to existing rollup (N→1) examples. If the only way to
fold would break existing example semantics or produce a degenerate demo
(e.g. an identity fan-out), do not list it even as a nit. Most reviewers
don't care about that level of consolidation when folding would force a
worse demo.

## uv.lock drift diagnostic (extended recipe)

The SKILL.md §3 covers the summary. Use this section when you need the full
diagnostic, the "find when it was introduced" step, or a concrete case study.

### Full diagnostic recipe

1. Inspect the diff — identify which package changed:
   ```bash
   git diff HEAD uv.lock | head -50
   ```
2. Find which `pyproject.toml` declares (or should declare) that dependency:
   ```bash
   grep -rn "<package-name>" --include=pyproject.toml -l
   ```
3. Cross-check: is the package in the *committed* pyproject and the *committed* lock?
   ```bash
   grep "<package-name>" <pyproject>           # current HEAD
   git show HEAD:uv.lock | grep "<package-name>"   # committed lock
   ```
   If pyproject lacks the package but the committed lock has it (or vice versa) →
   **drift confirmed**.
4. Find when the drift was introduced:
   ```bash
   git log -p -- <pyproject>
   ```
   Look for a commit that changed dependencies without a companion `uv.lock` change
   in the same commit.

### Why it recurs

Airflow is a large `uv` workspace monorepo with 100+ provider packages.
Contributors sometimes edit a `pyproject.toml` and push without running `uv lock`,
especially for small changes ("just remove an unused extra"). CI lock-validation can
be partial and miss the drift.

### Concrete case

`dcdd124431` ("Add Langchain hook to common-ai provider", 2026-05-20) committed a
`uv.lock` containing `langchain-openai`, but `providers/common/ai/pyproject.toml` at
HEAD no longer declares that dependency. A contributor trimmed the pyproject without
re-running `uv lock`, leaving the committed lockfile out of sync. Every fresh `uv sync`
regenerates the lock to match the current pyproject and surfaces the delta as a phantom
diff in every worktree.

### How to handle in a feature PR

1. Run the diagnostic above before touching anything else.
2. If drift is confirmed, do **not** fold the lock regeneration into the current feature
   PR. Open a separate worktree off `upstream/main` and submit a focused
   `chore: re-lock <pyproject>` PR.
3. For the current feature PR, `git checkout HEAD -- uv.lock` keeps the diff out of the
   commit. The diff will re-appear locally on the next `uv sync` — that is expected.
4. If another contributor suggests "just commit the lock diff with your feature work,"
   push back: it pollutes the PR diff and creates a force-push risk if `main` re-locks
   before merge.

---

## Case studies backing strict-review recurring patterns

Concrete Airflow incidents behind two of `strict-review`'s recurring must-fix
patterns. Read when applying those patterns to an Airflow diff and a worked
example helps.

### Commit body is a contract — the `RollupMapper` case

A trigger-policy commit claimed _"pre-existing serialized Dags default to
`WAIT_FOR_ALL` on deserialize"_ but `RollupMapper.deserialize` used
`data["wait_policy"]` with no `.get()` fallback — any cache-resident payload would
`KeyError`. Fix was to align prose with code (rewrite the commit body), not the
reverse. Pre-release status does **not** downgrade this: wire-format mutations are
acceptable pre-release, but the commit body's promise about behaviour must still
align with the diff.

### Underscore-private exception promotion — the `_AckTimeout` case

`_AckTimeout`, `_PollTerminated`, `_SubscriberOverflow` were all private, but test
files imported `_AckTimeout` to write `isinstance(sentinel.exc, _AckTimeout)` —
its `isinstance` result drove consumer behaviour, making it de-facto public API.
Fix: rename only `_AckTimeout` → `AckTimeout` (add to `__all__`); the siblings that
consumers never branch on by type stay underscore-private. Selective promotion is
the discipline; do not broadcast the whole hierarchy.

### Tests must feed production-path inputs, not pre-aligned ones — the partition-backfill tz case

In apache/airflow's AIP-76 partitioned backfill, the production paths that feed
`from_date`/`to_date` into the timetable — CLI `--from-date/--to-date` via `parsedate`,
API `from_date/to_date` via `coerce_datetime` — always attach the core `default_timezone`
(UTC in standard deployments), never the Dag's timetable timezone. A test asserting
tz-boundary behavior (cross-timezone daily backfill not dropping the first day, sub-day
window not widening) must feed the bound in that same production shape — a
UTC-midnight-aware datetime (e.g. `pendulum.datetime(2026,2,15,tz="UTC")`) — not a bound
pre-aligned to the timetable's own timezone (e.g. `pendulum.datetime(2026,2,15,tz="Asia/Taipei")`),
which bypasses the internal wall-clock rebase and can pass while hiding a real gap.
Case study: PR #68718's `test_create_backfill_partitioned_non_utc_boundary` fed a
pre-aligned Taipei bound, baseline ran green, but a UTC-hosted Taipei `0 0 * * *` Dag
was silently dropping its first partition day — 9 runs instead of 10 — caught only
because reviewer phanikumv flagged it. When a diff touches partition/backfill
tz-boundary tests specifically, ask "what does the production path actually feed?"
and check the test input matches that shape.
