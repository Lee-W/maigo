---
name: airflow-aware
description: This skill should be used when working in the apache/airflow repository as a contributor (not as a Dag author). It surfaces the conventions Airflow's own AGENTS.md enforces — naming, Breeze/uv environment, Ruff/Mypy style, coding rules, pytest patterns, PR hygiene — so any task (review, quick-fix, refactor) in airflow follows them.
---

<!-- mkdocs-include-start -->

# Airflow-Aware

**Loaded by**: `repo-detect` hook (SessionStart) when `apache/airflow` is detected in git remote or file structure.
**Applies to**: Any skill execution within an Apache Airflow contributor checkout — review, quick-fix, refactoring, or otherwise.

## When to apply

This is a **knowledge layer**, not a review checklist.
It is loaded automatically by the
[`repo_detect` hook](https://github.com/Lee-W/maigo/blob/main/hooks/repo_detect.py)
at session start when an Apache Airflow repo is detected.
It mirrors and supplements the repo's own `AGENTS.md` / `CLAUDE.md`, condensed for agent context.

It can also be triggered manually via a memory entry with `triggers: [airflow-aware]`
(see [Memory-triggered skill loading](https://github.com/Lee-W/maigo/blob/main/docs/reference/skills.md#memory-triggered-skill-載入)).

Once loaded, treat every convention as background — do not re-read each task.

## Contributor conventions

### 1. Read AGENTS.md first — it wins

The single source of truth for contributor conventions lives in the repo itself. This skill is a
condensed onramp formatted for agent startup context, not a competing authority.

1. **First action**: read [`AGENTS.md`](https://github.com/apache/airflow/blob/main/AGENTS.md)
   (or `CLAUDE.md` — both are identical, 455 lines).
2. **Conflict resolution**: if anything in this skill contradicts `AGENTS.md`, the repo file wins.
3. **Review tasks**: also read
   [`.github/instructions/code-review.instructions.md`](https://github.com/apache/airflow/blob/main/.github/instructions/code-review.instructions.md)
   for review-specific guidance.

### 2. Naming — Dag (prose) vs `DAG` (code)

In **prose**, write `Dag` (title case) — never all-caps `DAG` unless referring to the Python
class, and never expand "Directed Acyclic Graph". **Code tokens stay as-is**: class `DAG`,
`dag_id`, `airflow dags list`, `dag_processing/`, `DAG_FOLDER`. See the "Naming" section of
`AGENTS.md` when in doubt.

#### Naming hook false positives

The airflow-workspace naming hook (fires on Edit/Write, reports "RULE VIOLATION",
commands "Fix all occurrences now") is a **pure string match** — it fires on any
all-caps `DAG` spelling anywhere in the file, with no awareness of the naming rule's
own exceptions (Python code tokens, CLI commands, paths/config keys, URLs, anti-pattern
quotes that intentionally show the wrong form — all of these must stay literal).

When it fires:

1. `grep -n` list every hit in the file.
2. Classify each hit as prose-violation vs literal-exception against the exception list above.
3. Only fix the prose violations. If every hit is a literal exception, say so explicitly
   in the reply (with the classification) and don't touch the file.

Note: a file that *discusses* this naming rule itself (like this skill file) will always
trip the hook — that's expected, not a bug to fix.

#### Historical archival files are exempt — never rewrite past entries

`airflow-core/docs/migrations-ref.rst` and `RELEASE_NOTES.rst` /
`CHANGELOG.rst` (including provider `changelog.rst` files) reproduce
historical record verbatim — a migration revision's original message, or a
past PR's shipped title. Existing all-caps/lowercase spellings in those
**past entries** are not to be rewritten to `Dag`, even when a naming-rule
hook fires on them. Rewriting them silently changes the historical record and
breaks the `git log` ↔ release-note correspondence for past PRs. When scoped
to fixing something else in one of these files (e.g. a spell-check nit),
touch only the offending line; ignore the naming hook for pre-existing
all-caps occurrences elsewhere in the same file — don't pre-emptively "fix"
them. **New** entries appended to these files still follow the normal Dag
naming rule; only existing historical rows are exempt.

### 3. Environment — Breeze + uv + prek

Do **not** run `pytest`, `mypy`, or `pre-commit` directly on the host.
Use the Breeze container or `uv run --project <PROJECT>` for isolation.
Airflow is a monorepo; dependency isolation relies on `--project`.

```bash
# run tests for a specific project
uv run --project airflow-core pytest tests/unit/foo/test_bar.py

# format and lint
uv run --project airflow-core ruff format src/
uv run --project airflow-core ruff check --fix src/

# pre-commit equivalent (use prek, not pre-commit)
prek run --all-files
```

Scratch scripts go in `dev/` — not in repo root or `scripts/`.

Note: `prek` is the runner currently specified by upstream. It is compatible with the same hooks as `pre-commit`.

#### Before building a new prek hook: surface the genericity/fragility trade-off first

Before adding a new prek hook, answer two questions **up front** and surface
them to the user for sign-off — don't wait until the hook is fully
implemented (with tests, registered in `.pre-commit-config.yaml`) before the
user gets a chance to reconsider:

1. Do sibling checks already exist for a similar concern? A CI gate scoped to
   only one provider/module when siblings have no equivalent check is an
   inconsistent precedent worth calling out.
2. Will the check false-positive on a small, unrelated change (a doc
   reformat, a cross-reference restyling)? A brittle detection heuristic
   costs more in false-positive triage than it saves.

Beyond that up-front check, prefer **dynamic discovery over hardcoded
references** — e.g. walk a migration chain via its own directory/API rather
than hardcoding specific revision IDs, so a new entry added later is
automatically in scope without a script edit. And stop to simplify when a
hook's design starts accreting per-version matrices, baseline files, or
regenerate-baseline flags — a design that doubles in complexity in one
session usually has a simpler alternative (e.g. collapsing to a single
linear walk with no baseline) that gives the same coverage.

#### `uv run --project` vs `--directory` danger zone

In an Airflow worktree, `uv run --directory "$WT" <cmd>` is safe — it uses the
existing venv for that directory and does not trigger a re-resolve.

`uv run --project "$WT" <cmd>` only becomes dangerous when `$WT` is the
**whole worktree root**: that triggers a full workspace-level dependency
resolve, which pulls in `apache-airflow[all]` → `apache-airflow-providers-jdbc`
→ `jpype1`. Building `jpype1` needs Java, and macOS's default `/usr/bin/java`
is an empty stub, so the build fails at CMake's `find_package(Java)` step.

`uv run --project airflow-core <cmd>` (pointing at a monorepo **sub-project
name**, not a worktree path — as in the example above) is a different, safe
usage: it resolves only that sub-project's dependency set, not the whole
workspace. Don't conflate the two — the danger is specific to `--project` at
a worktree root, not to `--project` itself.

#### `verify_completion` in this repo

`repo_detect` writes `.claude/skip-test-verification` on first detection so the
Stop-hook does not try to run a host-side `uv run pytest` (which pulls `jpype1`
→ cmake `FindJava` and fails on machines without a JDK; the 90s timeout also
cannot cover any Airflow subproject's suite). To re-enable verification for a
focused area, delete that file or replace it with a targeted
`.claude/test-command` such as
`uv run --project airflow-core pytest tests/unit/<path>/test_<file>.py`.

**jpype1 fallback**: if the Stop-hook still encounters a `jpype1` / `cmake` /
`FindJava` error (because `.claude/skip-test-verification` was missing or the
hook executed before `repo_detect` had a chance to write it), treat it as a
**known upstream constraint** and move on. Do not try to install a JDK, patch
`jpype1` import paths, or rewire the lock file — those are upstream issues, not
part of any maigo task scope. If verification was genuinely needed, run a
targeted single-file pytest manually instead.

#### `uv.lock` phantom diff diagnostic

A persistent `uv.lock` diff you did not introduce — and that returns after
`git checkout HEAD -- uv.lock` + the next `uv sync` — is almost always
**lockfile drift on `main`** (a contributor edited a `pyproject.toml` without
re-running `uv lock`), not a local environment problem. Don't fold the
re-lock into your feature PR; `git checkout HEAD -- uv.lock` keeps the noise
out, and the diff re-appearing on the next `uv sync` is expected.

Full diagnostic — confirm the drift, find when it was introduced, worked case
study, and how to handle in a feature PR — is in the "uv.lock drift diagnostic"
section of `references/review-checks.md`.

### 4. Code style — Ruff + Mypy

- Formatter: `uv run ruff format`
- Linter: `uv run ruff check --fix`
- **Line length: 110** (not the Ruff default of 88 — agents most often miss this)
- **New files require the Apache License header** — copy it verbatim from any existing `.py`
  file in the repo (do not hand-retype it).
- Mypy is run via `prek` — do not invoke it directly on the host.

### 5. Coding rules agents most often miss

These are extracted from the "Coding rules" section of `AGENTS.md`. They are listed here
because they are the conventions agents most frequently overlook.

For the extended recipes on import placement (top-level vs `TYPE_CHECKING` vs
lazy, plain name over alias, shadowing-parameter rename), class-docstring
`:param` conventions (including dropping boilerplate `__init__` lead-ins),
user-facing docstring wording, naming/constant conventions, raise-vs-document
validation posture, dropping manually-enumerated invariants once a check
enforces them, mypy `Optional` narrowing via branch restructure, new prek
hook script conventions, and the "no `logical_date` in Airflow 3 examples"
authoring rule, read `references/code-style.md`.

- **No `assert` in production code** — use a real exception (e.g., `ValueError`, `RuntimeError`).
- **Do not add new `raise AirflowException`** — use a more specific exception class instead.
- **`session` parameter must be keyword-only** and the callee must not call `session.commit()`;
  transaction management is the caller's responsibility.
- **Use `time.monotonic()`** for elapsed-time measurement — not `time.time()`.
- **Imports go at the top of the file** — no function-local imports unless the comment
  explicitly notes a circular dependency, lazy load, or `TYPE_CHECKING` guard.
- **`__init__` and always-called functions: default to top-level imports.** Reserve the
  lazy / function-body form for exactly four cases: (1) `TYPE_CHECKING` block, (2) breaking
  a known circular-import cycle, (3) multi-process worker-isolation path, (4) deferred-execution
  callback (e.g., a `deserialize()` body that is not called at module import time).
  Self-check: "does this function run on every public touch of the class?" If yes → top-level.
  Note: §10.3 and §10.4 address distinct but adjacent rules — Unix-only module gates and heavy
  type-only imports in multi-process paths; this rule is about the default for eager call sites.

### 6. Delivery completeness

User-facing features (new public class / SDK symbol / scheduling behaviour) must ship
**all three** deliverables in the same PR:

1. **Implementation + tests** — the obvious part.
2. **Example Dag** — fold into an **existing** example file (e.g., `example_asset_partition.py`);
   reuse the existing block style and existing asset/producer objects. Do **not** open a new
   example file or add a bare new `with DAG(...)` block — consistent with the
   "don't proliferate example Dags" convention.
3. **Docs update** — update the relevant `.rst` (e.g., `airflow-core/docs/authoring-and-scheduling/assets.rst`).
   Prose uses "Dag"; known limitations are written as constraints, not `# TODO` placeholders.

**Public-symbol sync (docs side):** whenever a public symbol is added or removed,
`task-sdk/docs/api.rst` and the corresponding `airflow-core/docs/` `.. autoapiclass::` entries
must be updated together with `__init__.py` / `__all__` / lazy-import table.
Dropping a removed symbol and adding a new one are both required — a missing deletion causes
`breeze build-docs` to crash at Sphinx import time; a missing addition causes a silent gap
in the API reference. After editing, `grep` the old symbol name across `docs/` to confirm
no stale references remain.

Why: apache/airflow PR #64571 (`Window` / `RollupMapper`) and the partition-mapper
refactor both shipped with example + docs in the same PR; missing either was flagged in
round-1 review.

#### QA / status-doc conventions

When drafting or reviewing a manual QA plan, feature-coverage matrix, or
status doc for a feature that ships:

- **Don't add a "serialization round-trip" manual QA item.** The scheduler
  only ever reads serialized Dags, so every functional test in the plan
  already exercises the deserialized form implicitly — a broken round-trip
  would make those functional checks fail first. Field-level lossless
  round-trip belongs in a pytest unit test, not a manual QA row. The one
  legitimate manual touch is a first-time smoke glance at the
  `serialized_dag` JSON when a brand-new param ships — that's dev smoke, not
  a recurring QA item.
- **Don't leave "not done yet" signals in a status/QA doc meant to record
  completed work** — drop header decorations like `✅ merged` / `🚧` / `❌ not
  native`, and avoid absence-wording for deliberately-scoped behavior
  (`not implemented`, `scoped out`, `ad-hoc`/`throwaway` for a fixture).
  Describe an intentionally-scoped feature positively as the current design,
  not as a gap measured against something that was never built. An **empty**
  results column (template waiting to be filled) is fine — that's not a
  not-done signal. Once a results column is actually **filled**, a per-row
  `✅ Pass (...)` marking the verification method is good practice — the
  no-decoration rule governs headers/progress marks and "not done" phrasing,
  not a factual pass/fail record.
- **A defect found in the example Dag / test fixture while QA-ing a feature
  is in scope to fix**, not just to log. If the bug is in the shipped example
  producer/consumer rather than the feature under test, fix it and fold the
  fix into the same PR (ask before editing the shared artifact) — a broken
  example is a broken user-facing artifact, and fixing it is part of
  finishing the QA.

### 7. Testing

- **pytest only** — do not subclass `unittest.TestCase`.
- **All mocks must have `spec=` or `autospec=True`** — bare `MagicMock()` without a spec is not acceptable.
- **Use `assert_*` methods for mock assertions** (`assert_called_once_with`, `assert_called_with`,
  `assert_not_called`, etc.) — do not compare `.mock_calls` lists directly.
  The `assert_*` methods verify calling signature and raise a clear failure message;
  raw list comparison is fragile and obscures intent.
- **Time-dependent tests use `time_machine`** — do not monkey-patch `datetime.now` manually.
- **DB-touching tests must be marked `@pytest.mark.db_test`**.
- **Do not use `caplog`** — Airflow has a different approach to log assertion; see the
  "Testing" section of [`AGENTS.md`](https://github.com/apache/airflow/blob/main/AGENTS.md)
  for the prescribed pattern. The typical alternative is to attach a mock log handler and use
  its `assert_called_once_with` or other `assert_*` methods to verify the calling signature
  rather than inspecting `caplog` output.
- **Test paths mirror source paths**:
  `airflow-core/src/airflow/foo/bar.py` ↔ `airflow-core/tests/unit/foo/test_bar.py`

### 8. PR / commit / newsfragment

- Write commit messages and PR titles from the **user-impact perspective** — describe what
  changes for users, not which files were touched.
- Agent-opened PRs must include a `Generated-by:` footer in the PR body
  (see the "Pull requests" section of `AGENTS.md` for the exact format).
- **Newsfragments are only required** for changes to `airflow-core/`, `chart/`, or `dev/mypy/`.
  Changes in other subdirectories do not need one.
- **Imminent fixes** (obvious bugs, small refactors with no design question) can go straight
  to a PR — no need to open an issue first.

### 9. Architecture boundaries *(optional, for architectural review)*

Airflow's subsystems have strict ownership boundaries that must not be crossed:

- **Scheduler** does not execute user code.
- **Worker** does not write to the metadata DB directly.
- **Providers** do not import from `airflow` core internals.
- **Task SDK** is isolated from scheduler/worker internals.

Cross-boundary changes require extra scrutiny. Before proposing or reviewing such a change,
read
[`.github/instructions/code-review.instructions.md`](https://github.com/apache/airflow/blob/main/.github/instructions/code-review.instructions.md).

#### Core ↔ SDK paired-class symmetry

Several public APIs exist as paired classes — one in `airflow-core/` and one in
`task-sdk/` with the same conceptual role and the same name (e.g., the temporal
partition mappers `_BaseTemporalMapper` in `airflow.partition_mappers.temporal`
vs `airflow.sdk.definitions.partition_mappers.temporal`). When the two
implementations drift on a **same-named attribute**, the divergence is a
**bug**, not a nit — even if both sides happen to work in practice because
downstream code (encoders, serializers, consumers) tolerates both shapes.

Things to compare side-by-side when reviewing or self-reviewing such a class:

- Constructor signature (kwargs, positional-vs-keyword, defaults).
- Attribute *type* after `__init__` (e.g., is `_timezone` always
  `Timezone | FixedTimezone` on both sides, or is one side keeping a raw
  `str`?).
- Validation / normalization step in `__init__` (e.g., one side runs
  `parse_timezone()`, the other stores verbatim).
- Eager-raise behaviour for invalid input.

Do **not** accept "this can be a separate PR" framing just because the gap
is "merely" a type or validation asymmetry. Fix it in the current PR. The
related question — whether the overall patch is a **bugfix** or **feature
completion**, which determines newsfragment + backport label — is a
separate axis covered by the SDK/Core release-state framing memory
(check release tags via `git tag --contains <sha>` **and** `git show
<tag>:<file>` to confirm).

#### Design-integrity checks (references)

Four more framework/base-API design patterns — declarative type-pairing
guards over override proxies, symmetric paired-parameter naming, the two
independent cost axes of a new hot-loop extension surface, and closing a
framework-internal sum-type structurally rather than visibly — are in
`references/design-integrity.md`. Read it when designing or reviewing a new
base/framework API, a type-pairing guard, or an extension point on the
scheduler/triggerer/API hot loop.

### 10. Review-time-only checks *(loaded as strict-review item 10+)*

When `airflow-aware` is loaded during a **review task** (🟡 Soyo running
`strict-review` on an Airflow diff), read `references/review-checks.md` in this
skill's directory and append its sub-checks as items 10+, with the severity each
sub-check states. The file covers:

- **10.1** Execution API wire-format gate (Block)
- **10.2** Multi-PR split: wire-format symbol cross-check (Block)
- **10.3** Top-level imports of Unix-only modules (Block)
- **10.4** `TYPE_CHECKING` guards for heavy type-only imports (Request changes)
- **10.5** Security finding classification (3-way triage before reporting)
- **10.6** Newsfragment file presence (Request changes)

plus the Airflow case studies backing `strict-review`'s recurring must-fix patterns.
Outside of a review context (quick-fix / refactor), skip the file — these checks
are review-only and do not gate other tasks.

### 11. CLI / REST / docs / backport conventions

#### CLI and REST design consistency

Before designing a new CLI command's semantic, filter, or default, **grep
sibling commands first** — cross-command consistency outranks a per-command
UX win. If a proposed behavior diverges from how sibling commands treat the
same semantic field (e.g. a date-range filter, an end-date clamp), be able to
explain *why* this command deviates; if you can't, align with the siblings
instead. Do this before implementation, not after review blocks it.

When adding a REST endpoint that parallels an existing CLI command, name it
after the **CLI's verb** and the existing REST verb vocabulary, not a more
literally-accurate coined word — e.g. `clearPartitions` (mirroring CLI
`airflow partitions clear` and REST `clearDagRuns`) beats a technically-more-
precise `resetPartitionFields`. Consistency across the user-facing surface
beats per-endpoint pedantic accuracy.

#### Docs authoring

- **"When to use X vs Y" comparison docs** need why (X's core value
  proposition), when (bullets mapped to concrete operator/API names with doc
  links), a mirrored "use Y instead when…" list, and a one-line rule of thumb
  at the end. Find the *real* axis of difference before writing the
  difference section — a surface feature comparison that both sides share
  equally hasn't found the axis yet (e.g. two "agent" operators don't differ
  by whether they have tools/MCP if both do; they differ by where the loop
  executes and who controls the tools).
- **User-facing doc snippets teach the canonical import** — e.g.
  `from airflow.sdk import dag, task` — not a provider-internal compatibility
  shim path, which is only for in-package shipped code.
- **Section headers/labels name the specific things being compared**, not a
  generic count or umbrella ("Two styles of X" teaches nothing — name the
  styles). Keep internal-component words (e.g. "scheduler") out of
  user-facing prose; phrase from the Dag author's observable perspective.
- **`providers/<x>/docs/index.rst` has a hand-written prologue followed by an
  auto-generated block** (marked by an "AUTOMATICALLY GENERATED" comment)
  that gets overwritten at release time. Reordering/placement feedback on
  this file is answered by editing **above** the marker (usually a short
  lead-in sentence), never by moving content at or after it.
- When a new parameter/flag changes user-visible API semantics (e.g. how a
  special character is interpreted in a query param), the **public
  description / OpenAPI spec must be updated in the same change** as the
  code — not left describing the old semantics. Regenerate the spec + client
  after editing.
- **zh-TW locale content**: call it "Taiwanese Mandarin", never "Traditional
  Chinese" — this applies to commit messages, PR text, docs, and comments
  produced for this repo. When translating a UI string, check the repo's
  existing zh-TW translations for established terminology before coining a
  new term.

#### Partitioned / scheduling-range API granularity

Don't type a partitioned/scheduling-range API parameter at `date` granularity
(`datetime.date`) — take `datetime` bounds and walk the timetable's own
cadence instead. A `date`-typed parameter makes a sub-day window structurally
inexpressible, and day-bound expansion logic then silently widens any window
to the whole local day even for an hourly-cadence timetable. When adding or
reviewing timetable/backfill range behavior: pass datetimes and honor bounds
as both-ends-inclusive instants; always add a sub-day cron case
(`"0 * * * *"`) to the tests — day-grained tests alone give a false green on
day-bound bugs.

#### Backport judgment

When a backport branch's drift-check fails because it references something
(a file, a test site) that doesn't exist on that branch, check whether the
**underlying capability** is already present on the branch before deciding
the check should just be narrowed in scope. If the capability shipped but
the newer test coverage for it didn't get backported, the right move is
usually to backport the source PR that added the missing coverage — not to
shrink the check to stop noticing the gap.

## Composing with other skills

This skill pairs with
[`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md).

**Review scenario** — run `strict-review`'s 9-item base checklist as usual, then apply
airflow-aware conventions as Airflow-specific supplements:

- Convention 2 (naming) reinforces the naming check (base item 4).
- Conventions 4 and 5 reinforce the style and correctness checks (base items 5–6).
- Convention 6 (delivery completeness) reinforces the acceptance-match check (base item 1).
- Convention 7 (testing) reinforces the evidence and edge-case checks (base items 2–3).
- **§10 sub-checks (10.1–10.6, in `references/review-checks.md`) become items 10+**
  in the checklist output, with Block / Request-changes severity inherited from each
  sub-section.

**Quick-fix / refactor scenario** — use conventions 3, 4, 5, 6, and 7 as background knowledge.
Flag violations you notice, but do not run the full `strict-review` checklist unless the
task calls for it. §10 sub-checks are review-only — do not gate non-review tasks on them.
