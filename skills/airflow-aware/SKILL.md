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

## Read AGENTS.md first

The single source of truth for contributor conventions lives in the repo itself.

1. **First action**: read [`AGENTS.md`](https://github.com/apache/airflow/blob/main/AGENTS.md)
   (or `CLAUDE.md` — both are identical, 455 lines).
2. **Conflict resolution**: if anything in this skill contradicts `AGENTS.md`, the repo file wins.
   This skill is an onramp and supplement, not a competing authority.
3. **Review tasks**: also read
   [`.github/instructions/code-review.instructions.md`](https://github.com/apache/airflow/blob/main/.github/instructions/code-review.instructions.md)
   for review-specific guidance.

## Contributor conventions

### 1. Defer to AGENTS.md

This skill is an onramp — a condensed version of `AGENTS.md` formatted for agent startup context.
It is not a replacement. Any time a convention here conflicts with what `AGENTS.md` says,
follow `AGENTS.md`. See the [Read AGENTS.md first](#read-agentsmd-first) section above.

### 2. Naming — Dag (prose) vs `DAG` (code)

In **prose and documentation**, use `Dag` (title case): "the Dag will run at midnight".

**Code tokens are always preserved as-is** — do not alter casing:

- class name: `DAG`
- parameter: `dag_id`
- CLI: `airflow dags list`
- directory: `dag_processing/`
- env var: `DAG_FOLDER`

Do **not** expand "Directed Acyclic Graph" in prose — just write `Dag`.
Do **not** write all-caps `DAG` in prose unless you are literally referring to the Python class.

This rule is covered in the "Naming" section of `AGENTS.md`; refer to that section when in doubt.

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

A persistent `uv.lock` diff in your worktree that you did not introduce — and
that returns after `git checkout HEAD -- uv.lock` followed by the next
`uv sync` — is almost always **lockfile drift on `main`**, not a local
environment problem. A contributor edited a `pyproject.toml` (e.g., removed
an extra) without re-running `uv lock`, so the committed lockfile is out of
sync with the committed pyproject; every fresh `uv sync` regenerates the lock
to match the current pyproject and shows the delta as an uncommitted diff.

Diagnose:

```bash
git diff HEAD uv.lock | head -50               # what package changed
grep -rn "<package>" --include=pyproject.toml -l    # which pyproject owns it
grep "<package>" <pyproject>                   # current HEAD declares it?
git show HEAD:uv.lock | grep "<package>"       # committed lock has it?
```

If the pyproject and the committed lock disagree, drift is confirmed. Fix it
in a **separate** `chore: re-lock <pyproject>` PR off `upstream/main`. **Do
not** fold the lock regeneration into the current feature PR — it pollutes
the diff and creates a force-push risk if `main` re-locks before merge. For
the feature PR, `git checkout HEAD -- uv.lock` keeps the noise out of the
commit; the diff will re-appear locally on the next `uv sync` and that is
expected.

### 4. Code style — Ruff + Mypy

- Formatter: `uv run ruff format`
- Linter: `uv run ruff check --fix`
- **Line length: 110** (not the Ruff default of 88 — agents most often miss this)
- **New files require an Apache License header**:

```python
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
```

- Mypy is run via `prek` — do not invoke it directly on the host.

### 5. Coding rules agents most often miss

These are extracted from the "Coding rules" section of `AGENTS.md`. They are listed here
because they are the conventions agents most frequently overlook.

- **No `assert` in production code** — use a real exception (e.g., `ValueError`, `RuntimeError`).
- **Do not add new `raise AirflowException`** — use a more specific exception class instead.
- **`session` parameter must be keyword-only** and the callee must not call `session.commit()`;
  transaction management is the caller's responsibility.
- **Use `time.monotonic()`** for elapsed-time measurement — not `time.time()`.
- **Imports go at the top of the file** — no function-local imports unless the comment
  explicitly notes a circular dependency, lazy load, or `TYPE_CHECKING` guard.

### 6. Testing

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

### 7. PR / commit / newsfragment

- Write commit messages and PR titles from the **user-impact perspective** — describe what
  changes for users, not which files were touched.
- Agent-opened PRs must include a `Generated-by:` footer in the PR body
  (see the "Pull requests" section of `AGENTS.md` for the exact format).
- **Newsfragments are only required** for changes to `airflow-core/`, `chart/`, or `dev/mypy/`.
  Changes in other subdirectories do not need one.
- **Imminent fixes** (obvious bugs, small refactors with no design question) can go straight
  to a PR — no need to open an issue first.

### 8. Architecture boundaries *(optional, for architectural review)*

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

### 9. Review-time-only checks *(loaded as strict-review item 10+)*

When `airflow-aware` is loaded during a review task (🟡 Soyo running `strict-review`
on an Airflow diff), the following Airflow-specific checks supplement the base 9-item
checklist as items 10+. Outside of a review context (quick-fix / refactor) they
are useful background but not a checklist gate.

#### 9.1 Execution API wire-format gate *(Block-level)*

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

#### 9.2 Multi-PR split: wire-format symbol cross-check

If the PR body says "PR N of M", "split from #NNNNN", "consumes what was added in
#NNNNN", or `cc:` mentions the same reviewer across sibling PRs, fetch the sibling
PR's diff (`gh pr diff <sibling> --repo apache/airflow`) and compare wire-format /
API field names character-for-character (singular vs plural, underscore placement,
casing, type — e.g. `list[str]` vs `str`).

Mismatches are typically **Block-level**: silent end-to-end breakage that the PR's
own tests will not catch because they're self-consistent against the wrong shape.
Past examples: #66699 renamed `retention_days` → `expires_at` in prod but not tests;
#66782 consumer reads `partition_key` while #65447 producer emits `partition_keys`.

#### 9.3 Top-level imports of Unix-only modules

Top-level imports of `fcntl`, `pwd`, `grp`, or `resource` break Windows.
Flag as **Block** unless the whole file is Unix-gated (e.g., `sys.platform != "win32"`
guard at module top, or the file lives under a `_unix` / `_posix` submodule).

#### 9.4 `TYPE_CHECKING` guards for heavy type-only imports

In multi-process code paths (scheduler, Dag File Processor, triggerer, worker), heavy
type-only imports (e.g., `kubernetes.client`, `boto3`, `google.cloud.*`) must be
guarded by `if TYPE_CHECKING:` — pulling them into every fork balloons memory and
startup time. Flag as **Request changes**.

#### 9.5 Security finding classification

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

#### 9.6 Newsfragment file presence

If the diff modifies code under `airflow-core/`, `chart/`, or `dev/mypy/` and is
user-visible (feature / bugfix / breaking change / doc change with user impact),
look for a matching
`<distribution>/newsfragments/{PR_NUMBER}.{bugfix|feature|improvement|doc|misc|significant}.rst`
file in the diff. Missing → flag as **Request changes** (not Block).
**Do not** require newsfragments for changes under `providers/` or `airflow-ctl/`
— their release managers regenerate the changelog from `git log`.

## Composing with other skills

This skill pairs with
[`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md).

**Review scenario** — run `strict-review`'s 9-item base checklist as usual, then apply
airflow-aware conventions as Airflow-specific supplements:

- Convention 2 (naming) reinforces the naming check (base item 4).
- Conventions 4 and 5 reinforce the style and correctness checks (base items 5–6).
- Convention 6 (testing) reinforces the evidence and edge-case checks (base items 2–3).
- **§9 sub-checks (9.1–9.6) become items 10+** in the checklist output, with Block /
  Request-changes severity inherited from each sub-section.

**Quick-fix / refactor scenario** — use conventions 3, 4, 5, and 6 as background knowledge.
Flag violations you notice, but do not run the full `strict-review` checklist unless the
task calls for it. §9 sub-checks are review-only — do not gate non-review tasks on them.
