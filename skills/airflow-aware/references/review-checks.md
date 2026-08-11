# Airflow review-time checks (strict-review items 10+)

Loaded on demand by `skills/airflow-aware/SKILL.md` §10 — **review tasks only**
(🟡 Soyo running `strict-review` on an Airflow diff). Each sub-check below becomes
an item 10+ in the checklist output, with the stated Block / Request-changes severity.
Outside of a review context (quick-fix / refactor), do not gate tasks on these.

## Secrets masker tests: `@pytest.mark.enable_redact` + reset before use

Airflow-specific supplement to `strict-review`'s "Tests touching global state must
reset themselves" convention (`skills/strict-review/references/test-conventions.md`):
a test that calls `mask_secret()` must be marked `@pytest.mark.enable_redact` (a global
autouse fixture otherwise patches redact/mask_secret out) and must call
`reset_secrets_masker()` before registering its own pattern — otherwise it inherits
patterns registered by earlier tests and leaks its own secret to whatever runs next.

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

Three related sub-judgments for unreleased-version work:

- **`Guard:` not `Regression:` for a bug caught during the same unreleased feature's own
  development.** A test or comment describing a bug found and fixed while a feature is
  still unreleased must not open with `Regression:` — there is no shipped-then-broke
  baseline, so `Regression:` misleads a reader into thinking a released version broke.
  Reword to `Guard:` and state plainly that it guards against reintroducing a bug seen in
  an earlier draft. Reserve `Regression:` for behavior that worked in a released version
  and then broke.
- **Mutating an existing Alembic migration file for an unreleased version is acceptable,
  and preferred over adding a new revision.** Don't flag this as a blocking issue or
  insist on a new revision just because the migration already exists on `main`. The
  criterion is "has this migration's version shipped?", not "is this migration in
  `main`?" — Airflow's "migrations are immutable" rule applies to released versions;
  additive changes to an in-development version's migration belong in the existing file.
  Released-version migrations remain immutable — still flag those.
- **A `_private_ui` route bug fix doesn't need a newsfragment — judge by same-file
  precedent, not by release status.** Don't resolve this by arguing whether the route
  already shipped; check `git log` on the route file (e.g.
  `airflow-core/src/airflow/api_fastapi/core_api/openapi/_private_ui.yaml` endpoints) for
  a precedent bug-fix commit on the same file and follow what it did, even when the
  endpoint is confirmed already shipped in a release.

## 10.7 Revert of a recent fix: check for a tracking issue first *(judgment gate — avoid a false-positive regression flag)*

**Scope gate**: only applies when the diff/PR title/description reverts, or
partially reverts, a commit that landed recently.

Before flagging a PR that reverts a recent fix as a regression, check the PR
body / linked issue for a tracking issue that lists the revert as a planned
step. A tightened prek/CI rule sometimes forces code into a worse shape
temporarily; when the rule is later relaxed, a tracking issue enumerating
"Revert / Split / Rewrite" items records the planned cleanup. Finding such
an issue means the revert is a governed wrap-up, not a regression — read the
tracking issue's content and confirm the revert is actually listed in it
before treating it as intentional; absence of any such reference is when to
treat it as a real regression.

## 10.8 Self-discovered bugfix: verify upstream doesn't already have it *(Request changes if evidence is missing)*

**Scope gate**: only applies to a bugfix PR/branch where the bug was
**self-discovered** (found by the agent itself while working on something
else), not opened from a tracked issue.

Before investing further in the branch, and again before opening the PR,
check whether `upstream/main` already has an equivalent fix in flight or
merged:

```bash
git fetch upstream main && git log upstream/main --oneline -30 -- <the paths touched>
gh pr list --search "<keywords>" --state all
```

The repo's own "Before starting: check for an existing PR" convention is
written for *taking* an issue, so it's easy to skip for a bug spotted
directly in `main` — that's exactly the gap this check closes. Re-check
after a long working session; upstream moves while work is in progress. A
merged upstream fix means drop the branch (verify how much of the diff still
adds value — sometimes only a small leftover, like a missing translation
string, survives); an open PR means review or build on it rather than
opening a near-duplicate.

## 10.9 Forward-looking code comments need a tracking-issue URL or a neutral rewrite *(Request changes)*

**Scope gate**: only applies when the diff contains a forward-looking phrase
naming a possible future change with no inline tracking-issue URL — e.g.
"switch to X if this becomes a problem", "we might revisit this later",
"could be replaced by Y".

