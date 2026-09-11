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
#NNNNN", `cc:` mentions the same reviewer across sibling PRs, **or the PR body/commit
message explicitly references a sibling PR** ("see #NNNNN", "lands with #NNNNN") —
that reference alone is a trigger, not just a structurally-declared multi-PR split —
fetch the sibling PR's diff (`gh pr diff <sibling> --repo apache/airflow`) and verify:

1. **Field names** on dict/Pydantic payloads match character-for-character (singular
   vs plural, underscore placement, casing).
2. **Field types** match (e.g. `list[str]` on the producer matching `list[str]`
   reader on the consumer, not `str`).
3. **Method/kwarg names on shared interfaces line up across all three of the SDK,
   wire, and backend layers** — not just one layer against another; a name can agree
   between two of the three and still diverge on the third.

Mismatches are typically **Block-level**: silent end-to-end breakage that the PR's
own tests will not catch because they're self-consistent against the wrong shape.
Past examples: #66699 renamed `retention_days` → `expires_at` in prod but not tests;
#66782 consumer reads `partition_key` while #65447 producer emits `partition_keys`;
#66859's backend test stub kept `retention_days=None`, which works against current
`main` but breaks once sibling #66699's rename lands first.

**How to apply**: when fetching the current PR's diff, also fetch the named sibling
PR(s) in the same pass. Build a small "symbol table" — literally list each wire/API
name from each side side-by-side — and compare it, rather than reading each diff
separately and trusting memory to catch a mismatch.

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

  Second instance of the same method, this time for an additive field: for a
  `DAGResponse` new optional field + UI prefill behavior change, walk the last
  ~25 commits touching `api_fastapi/core_api/datamodels/dags.py`
  (`git log --format=%H -25 -- <file>`, then check each for a matching
  `newsfragments/` entry) rather than guessing from the golden-rule intuition
  or the feature's release status. Precedent: an additive optional response
  field + UI detail-page display got **no** newsfragment; an API type change
  got **no** newsfragment; a config-option PR that also introduced a behavior
  tier **did**. Conclusion for this shape (additive optional field + UI
  prefill): don't add one, let a reviewer request it if they disagree — this
  is a convention-conformance input, not a waiver on the checklist item.

## 10.7 Provider changelog: breaking/important behavior changes must be hand-edited into `docs/changelog.rst` *(Request changes)*

