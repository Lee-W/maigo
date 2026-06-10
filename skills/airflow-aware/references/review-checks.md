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