The repo's own
[`AGENTS.md`](https://github.com/apache/airflow/blob/main/AGENTS.md) "Tracking
issues for deferred work" section already mandates a tracking issue (with an
inline URL comment at the workaround site) for the narrower case of a PR
that ships a **workaround, mitigation, or partial fix** — apply that section
as the authority for those PRs, and flag a missing tracking-issue URL there
as Request changes.

For a forward-looking comment **outside** that narrower "workaround" scope
(a stray aside in otherwise-complete code, or PR-description prose), it
still needs one of two forms:

- **Real tracking issue** — inline the issue URL.
- **Neutral trade-off note** — rewrite to describe the design choice and its
  known consequence, without promising a future fix, when no real follow-up
  is actually planned. Don't manufacture a placeholder tracking issue just
  to satisfy this check — delete the promise and state the trade-off
  instead.

Orphan phrases with neither form are must-fix; apply the same posture to
PR-description and commit-body text, not just code comments.

The same judgment also governs log/audit/error message text, not just code comments —
see `skills/strict-review/references/recurring-patterns.md`'s "Log/audit/error messages
state what happened, not why it might change later."

## 10.10 Newsfragment content must reflect a genuine capability delta vs upstream *(Request changes)*

Presence of a newsfragment file (10.6) doesn't mean its content is accurate.
Before accepting one, diff the branch against `upstream/main` to confirm the
capability it describes is genuinely new or changed **relative to what's
already shipping**:

```bash
git show upstream/main:<file> | grep <symbol>
git diff upstream/main -- <file>
```