**Scope gate**: only applies to diffs under `providers/<name>/`. Does not
apply to `airflow-core/`, `chart/`, `dev/mypy/` (10.6's newsfragment rule) or
`airflow-ctl/` (fully RM-generated, PRs must not touch `RELEASE_NOTES.rst`).

`providers/AGENTS.md`'s documented rule runs the **opposite** direction from
10.6's newsfragment rule: a breaking or important behavior change must be
hand-edited into that provider's `docs/changelog.rst`, directly below the
`Changelog` header, in the same PR. Routine feature/bugfix/misc entries are
collected automatically by the release manager from commit messages — most
PRs should **not** touch the changelog at all. pre-1.0 is not an exemption;
the rule applies regardless of the provider's version — confirmed precedents:
#69695 (exasol, `pyexasol` 2.x bump), #69474 (postgres, `psycopg` v3 default),
and #67644 (common.ai, Pydantic XCom — that provider is itself pre-1.0);
`gh pr diff <n> --name-only` on each hits `providers/<p>/docs/changelog.rst`.

Two traps when judging this:

- **Don't use "this provider's changelog.rst has never been touched by a
  feature PR" as evidence the rule doesn't apply.** A young provider's
  changelog only shows `Prepare providers release` entries because the file
  itself is young, not because hand-edited entries are unusual in this repo —
  check a mature provider's changelog (e.g. `providers/amazon/docs/changelog.rst`)
  for the counter-example before concluding otherwise.
- **Don't conflate this with `airflow-ctl/RELEASE_NOTES.rst`, which is fully
  RM-generated and explicitly forbids PR edits** — the two files have
  opposite contribution models; a lesson learned from one does not transfer
  to the other.

Judge "is this breaking" by **actual runtime behavior**, not the diff's type
annotations: a return-type change from `tuple[bool, str | None]` to
`tuple[bool, str | None, str | None]` breaks any caller that unpacks it
(needs a changelog entry); a signature narrowing from `-> Any` to a concrete
type, where the `return` statement itself is unchanged, has zero runtime
delta (no changelog entry needed) even though the type annotation looks like
a bigger change. Misjudging toward "breaking" forces a false changelog
entry; misjudging toward "routine" leaves downstream users with an
unrecorded `ValueError: too many values to unpack` after upgrading. This is
a convention-conformance input, not a waiver on the checklist item.

## 10.8 Revert of a recent fix: check for a tracking issue first *(judgment gate — avoid a false-positive regression flag)*

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

## 10.9 Self-discovered bugfix: verify upstream doesn't already have it *(Request changes if evidence is missing)*

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

## 10.10 Forward-looking code comments need a tracking-issue URL or a neutral rewrite *(Request changes)*

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

## 10.11 Newsfragment content must reflect a genuine capability delta vs upstream *(Request changes)*

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

## 10.12 Operator `__init__` vs `execute()` check placement, and rendered-guard symmetry *(Request changes)*

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

## 10.13 registry `slice`/`first` cutoffs need a sort key *(Request changes)*

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

## 10.14 New provider, or new major capability surface, needs a governance-gate check *(informational — report separately from the code verdict)*

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

## 10.15 Cross-timetable `partition_date` comparisons must normalize via `localize_partition_datetime` *(Request changes)*

**Scope gate**: only applies when the diff compares, sorts, or validates a
`partition_date`-related `datetime` bound across timetables (e.g. an
inverted-window guard, a CLI/API range check).

`Timetable.localize_partition_datetime` has exactly two implementations
repo-wide, with different semantics: the base `Timetable`'s
`timezone.coerce_datetime(dt)` is a no-op pass-through for an already-aware
datetime — it compares as an **absolute instant**, keeping the original
offset. `CronMixin` (the shared base for `CronDataIntervalTimetable`,
`CronPartitionTimetable`, and other cron-scheduled timetables) instead does
`convert_to_utc(make_aware(dt.replace(tzinfo=None), self._timezone))` — it
**discards** the original offset and reinterprets the wall-clock reading
using the timetable's own timezone.

A comparison written against a `datetime` without first normalizing through
`dag.timetable.localize_partition_datetime()` will diverge from downstream
query semantics (e.g. `apply_partition_date_window`) whenever the Dag's
timetable is `CronMixin`-based, because the guard is silently comparing
absolute instants while the downstream query discards the caller's explicit
UTC offset.

How to apply: when reviewing partition-date bound comparison logic, check
whether it normalizes through the same `localize_partition_datetime` call
the downstream query uses — don't assume "aware datetime, direct comparison"
is equivalent to downstream behavior. Case study: PR #69454's inverted-window
guard compared absolute instants, which disagreed with `CronMixin`'s
wall-clock semantics and could wrongly reject a legal window or wrongly
allow an inverted one; the fix moved the guard after `dag` resolution and
compared via `dag.timetable.localize_partition_datetime()`.

## 10.16 Logging/audit field review: cap+sort unbounded collections; reject fields redundant with a sibling *(Request changes)*

**Scope gate**: applies whenever a diff adds or changes a field rendered
into a DB row (`Log.extra`) or a structured log/audit line.

Two related checks surfaced in the same PR review round:

- **Any unbounded, user-data-sized collection rendered into a DB row or log
  field needs a cap and a stable sort, by default — don't wait for a
  reviewer to ask.** An unbounded collection written into `Log.extra` is an
  unbounded DB payload; iterating an unordered `set` also makes the message
  differ between otherwise-identical scheduler ticks, defeating comparison
  across audit rows. Pick the sort key so survivors after truncation are the
  informative ones (e.g. `(-backlog_count, dag_id)` so the most-backlogged
  Dags survive, not an arbitrary prefix), and state *what* was dropped in the
  truncation suffix, not just how many. Don't rely on SQL `ORDER BY` alone —
  it usually lacks a tie-break column, and row order isn't a contract across
  backends. Watch the reverse direction too: if an earlier review round
  already removed truncation at a reviewer's request, say so explicitly when
  re-introducing a cap so it doesn't read as ignoring that round.
- **Before accepting a new log/audit field, check it isn't mathematically
  forced to equal a sibling field already in the same log line, on every
  code path that reaches the log call.** This kind of redundancy passes
  review by inspection (both fields "look" like independent metrics) and
  passes tests that only assert the log dict's shape rather than reasoning
  about whether the two values could ever actually differ. Example: a
  per-tick cap log carried both `cap` and `pending_count=len(pending_apdrs)`,
  but `pending_apdrs` was always sliced to exactly `cap` elements before the
  log call fired — `pending_count` could never differ from `cap`. Reviewer
  caught it on PR #71072; fixed in commit `8b2aaf8e72` by replacing it with a
  real `backlog_total` from a separate count query (see 10.17 for why that
  separate query still needs to avoid a row-locking probe). If a new field is
  provably redundant with a sibling, either drop it or replace it with a
  genuinely independent computation.

## 10.17 A capped, row-locked query must not use a `LIMIT cap + 1` probe row *(Request changes)*

**Scope gate**: applies to any query wrapped in `with_row_locks`
(`SELECT ... FOR UPDATE` / `SKIP LOCKED`) that needs to distinguish "exactly
at the cap" from "more backlog behind it."

A `LIMIT cap + 1` "probe row" trick — fetching one extra row beyond the cap
to cheaply tell "there's more backlog" apart from "this batch is everything"
without a separate `COUNT` query — is unsafe once the fetch is row-locked:
the probe row gets locked too, even though it doesn't belong to this
process's batch and is never processed. Under HA (multiple scheduler
replicas), that's contention on a row another replica may need on its next
tick. Surfaced on PR #71072 (`scheduler_job_runner.py`, partitioned Dag run
per-tick cap) — a reviewer flagged it, fixed in commit `8b2aaf8e72`.

How to apply: when a capped, row-locked query needs this distinction, drop
the `+1`. Only when the capped fetch comes back full, issue a **separate,
lock-free** `select(func.count())` with the same predicates (no
`with_row_locks` — counting is a read, not a claim) to get the real backlog
size. Row-locking reads should only ever touch rows this tick's process
actually claims and processes.

## 10.18 `providers/common/ai` hook capability additions: check three parity axes *(Request changes)*

**Scope gate**: applies when a diff gives a `providers/common/ai` hook (or a
sibling object it constructs, e.g. an embedder) a new capability.

Check for parity with sibling hooks on three axes — catching these up front
turns a multi-round review into one round:

1. **Per-capability `*_conn_id`, with sibling hooks as the reference.**
   Hooks that already support a second capability (e.g. an embedding
   provider distinct from the chat provider) take a dedicated `*_conn_id`
   that falls back to the primary `conn_id`, because the second provider
   often isn't the primary one. A capability that unconditionally reuses the
   primary connection will hand one vendor's credentials to a different
   vendor's provider class — and the generic `{api_key, base_url}` kwargs
   are legal for almost every provider class, so nothing raises. Watch the
   fallback expression itself too: `x_conn_id if x_conn_id is not None else
   primary_conn_id` makes a cross-vendor mis-wiring *avoidable*, not
   *detected* — if both resolve to a `vendor:model` string, compare the
   vendor prefixes and raise `ValueError` when they differ under a fallback.
2. **Instrumentation must reach the new call path.** If the hook's primary
   object applies instrumentation settings, a new object built alongside it
   (e.g. an embedder) must receive the same instrumentation, or the
   provider's OTel-export config silently produces spans for the primary
   path and nothing for the new one. The mechanism can legitimately differ
   per class (one class may not accept an `instrument` constructor kwarg in
   the pinned library version, requiring a sentinel dance, while another
   does) — that's not itself an inconsistency to flag.
3. **`provider.yaml` conn-field parity across the whole connection-type
   family.** If sibling connection types in the same family declare a
   conn-field for a capability, every member of a newly-added family needs
   it too, mirrored into `get_provider_info.py` (see 10.7's sibling
   concern, and this file's "`provider.yaml`'s `ui-field-behaviour`/`conn-fields`
   override the hook" note) — otherwise the UI offers no input for that
   capability and users must hand-edit the Extra JSON.

Also check `test_connection()` when two capabilities can be configured
independently: an early `return` after validating only the first means a
misconfigured second capability reports as healthy, defeating the point of
the UI's Test button. Validating both costs the same order of work, since
`test_connection()` only resolves strings and constructs provider classes
without calling a real API.

## 10.19 A `DAGResponse` (or derived-model) field addition must exist on `DagModel` *(Block)*

**Scope gate**: applies when a diff adds or removes a field on `DAGResponse`
or a derived response model in `api_fastapi/core_api/`.

The Dags-list UI route builds `DAGWithLatestDagRunsResponse` by iterating
`DAGResponse.model_fields` and calling **default-less**
`getattr(dag, DAG_ALIAS_MAPPING.get(f, f))` against a bare `DagModel`. Adding
any `DAGResponse` field that is **not** a `DagModel` attribute (one only
populated by route-level `setattr`, or one that only has a pydantic default)
raises `AttributeError`, and the Dags-list UI route returns a 500.
`computed_field`-based fields (e.g. `is_backfillable`, `file_token`) are
unaffected — they never enter `model_fields`.

**The two consumer routes fail differently, so both must be checked
separately.** The public `GET /dags` route goes through pydantic's
`from_attributes` and only silently falls back to a default (wrong value,
no exception) — passing `routes/public/test_dags.py` is not evidence the UI
route is fine. The route that actually breaks is
`routes/ui/test_dags.py`; a self-review or CI run that only exercises the
public route's tests can miss the regression entirely (confirmed instance:
two sibling PRs each added one field, each showed a clean public-route test
run and a failing UI-route test run).