Two specific traps this catches: a flag/field/behavior added **and removed**
within the same unreleased PR (net: users never saw it, so its removal isn't
user-facing and shouldn't be newsfragmented as a removal); and a newsfragment
describing what reads like a new capability but turns out to be an internal
rework with the same observable behavior already on `upstream/main` (check the
actual pre-PR code, not the PR's own framing of "before"). If the net delta is
"internal rework, no observable change," the newsfragment should be dropped —
apply the repo's own golden rule (`CLAUDE.md` / `AGENTS.md`: only add a
newsfragment when certain it's user-facing).

## 10.11 Operator `__init__` vs `execute()` check placement, and rendered-guard symmetry *(Request changes)*

**Scope gate**: only applies when the diff touches a class that directly
subclasses `BaseOperator`. The `validate_operators_init.py`-style prek hook
only scans direct subclasses — an operator behind an intermediate base class
(e.g. a shared `LLMOperator`) isn't scanned and is not valid precedent to cite
either way.

- **Provision vs rendered-value.** A check that only asks "did the user
  provide this parameter" (`field is None` / `is not None`) belongs in
  `__init__` — even when the field is a template field. A check that needs
  the *rendered* value to answer (is the value itself valid after templating)
  stays in `execute()`. "It's a template field, so it can only be checked in
  `execute()`" is not a valid justification for moving a provision check out
  of `__init__`. Note the hook only sanctions *identity* comparisons
  (`is None` / `is not None`) as provision checks — a truthiness form
  (`not field` / `if field`) is still flagged even in `__init__`, so rewrite
  to the identity form rather than just relocating the check.
- **Rendered-guard symmetry.** When `execute()` has a rendered-value guard for
  one template field, every other template field feeding the same downstream
  call in that function needs the same guard. An asymmetric guard is a
  defect, not a style choice: standard Jinja renders `{{ none }}` to the
  string `'None'`, but `NativeEnvironment` deployments
  (`render_template_as_native_obj=True`) produce a real `None` — the
  ungated field then falls into the downstream call unguarded, raising the
  wrong exception type (a bare `TypeError` instead of a clear `ValueError`)
  with no message distinguishing "not provided" from "rendered to None."

Case study: apache/airflow#70628 — `DocumentLoaderOperator.execute()` guarded
`file_type`'s rendered value but not `source_path`'s; the ungated
`source_path` fell into `_resolve_files(None)`, producing
`TypeError: argument of type 'NoneType' is not iterable` instead of a
readable error.

## 10.12 registry `slice`/`first` cutoffs need a sort key *(Request changes)*

**Scope gate**: only applies when the diff touches `registry/src/*.njk`
templates, or the `_data/*.js` layer feeding them.

Any `| slice(0, N)` (or `| first` / `[:N]`) truncation in a registry template
must be preceded by an explicit sort — sort in the `_data/*.js` layer, not the
template (nunjucks' `sort` filter doesn't accept a dotted attribute path, so
sorting there requires flattening first, which is more code for the same
result). Widening the membership of the collection feeding a slice — a
broader match condition, an added keyword, a new data source — is a silent
regression if the cutoff isn't sorted: known providers can drop out of a
badge/top-N list with no test or build failure to flag it, only a visual
discrepancy on the built page. When reviewing a change that widens any
collection with a downstream slice, grep that collection's consumers for a
truncation point and require a sort key as part of the same change, not a
follow-up.

## 10.13 New provider, or new major capability surface, needs a governance-gate check *(informational — report separately from the code verdict)*

**Scope gate**: only applies when the diff adds a substantial new
provider-level capability — a whole new toolset, a new integration surface —
not an incremental feature or bugfix on an existing provider.

apache/airflow requires a governance step independent of code correctness for
this class of PR: a dev-list `[DISCUSS]` thread, and a named long-term
maintainer commitment per `ACCEPTING_PROVIDERS.rst`. A clean code-level
verdict does not imply the PR is mergeable. Check for the `[DISCUSS]` thread
on lists.apache.org and a named maintainer commitment *before* treating a
code APPROVE as "ready to merge" — report governance status as a separate
line item, not folded into code must-fix, and don't let a code APPROVE imply
mergeability either. Seen enforced on apache/airflow#68847 (SandboxToolset):
clean code review (APPROVED, full test/mypy/ruff pass) still blocked without
the governance thread and a named maintainer.

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

## New provider.yaml module section: registry + validator touchpoints (narrow — read only when this applies)

**Scope note**: this only applies when a diff introduces a brand-new
`provider.yaml` **module-section type** — a new category alongside
`sensors`/`operators`/`hooks`/`triggers`/`bundles`/`toolsets` — not a new
entry under an existing section. This is rare enough not to warrant a
standing numbered checklist item; read this recipe when it comes up.

The change spans two subsystems, and one of them can turn CI red if a new
section is added to the wrong list:

- **Registry side**: `dev/registry/registry_tools/types.py`'s `MODULE_TYPES`
  (source of truth: `yaml_key` / `level` / `suffixes` / `label` / `icon`) plus
  its base-class import list; `registry/src/_data/types.json` (generated,
  drift-checked); CSS in `tokens.css` (a `--color-<type_id>` token) and **five**
  `main.css` rule families, not just one — `.tab-icon`, `.type-icon`,
  `.share-bar`, `.provider-card .modules`, and
  `.provider-detail-page .modules .module .icon`. Missing CSS doesn't error —
  the badge silently falls through to the bare base rule with no background.
  Note the two naming conventions: the registry type id uses underscores
  (`retry_policy`), the `provider.yaml` key uses hyphens (`retry-policies`);
  CSS uses the type id.
- **Validator side** (`scripts/in_container/run_provider_yaml_files_check.py`):
  four hardcoded section lists exist, and they are not equally safe to
  extend — check `check_duplicates_in_integrations_names_of_hooks_...` and
  the `registered_modules`/`check_invalid_integration` call sites are safe to
  add to; a fifth touchpoint pair (`base_class_resource_map` and the
  `registered_modules` tuple) both need the new `(<BaseClass>, "<yaml-key>")`
  entry — missing either leaves class-registration unchecked for the new
  section.

**The trap**: `check_correctness_of_list_of_sensors_operators_hook_trigger_modules`
runs a completeness assertion whose glob is `**/{resource_type}/*.py` — it
assumes the module lives in a directory *named after the resource type*. If
the new section's modules don't (e.g. a hypothetical `retry-policies` module
living under `policies/retry.py` rather than `retry-policies/`), adding it to
this list turns CI red with `Items in the right set but not the left`. In
that case, write a new existence-only `@run_check` function instead (shape:
`check_hook_class_name_entries_in_connection_types`, collecting
`python-modules` with `ObjectType.MODULE`) — and register it in the
unconditional call sequence, not inside `if all_files_loaded:` (that block
only runs on a full scan; a scoped single-file validation run would silently
skip the new check and report a false green). "Yaml key ≠ directory name" is
not unique to a hypothetical new section either — `secrets-backends` modules
already live under `secrets/`, not `secrets-backends/` — so don't describe
the directory-matches-key pattern as universal in a comment or PR
description.

This whole scenario is a worked example of the
[`change-site-enumeration`](https://github.com/Lee-W/maigo/blob/main/skills/change-site-enumeration/SKILL.md)
skill's "shared constant changes tuple arity/field count" row — grep the
constant name (`MODULE_TYPES`, the hardcoded section lists), not the type
name, and re-grep after the change to confirm no further site remains.

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