How to apply: for any new `DAGResponse`-family field, require either (a) the
route defines a `DAG_RESPONSE_ROUTE_SUPPLIED_FIELDS`-style frozenset and the
UI route's comprehension explicitly excludes fields it supplies via
`setattr`, or (b) confirm the field genuinely maps to a `DagModel` attribute.
Flag a bare `getattr(dag, name, None)`-with-default rewrite as insufficient —
it silently converts a real typo in the field-mapping into a quietly-`None`
value instead of a loud error. A tripwire that asserts
`hasattr(DagModel, name)` for every non-excluded field name is the
preferred shape, since it surfaces the next add-a-field mistake at the
route rather than 500ing in production.

## 10.20 Two queries scanning the same rows under the same `WHERE` predicate should merge *(Request changes)*

When two queries share the same `WHERE` predicate over the same rows, and
each derives one value (e.g. a total count and a distinct-id count), prefer
merging them into a single `group by` / aggregate query and deriving both
values from that one result, rather than issuing two separate queries.

Why: a single query scans once instead of twice, and a single query's
result is internally consistent by construction — two separately-issued
queries can drift apart if only one of them is updated the next time the
predicate changes, with no compiler or test catching the mismatch.

How to apply: when reviewing a diff (or writing a query) that issues two
queries with an identical or heavily-overlapping `WHERE` clause, check
whether both derived values can come from one `group_by(...)` call —
e.g. a `count()` and a `sum()` both computed off the same grouped result —
before accepting two separate round trips.

## 10.21 Don't flag release-manager/CI-generated docs as scope creep, and don't require a per-PR edit to them *(judgment gate)*

**Scope gate**: applies when a diff touches `providers/<name>/docs/index.rst`'s
"Optional cross provider package dependencies" table, or
`airflow-ctl/RELEASE_NOTES.rst`.

Two files in this repo are generated/release-manager-owned in a way that's easy
to misjudge in review — in the opposite direction from 10.6's newsfragment rule
and 10.7's changelog rule (those require an edit; these two must **not** be
hand-edited or requested):

- **`providers/<name>/docs/index.rst`'s cross-provider dependency table** is
  generated by `breeze release-management prepare-provider-documentation`
  (template `dev/breeze/src/airflow_breeze/templates/PROVIDER_INDEX_TEMPLATE.rst.jinja2`)
  from `generated/provider_dependencies.json`'s `cross-providers-deps`. It is
  not a prek hook, but CI's `.github/workflows/test-providers.yml` runs the
  same regeneration step, so a committed `index.rst` that drifts from the
  metadata (e.g. a batch of providers gaining a new cross-provider dep without
  a synced `index.rst`) fails CI. When a diff shows a large, seemingly
  off-topic `providers/*/docs/index.rst` change, don't suggest `git restore`
  as scope creep before confirming whether it's this CI-enforced
  regeneration — the correct move is to keep the regeneration as its own
  focused commit, not discard it. (The `README.rst` cross-provider table is a
  separate pipeline, regenerated by the `sync-provider-readme` prek hook from
  `pyproject.toml`.)
- **`airflow-ctl/RELEASE_NOTES.rst`** is release-manager-generated after
  cutting a release candidate — its header (introduced in #67128) states
  "This file is populated while releasing after cutting the release
  candidate. Please do not edit in PRs." It follows the same contribution
  model as a provider's `docs/changelog.rst` *routine* entries (release
  manager generates from `git log`), not the newsfragment model. Don't ask an
  `airflow-ctl` PR's author to add a `RELEASE_NOTES.rst` entry, and don't flag
  a missing one as incomplete.

**How to apply**: before flagging either file as missing an entry, or as
unrelated scope creep, identify which of these two categories it falls into.
Both call for the reviewer to *not* act — the opposite instinct from
10.6/10.7's *require an edit* — so mixing up which file follows which model
produces a false-positive finding either way.

## 10.22 Dialect-dispatch catch-all `else` branch defaulting to sqlite is a footgun — reuse the canonical upsert helper or fail loud *(Request changes)*

apache/airflow has a canonical dialect-specific upsert builder at
`airflow-core/src/airflow/utils/sqlalchemy.py` (around lines 65-101). Its
docstring documents "Build a dialect-specific `INSERT ... ON CONFLICT DO
UPDATE`" and states `:raises ValueError: if the dialect does not support a
known upsert syntax`; the dispatch shape is `if dialect == "postgresql": ...
elif "mysql": ... elif "sqlite": ... else: raise ValueError(...)`.

**The footgun**: several call sites hand-roll their own dialect dispatch with
a catch-all `else` branch that assumes sqlite (e.g. the pg/sqlite helper
introduced in `assets/manager.py` by #62501, and
`dag_processing/collection.py:873`'s `if postgresql / elif mysql / else
<sqlite>`). Once Airflow supports a future metadata backend, that `else`
silently treats it as sqlite and issues
`sqlalchemy.dialects.sqlite.insert().on_conflict_do_update()` against a
non-sqlite database — a silent, wrong write with no exception raised.

**How to apply**: when reviewing a diff that adds a dialect-specific branch
(`if dialect == ...`), require either (a) reuse of the `utils/sqlalchemy`
helper, or (b) the same fail-loud shape — enumerate the known dialects
explicitly and `raise ValueError` on `else`, never assume the last-known
dialect as a default. Airflow's currently-supported metadata backend set
(postgresql/mysql/sqlite) is closed, so an *existing* catch-all-sqlite branch
is a latent robustness gap rather than a live bug today — flag it as Request
changes rather than Block, but do not accept a *new* catch-all-sqlite branch
in a PR under review. A known follow-up is a one-time sweep across the
existing call sites (at least `assets/manager.py` and
`dag_processing/collection.py:873`) to convert them to the fail-loud shape —
a reviewer spotting a new instance should point at that plan rather than
treat it as a fresh discovery.

## 10.23 registry class-level module `category` string is not user-visible — don't confuse it with the type `label` *(narrow — only applies to `dev/registry/` or `registry/` diffs, Request changes)*

**Scope gate**: only applies when a diff touches `dev/registry/` or
`registry/`.

In `registry/src/provider-version.njk` (the provider-version page), each
module entry's `category` field is used in exactly one place:
`data-category="{{ module.category }}"`, an HTML attribute never rendered as
visible text. The sidebar's "Categories" filter list (`pv.provider.categories`,
`cat.id`/`cat.name`) is built only from `provider.yaml`'s `integrations` list,
via `extract_integrations_as_categories` in `dev/registry/extract_metadata.py`.
Class-level (FQCN) sections — notifications/secrets-backends/logging/executors/
extra-links/queues/auth-managers/db-managers — have no matching integration, so
their `category` string never appears as a clickable filter option and is
never seen by a user.

**How to apply**: when a diff renames a class-level section's category-related
string (as in apache/airflow#70190, which renamed the `queue` type's
user-visible **label** from "Queues" to "Message Queues"), first identify
which string is being changed:

- `MODULE_TYPES[...]["label"]` — the user-visible type label shown on the
  module-type tab. Renaming this is a real UI change.
- The internal `category` string (`CLASS_LEVEL_CATEGORY_OVERRIDES` or its
  yaml-key fallback) — only a `data-*` attribute value. Renaming this has
  **no** visible effect on the page.

Flag a PR that renames only the internal `category` string, believing it
changes user-facing text, as a no-op relative to its stated intent — point
the author at `MODULE_TYPES[...]["label"]` instead.

## 10.24 Operator's own `xcom_push()` calls for extra keys need their own `do_xcom_push` guard *(Request changes)*

`do_xcom_push=False` only suppresses the task runner's single push of the
operator's **return value**. Any extra key an operator pushes itself inside
`execute()` via `context["ti"].xcom_push(key=..., value=...)` is **not**
controlled by that flag — a user turning it off to keep the metadata DB lean
still gets extra XCom rows every run.

Repo precedent to follow (don't invent a new shape):

- `providers/amazon/src/airflow/providers/amazon/aws/operators/emr.py:196` —
  wraps the push directly: `if self.do_xcom_push: ... xcom_push(...)`.
- `providers/amazon/src/airflow/providers/amazon/aws/operators/ecs.py:545` —
  same shape.
- `providers/amazon/src/airflow/providers/amazon/aws/operators/eventbridge.py:83`
  — a variant that gates the return value instead of the `xcom_push` call.

**Trap**: the guard must wrap only the push, not the `return`. Indenting
`return` inside the `if self.do_xcom_push:` block makes the operator return
`None` when the flag is off — a behavior regression distinct from the extra
XCom row issue.

**How to apply**: when reviewing a new `xcom_push()` call added inside a
provider operator's `execute()`, require it wrapped in `if
self.do_xcom_push:` in the same PR, and require a test asserting
`xcom_push.assert_not_called()` when the flag is off. Case study:
apache/airflow#72151, caught by a reviewer.

## 10.25 Frame an SDK/Core capability gap as feature completion, not a bugfix — but check release state first *(judgment gate)*

**Scope gate**: applies when a branch adds a kwarg/attribute to a Task SDK
class that Core already had (or vice versa), and the PR/commit framing calls
it a "fix."

When one side of a Core/SDK pair (e.g.
`airflow-core/.../partition_mappers/temporal.py` vs
`task-sdk/.../partition_mappers/temporal.py`) gained a kwarg the other side
never got, don't default to "bugfix" framing — verify the introducing
commit's release state first:

1. `git tag --contains <introducing-sha> | grep -E '^3\.'` — **empty is not
   conclusive on its own**: a cherry-pick to a `v<X>-<Y>-test` branch rewrites
   the SHA, so a feature already released via cherry-pick won't show up under
   `--contains` for the original commit.
2. Cross-check by reading the actual release artifact: `git show
   <latest-3.x-tag>:<path>` and `git show upstream/v<X>-<Y>-test:<path>`, and
   compare the surface (kwargs, exported symbols, dispatch body) against
   `main`.

If both checks confirm the capability is missing from every released
artifact → feature completion: no newsfragment, no backport label (same
posture as 10.11's "internal rework, no observable change" case). If a
released tag already ships part of the feature → it is a user-visible bug for
that release and needs a newsfragment plus a `backport-to-v<X>-<Y>-test`
label (same posture as 10.7's breaking-change classification — judge by
actual release state, not by which branch the diff targets).

Also check where the serializer registers its dispatch (e.g.
`airflow.serialization.encoders._Serializer`, registered against SDK
classes). If the SDK class lacked the attribute before the branch, the
encoder was internally consistent — it had nothing to read and nothing to
emit. Don't describe that as "the encoder silently dropped the field";
describe the real gap as "the SDK constructor didn't accept a kwarg the Core
constructor accepted, making the capability unreachable through
`airflow.sdk`."

**How to apply**: for any branch/PR framed as "fix SDK X" or "fix X
serialization," run the two release-state checks above before accepting the
framing, and read the SDK class to see whether the attribute existed
pre-branch. Get both right before requesting a newsfragment/backport label or
accepting "feature completion" framing.

## 10.26 `common.ai` vendor enumeration must come from `infer_provider_class`, not `known_model_names()` *(Request changes)*

**Scope gate**: extends 10.18's three parity axes for `providers/common/ai` —
applies when a diff enumerates, tests, or documents which vendors a
`pydanticai` connection can reach.

The authoritative source for "which vendors can this connection reach" is
`pydantic_ai.providers.infer_provider_class`'s accepted string set, not
`pydantic_ai.models.known_model_names()`. The reason is the resolution path
itself: `PydanticAIHook.get_conn()` hands the user's model string to
`infer_model(model_name, provider_factory=infer_provider_class)`
(`providers/common/ai/src/airflow/providers/common/ai/hooks/pydantic_ai.py:170-184`),
so reachability is defined by what `infer_provider_class` accepts, not by
which vendors happen to have pre-listed model names.

Enumerating from `known_model_names()` alone produces three concrete errors:
it drops already-supported vendors that have no model-name prefix (e.g.
`ollama`); it misses OpenAI-compatible routing layers with no models of their
own (e.g. `openrouter`, `litellm`, `vercel`); and it needs the
`gateway/<vendor>:<model>` prefix handled separately — that vendor set is a
subset of the direct set, but `gateway` itself is a separately-reachable
service and must be listed on its own.

Two further filters apply before a module name counts as a real vendor:
**unreachable** modules (e.g. `voyageai`, `sentence_transformers`) exist under
`pydantic_ai.providers` but raise `UserError: Unknown model` from
`infer_model` — the exception type itself is the discriminator (unreachable
raises `UserError`; reachable raises a stub's `AttributeError` instead); and
**reachable-but-deprecated** vendors (e.g. a retired API whose upstream
provider class is marked `@deprecated` with its backend already shut down)
should be excluded from anything user-facing even though the module still
resolves, on the basis that listing a shut-down vendor is worse than omitting
it.

**How to apply**: don't generate this list via docs-build-time import (the
result depends on which optional extras happen to be installed on the build
machine, and would drift from what `provider.yaml` declares). Treat
`provider.yaml` as the single source of truth, and gate it with a
**two-directional** set-equality test (a one-directional subset check lets a
missing vendor pass silently) comparing `provider.yaml`'s declared connection
types against `infer_provider_class`'s accepted strings, with any exclusions
named explicitly and each carrying a one-line justification comment.

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

### Not just `uv sync`/`uv lock` — any `uv run <cmd>` triggers it too

The trigger point is wider than the two commands above. `uv run` implicit-syncs the
environment before executing, so a command that has nothing to do with the
lockfile — `uv run ruff format <file>`, `uv run ruff check --fix <file>`, `uv run
pytest ...` — surfaces the exact same phantom `uv.lock` diff the first time it runs
against a workspace that already has pyproject↔lockfile drift. Treat it identically
to the `uv sync`/`uv lock` case: `git status --short` after any `uv run` call, and
`git checkout HEAD -- uv.lock` on sight if it shows up. It is not evidence you broke
something.

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

## `provider.yaml`'s `ui-field-behaviour`/`conn-fields` override the hook's `get_ui_field_behaviour()` entirely (narrow — read when a diff changes connection-form UI text)

**Scope note**: applies when a diff changes a connection type's user-visible
field text (placeholder, label, hidden fields, external-services) by editing
a hook's Python methods.

`ProvidersManager._import_hook` first computes `ui_metadata_loaded =
conn_config is not None and bool(conn_config.get("conn-fields") or
conn_config.get("ui-field-behaviour"))`, and only falls back to the hook's
`get_connection_form_widgets()` / `get_ui_field_behaviour()` when that is
**False**. Once a connection type's `provider.yaml` entry declares
`conn-fields` or `ui-field-behaviour`, the hook's same-named Python method
becomes dead code — every placeholder, relabeling, and hidden-field the
connection UI (and the provider registry) shows for that connection type
comes from `provider.yaml`.

**How to apply**: to change a connection type's user-visible field text,
treat `provider.yaml` as the only source of truth — edit it, then run `prek
run update-providers-build-files --files providers/<p>/provider.yaml` to
regenerate `get_provider_info.py` (a generated file — never hand-edit it).
The reverse also applies when checking whether a stale claim has been fully
cleaned up: enumerate `provider.yaml` alongside the hook source and docs —
grepping only the hook's Python file and docs misses the file that actually
drives the UI. Case study: apache/airflow#72013 (fixing `LlamaIndexHook`'s
false claim of Ollama/vLLM support) initially edited only the docs and
`hooks/llamaindex.py`'s `get_ui_field_behaviour()`; review caught that the
connection UI and provider registry both read `provider.yaml`, so the edited
method was dead code and the false claim was still user-visible.

## Migration PR conventions (narrow — read only when the diff touches `airflow-core/src/airflow/migrations/`)

**Scope note**: this only applies when a diff touches
`airflow-core/src/airflow/migrations/`. Skip it entirely otherwise.

### Rebasing onto a new head requires four synced sites, not two

If the PR adds a new migration and rebasing onto `main` pulls in a
**different** new migration, a conflict is guaranteed — but `git` only marks
**two** of the four sites that actually need updating:

1. **Migration filename's numeric prefix** (`0131_3_4_0_xxx.py` →
   `0132_3_4_0_xxx.py`, via `git mv`) — `main` already claimed `0131_`, and a
   numeric collision produces no git conflict, so it passes through silently.
2. **Two lines inside the file**: `down_revision = "<main's new head>"`, and
   the matching `Revises: <same id>` in the docstring — the docstring line is
   easy to miss since nothing points at it.
3. **`airflow-core/src/airflow/utils/db.py`'s `_REVISION_HEADS_MAP`** — the
   entry for that Airflow version must point at *your* revision (you are the
   new head). Git does flag a conflict here.
4. **`airflow-core/docs/migrations-ref.rst`'s table** — your row's
   `Revises ID` must point at main's new revision while keeping the `(head)`
   marker, **and** main's newly added row must be re-added — a three-way
   merge keeps only one side's row, not both. Git does flag a conflict here.

Confirm the chain is actually linked (more reliable than eyeballing):

```bash
cd airflow-core/src/airflow/migrations/versions
grep -H -E '^(revision|down_revision) = ' 01[23]*.py
```

`revision`/`down_revision` should chain head-to-tail with exactly one head.
Verify site 4 with `prek run --from-ref main --stage pre-commit`'s
`Update migration ref doc` hook (it regenerates `migrations-ref.rst`; a pass
confirms the table is right). Verify sites 1–3 with
`prek run migration-round-trip --hook-stage manual --all-files`.

### A migration touching a parent table needs `disable_sqlite_fkeys` around the whole body

A new migration that uses `op.batch_alter_table()` on a **parent table** (one
a child table declares `ON DELETE CASCADE` against — `dag` is the most common)
must wrap the **entire body** of both `upgrade()` and `downgrade()` in
`disable_sqlite_fkeys(op)`:

```python
from airflow.migrations.utils import disable_sqlite_fkeys


def downgrade():
    with disable_sqlite_fkeys(op):
        with op.batch_alter_table("dag", schema=None) as batch_op:
            batch_op.drop_column("...")
```

**Why**: SQLite has no real `DROP COLUMN`; alembic's batch mode rebuilds the
table (create temp → insert-select → drop → rename). During that rebuild the
FK is still enforced, so `DROP TABLE dag` raises `IntegrityError: FOREIGN KEY
constraint failed`. Worse, `PRAGMA foreign_keys` only takes effect while the
connection is in autocommit mode — the batch rebuild's internal `INSERT`
takes the connection out of autocommit, so a `disable_sqlite_fkeys` call
placed **after** that point is a silent no-op. The convention is therefore
stricter than the underlying rule: always wrap the outermost scope, never
narrow it down. Wrap `upgrade()` too even if it's "just" an `add_column` —
at write time it's hard to predict whether a given `batch_alter_table` will
trigger a rebuild.

**How to apply**:

1. Copy the shape from an existing migration in the same repo that already
   does this correctly rather than inventing a new pattern.
2. **Local `prek run --stage pre-commit` does not catch this** — the
   round-trip hook is registered under `stages: [manual]`. Verify locally
   with `prek run migration-round-trip --hook-stage manual --all-files`
   (runs through Breeze, takes minutes; first run may build the image).
3. The corresponding CI job is `Migration round-trip check`, which only
   triggers when the diff touches
   `airflow-core/src/airflow/migrations/`.
4. Authoritative doc: `contributing-docs/26_migration_round_trip_check.rst`.

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

### Commit body is a contract — the `SharedStreamManager` case

`airflow.triggers.shared_stream.SharedStreamManager`'s module docstring and
`event-scheduling.rst` both promised an at-most-one-in-flight guarantee in
ack mode — "the producer waits for acks before yielding the next event." The
actual code does not implement this: `_poll` is a plain `async for` over
`open_shared_stream`, and nothing awaits an outstanding ack between
iterations. The real backpressure comes entirely from the **subscriber
queue's bound** — a full queue force-fails that subscriber with `QueueFull`,
which is a different mechanism than the documented one and a different
failure mode for callers who design around the doc's promise (e.g. an
SQS/Kafka producer built assuming at-most-one-in-flight). A green test suite
does not catch this class of defect, because it's a mismatch between the
documented contract and the code, not a logic bug — treat any "producer
waits for acks" / "does not yield until all subscribers ack" phrasing in
ack-mode shared-stream docs or docstrings as a claim to verify against the
actual `_poll` implementation, and require the wording rewritten to describe
queue-bounded backpressure (full queue force-fails the subscriber) rather
than producer-side awaiting.

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
