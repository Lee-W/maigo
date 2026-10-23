# Airflow verification tooling — false-green shapes, coverage gaps, local false-reds, attribution

Loaded on demand by `skills/airflow-aware/SKILL.md` — apache/airflow-specific
failure modes of `prek`, `pytest`, and the local UI/dependency toolchain that
recur often enough to warrant a shared reference. Read this file before
trusting a "Passed" / "exit 0" as evidence in this repo, or when a test run
gives a confusing or unstable result.

---

## 1. False-green shapes in `prek`

`prek run` reporting `exit 0` is not by itself evidence a hook actually
checked your change. Several distinct mechanisms can produce a clean-looking
run that checked nothing, or checked the wrong content. The general hook-runner
shapes (stashing of unstaged changes, zsh word-splitting of `--files`, `git add -N`,
`git rebase --continue` running no hooks, a `files:` regex that never matches, a corrupted
toolchain cache) are in
[`git-workflow`'s `hook-runner-verification.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/hook-runner-verification.md);
only the Airflow-specific ones are listed here.

Reproduce a hook failure from the repo root (see that file) — with one Airflow exception:
deliberately running from `providers/` is acceptable to avoid a root-level lychee SSH failure
that is unrelated to your change, never to make the target hook pass.

### The `identity` hook can report a false "files were modified" failure

`identity` (labeled "Print checked files") never modifies anything — it's
just where prek's "was this file touched before the hook ran" bookkeeping
gets reported when a *different* hook doesn't claim the change first. If a
commit is blocked with `Print checked files ... files were modified by this
hook`, but `git status --short` shows the working tree matches the index
exactly, that's a false signal. Confirm before dismissing it: run the full
pre-commit stage on just those files (`prek run --files "path/a.py"
"path/b.py"`, quoting each path individually to dodge the zsh word-splitting trap described in `harness-discipline`'s `shell-and-tool-gotchas.md`);
exit 0 and zero modifications means the false signal is real. Escape hatch:
`git commit --no-verify`, then separately run the commit-msg hook against
the already-written message so it isn't silently skipped.

## 2. Coverage gaps — prek passing doesn't mean the thing you care about ran

Beyond false greens, several prek hooks have **narrower real coverage than
their name or config implies**. A clean prek run in these cases is honest
about what it checked — the gap is that it checked less than expected.

### The mypy hooks do not cover `providers/`

prek's mypy hooks (`mypy-airflow-core`, `mypy-task-sdk`, `mypy-shared-*`, …)
never run against `providers/`. Provider type-checking runs separately via
`breeze run mypy <path>` (or `uv run --project providers/<name> mypy <files>`)
and is not in the hook set at all. A provider PR with "`prek run --files
<changed>` all Passed" is **not** evidence of type correctness — ruff,
ruff-format, and similar hooks all report clean while mypy simply never ran.
A provider PR's acceptance criteria must list pytest **and** mypy as
separate items; `prek` alone cannot stand in for the type-check gate.

### The UI compile hook doesn't rebuild `dist/`

`ts-compile-lint-ui` runs `eslint --fix`, `prettier --write`, and `tsc` in
`airflow-core/src/airflow/ui` — it never runs `pnpm build`, so it never
refreshes `airflow-core/src/airflow/ui/dist/`. The api-server serves
`/static` from that `dist/` directory
(`api_fastapi/core_api/app.py`), so running this hook after adding, say, a
new i18n key and expecting a live server to pick it up is a no-op. The hook
that actually produces `dist/` is `compile-ui-assets`, registered under the
**manual** stage:

```bash
cd airflow-core && uv run prek run compile-ui-assets --all-files --stage manual
```

`breeze start-airflow` (without `--dev-mode`) kicks that build off in the
*background*, so a page loaded too early still serves the previous bundle;
`--dev-mode` sidesteps the race entirely by mounting locale files straight
from source. Acceptance criteria for UI work that name only `eslint` and
`tsc` also miss `prettier` — a formatting-only violation still fails the
first `git commit` via `files were modified by this hook`, with the fix
already silently applied to the working tree by the time you retry.

### `ruff-format` ignores its declared file list — never use its `types_or` to argue scope

`ruff` (lint) and `ruff-format` look symmetrical in `.pre-commit-config.yaml`
but behave differently: the lint hook's `entry: ruff check --force-exclude`
receives prek's matched filenames, so its `types_or`/`exclude` genuinely
scope it. `ruff-format`'s entry is a three-line wrapper script that calls
`ruff format --force-exclude` with **no file arguments** at all, letting
ruff do its own discovery — the file list prek computed is discarded, so
this hook's `types_or`/`exclude` restrict nothing. Since ruff 0.16 this
includes Python code blocks embedded in Markdown. Never reason "this hook's
`types_or` is `[python, pyi]`, so my `.md` change can't be touched by it" —
that inference only holds for the lint hook. Settle it empirically: revert
the file, run `prek run ruff-format --all-files`, and see whether it reports
`files were modified by this hook`.

### prek hooks live in per-distribution configs, not just the root one

apache/airflow has a root `.pre-commit-config.yaml` **and** one per
distribution (at least `airflow-core/`, `airflow-ctl/`, `scripts/`, `dev/`,
`dev/mypy/`, `go-sdk/`, `ts-sdk/`, `kubernetes-tests/`,
`airflow-e2e-tests/`, `task-sdk-integration-tests/`). A hook id absent from
the root config is not absent from the repo — all the UI hooks
(`ts-compile-lint-ui`, `compile-ui-assets`, `check-i18n-json`,
`mypy-airflow-core`, …) live only in `airflow-core/.pre-commit-config.yaml`.
Before asserting "there is no prek hook for X," enumerate every config:

```bash
find . -name .pre-commit-config.yaml -not -path "*/node_modules/*"
grep -rn "id: .*<thing>" $(find . -name .pre-commit-config.yaml)
```

Each sub-config's `files:` patterns and `entry:` paths are also relative to
*that config's directory* — invoke those hooks from that directory
(`cd airflow-core && uv run prek run <hook> --files "src/airflow/ui/..."`),
not from the repo root.

### `scripts/in_container/run_provider_yaml_files_check.py` cannot be pytest-unit-tested — verify by behavior instead

This validator script is blocked from pytest coverage by three independent
mechanisms (confirmed by trying both the unit-test and subprocess routes):

1. **An import guard** — `if __name__ != "__main__": raise SystemExit(...)`
   at the top of the file — blocks importing it to call its internal
   `check_*` functions directly. This is not the general convention for
   `scripts/in_container/` — of ~25 scripts there, only this one has the
   guard; a sibling script without the guard is exactly what makes
   `scripts/tests/in_container/test_run_generate_constraints.py`'s
   import-based test possible.
2. **`AIRFLOW_ROOT_PATH` cannot be overridden** — it's hardcoded as
   `Path(__file__).resolve().parents[2]` with no env-var escape hatch, so
   even a subprocess invocation can only ever act on the real repo tree, not
   a tmp fixture. Testing a "broken input" case means mutating a real
   `providers/<p>/provider.yaml` and reverting it — a test that mutates a
   tracked file, leaves the tree dirty on failure, and races with a parallel
   run (the corresponding prek hook is itself marked `require_serial: true`).
3. **The most disqualifying one: it wrecks the dev environment on
   startup.** The script's `sync_dependencies_without_dev()` runs `uv sync
   --no-dev --all-packages` at the top of every execution, stripping dev
   dependencies from the contributor's `.venv`. Running this under pytest
   would sabotage the very environment pytest runs in.

The third point is *why* the first point's guard exists: this script is
designed to run only inside the Breeze container, where wrecking the venv is
a non-issue. Testing it on the host conflicts with that design premise.

How to apply: when changing this script's check logic, don't plan a pytest
unit test — it's a dead end. Verify behaviorally instead: deliberately break
a target field in some `provider.yaml` → run `cd providers && prek run
check-provider-yaml-valid --files <p>/provider.yaml` and confirm non-zero
exit with the broken value named in the error → `git checkout --
providers/<p>/provider.yaml` to restore → confirm `git status --short` is
clean. This matches the file's existing state — all 20+ `@run_check`
functions in it have no unit tests; the prek hook itself is the verification
mechanism. If a reviewer asks for tests anyway, the correct response is "that
needs `AIRFLOW_ROOT_PATH` to become injectable and
`sync_dependencies_without_dev` to become skippable first — suggest a
separate PR," not simply asserting tests aren't needed.

### A provider optional dependency without a matching `dev` group entry silently skips its own test file

Adding a dependency to `[project.optional-dependencies]` alone does **not**
make it available to the unit-test environment. Every optional dependency in
`providers/common/ai` that has unit tests appears in *both* places —
`[project.optional-dependencies]` and `[dependency-groups] dev`. Combined
with the usual `pytest.importorskip("<pkg>")` at the top of the test file,
listing it in only the extras means the entire test file is skipped — **and
CI still reports green**, because skips are not failures. "There are tests"
and "the tests run" are different claims; a green CI badge is only evidence
of the first.

How to apply: when a PR adds an optional dependency plus tests that
`importorskip` it, check the `dev` group in the same diff. To verify rather
than infer:

```bash
uv sync --project providers/<name>
python -c "import importlib.util as u; print(u.find_spec('<pkg>'))"  # None = can't run
```

Also pull a provider CI job log
(`gh api repos/apache/airflow/actions/jobs/<id>/logs
--allow-escape-sequences`) and grep for both the test file name and an
install line for the package — absence of both is strong evidence the tests
never ran; say "please confirm the tests execute" rather than asserting they
never do unless every job was checked. Found via PR #71725 (a sandbox
backend's optional dependency added only to extras, guarding 353 lines of
tests over a path that ships user commands/file contents to a third-party
service).

## 3. Local-machine false reds

These are environment states that make real, unmodified code look broken.
The tell across all of them: an isolated/scoped rerun is green while the
broader run is red, or the failure set changes between otherwise-identical
runs.

### Node 26's experimental global `localStorage` breaks the UI vitest suite

Running the UI test suite (`airflow-core/src/airflow/ui`, vitest +
happy-dom) under Node v26 fails spuriously: Node's experimental global
`localStorage` shadows happy-dom's `window.localStorage` when
`--localstorage-file` isn't provided, so `localStorage.clear()` in test
hooks throws, and dependent tests time out with misleading
`ECONNREFUSED localhost:3000` symptoms that look like a broken mock server.
Fix (environment, not code):

```bash
NODE_OPTIONS="--localstorage-file=<path>" pnpm exec vitest run <files>
```

This only fixes *whether a store exists* — it does not fix *one store
shared across all workers*. A full-suite run still cross-pollutes tests
that write to localStorage, and **the losing set of files rotates between
runs**. Tell a real regression apart from this pollution by running the
suspect file alone with its own fresh store file: pollution passes in
isolation, a real regression still fails.

### A fresh worktree has no UI `node_modules`, and naive install can destroy an existing one

A freshly `git worktree add`-ed checkout has no
`airflow-core/src/airflow/ui/node_modules` — UI tooling fails with exit 127
until deps are installed. Plain `pnpm install` aborts non-interactively
(`ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`); `CI=true pnpm install
--frozen-lockfile` bypasses that. **But `CI=true` alone is not enough when
the host's `pnpm` is newer than the repo's pin** — it converts the abort
into destruction: a newer pnpm no longer reads the deprecated `pnpm` field
in `package.json`, treats the lockfile's `overrides` as unset, deletes the
existing working `node_modules`, and then fails on a lockfile-config
mismatch, leaving nothing installed. Always drive UI tooling through the
pinned version instead of the host's:

```bash
CI=true npx -y pnpm@<pinned-version> install --frozen-lockfile
CI=true NODE_OPTIONS="--localstorage-file=<path>" \
  npx -y pnpm@<pinned-version> exec vitest run <test file>
```

Re-derive the pin from `airflow-core/.pre-commit-config.yaml` (the UI hooks'
`additional_dependencies`) rather than hardcoding a version — it moves. The
`ts-compile-lint-ui` prek hook is unaffected by any of this since it uses
prek's own pinned node toolchain.

### A fresh worktree's first commit/prek run can hang for 10+ minutes — that's env setup, not a hang bug

The first `git commit` (or a full `prek run --files ...`) in a brand-new
worktree can take more than 10 minutes, well past a typical tool timeout —
not because prek is broken, but because a heavy hook (commonly a mypy hook)
is building its per-worktree environment for the first time (e.g. a venv
under `.build/mypy-venvs/`, which is not shared across worktrees). Confirm
this rather than assuming: a light hook (`prek run trailing-whitespace
--files <one file>`) should still return in well under a second, proving
prek itself and its shared cache are fine. Once confirmed as "slow, not
broken": unblock with `git commit --no-verify`, then run the full `prek run
--files <changed>` in the background and report its exit code once done.
Don't retry the full hook set in the foreground repeatedly — each attempt
just gets cut off by the timeout and restarts the same slow build from
scratch.

### A stale local `airflow.db` schema breaks a whole provider test suite

Running an entire provider's test directory (as opposed to a single file)
can fail with `no such table: ...` / `UNIQUE constraint failed`, then abort
mid-run with `Unable clear test DB, try to run with flag --with-db-init`.
That abort truncates collection, so the outer symptom looks like: collected
count differs between runs, exit code 2 instead of 1 (automation can't parse
a failure name out of it), and failures cluster in `db_test`-marked tests
while a single file run in isolation is green. **Judge**: whole-directory red
+ single-file green + unstable collected count → suspect the local metadata
DB before calling it a regression. `--with-db-init` is not the fix on an
already-broken DB — it can fail its own re-init and turn "some tables
missing" into "no tables at all," erroring every test at setup. The actual
fix is deleting the DB file (back it up first — it's the user's local dev
DB, shared by every worktree, so ask before deleting) and letting the next
run recreate it automatically.

**A second, unrelated root cause produces a similar-looking but distinct
symptom** — the same test file flickering red/green/red across consecutive
runs while it is always green when run alone. That's concurrent worktrees
sharing the same `~/airflow/airflow.db` (confirm via `ListAgents` showing
multiple sessions active). Deleting the DB does **not** fix this — a
rebuilt DB gets hit by the next concurrent run just the same. Distinguish
by recurrence pattern: **stable, same failures every run → stale schema**
(delete + rebuild); **flickering across runs, single-file always green →
concurrency** (no fix beyond not writing it to a known-failures list, since
that would silence a real future regression too). This is exactly what the
isolated `AIRFLOW_HOME` recipe below (§ "Every worktree shares one sqlite
test DB") prevents — apply it proactively rather than diagnosing after the
fact.

### `providers/common/ai`'s sandbox tests fail on macOS, unrelated to branch content

Running `uv run --project providers/common/ai pytest
providers/common/ai/tests` on macOS locally gets a stable **12 failed / 1380
passed**, all in
`.../tests/unit/common/ai/sandbox/test_base.py::TestDefaultFileOperations`
(round-trip, binary content, hostile filenames, `list_directory`, oversized
file). Every failure raises the same shape of `SandboxError` claiming a
temp-directory file "does not exist in the sandbox, or is not readable" —
e.g.:

```
SandboxError: '/private/var/folders/.../pytest-of-<user>/pytest-NNN/<tmpdir>/a.txt'
  does not exist in the sandbox, or is not readable.
```

This is not a regression: confirmed by diffing the branch against `main` —
`sandbox/`'s src and tests were byte-identical, yet the same 12 failed. The
suspected (unconfirmed) root cause is a macOS `/tmp` → `/private/var`
realpath mismatch defeating the sandbox's path allowlist check — that's a
guess, not something read through the comparison logic yet.

The count is not fixed. A later run (2026-10-07, whole
`providers/common/ai/tests/unit`) saw **38 failed / 3096 passed**, all
still under `sandbox/` (`test_base.py` 34, `test_sbx.py` 4), with a second
failure shape: `find: -printf: unknown primary or operator` — BSD `find` on
macOS has no `-printf` — plus a few regex mismatches. That branch did not
touch `sandbox/`, but this run was not compared against a HEAD checkout, so
treat "pre-existing" as an inference. Judge by location and failure shape,
not by matching a remembered number.

How to apply: when verifying a `providers/common/ai` hook change in this
repo, scope both `.claude/test-command` and manual verification to
`providers/common/ai/tests/unit/common/ai/hooks` (fast — under 5s) rather
than running the whole `tests/` directory, unless the change actually
touches `sandbox/`. If `sandbox/` itself needs fixing later, treat the root
cause as unconfirmed and read `base.py`'s path-comparison logic before
proposing a fix.

### `Run black on docs` reformats long Python inside RST code blocks, failing the first commit

The `Run black on docs` prek hook rewrites Python code embedded in RST
`code-block` directives when a line runs too long (confirmed: a long call in
`quickstart.rst` got wrapped). Like any hook that modifies files, it fails
the **first** `git commit` with `files were modified by this hook` — that's
not a real problem, just the hook's own rewrite landing on disk between the
first and second attempt. `git add` the reformatted file and commit again;
the second attempt is green because there is nothing left to rewrap. Keep
doc-example lines short to begin with to avoid the extra round trip.

### `ANSWER=no` skips breeze's interactive rebuild prompt (background for several entries below)

When a tracked file breeze cares about (e.g. `Dockerfile.ci`) has changed,
`breeze run …` stops on an interactive "Likely CI image needs rebuild …
Press y/N/q" prompt that hangs a non-interactive shell. Prefix any breeze
invocation with `ANSWER=no` to decline the rebuild and reuse the existing
image: `ANSWER=no breeze run pytest <tests> -xvs`. The env var answers all
of breeze's yes/no prompts globally — several of the entries below assume
it's already in place.

### A brand-new worktree's first `breeze run` builds a CI image — that can outrun a harness timeout, and looks like a test failure

In a git worktree (or image cache) that has never run breeze before, the
first `breeze run pytest ...` call builds the CI image first — a
multi-layer Docker build that can take 30–90+ seconds, counted as part of
that call's runtime. maigo's own Stop-hook verification
(`verify_completion.py`) has a fixed timeout (observed ≈90s); if the first
call lands inside the image build, the hook reports a timeout that reads
exactly like a test failure, even though pytest never started. Confirm
before concluding the tests are broken: manually rerun the same command
with a much longer timeout (e.g. 10 minutes) — once the image is built,
Docker's layer cache makes later calls in the same worktree finish in
seconds. Don't assume broken test logic, or narrow the test scope, on a
first-call timeout alone.

### A high-concurrency test hitting `QueuePool limit` in breeze is usually an environment limit, not a code defect

A high-concurrency (many-thread/many-connection) airflow-core test failing
with `sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10
reached, connection timed out` under breeze is usually breeze's own test
connection pool being too small for that concurrency level, not a defect in
the code under test. Case: PR #62501's
`test_create_dag_runs_when_concurrent_asset_events_created` (30 threads,
needs postgres/mysql) hit the same `QueuePool` timeout across two
independent review rounds; three separate mutations (removing the
`created_at` ordering, the `NOT EXISTS` reverse-check, the delete guard)
all left the timeout unchanged. **Judgment**: a mutation test not clearing
the timeout does **not** license concluding "so it's a code bug" — that
result is equally consistent with "the pool was never going to be enough
regardless." To actually distinguish the two, inspect breeze's DB pool
configuration or the code path's session lifecycle directly — don't infer
it from a mutation canary that can't discriminate between the two
explanations. Treat this the same as the image-build timeout above: don't
upgrade a verdict on the strength of local reproduction alone.

### `breeze ci-image build` doesn't produce a real image on this arm64 machine

`breeze ci-image build --python 3.10` on this machine does not give an
image reflecting a `uv.lock` change (observed 2026-08-24, trying to get a
real `breeze run mypy` result after a provider's `pydantic-ai-slim` floor
bump):

| Invocation | Outcome |
|---|---|
| default registry cache | exit 0, but a **false green** — image `Created` timestamp unchanged, container still on the old package version |
| `--docker-cache disabled` | fails in ~3s: `ibm-db==3.3.0` native build → `NameError: name 'arch_' is not defined` |
| `--docker-cache local` | same `ibm-db` failure |

`ibm-db` (pulled in via `apache-airflow-providers-ibm-db2`) has no arm64
wheel and its `setup.py` breaks on this platform — nothing about the
provider actually being worked on is involved. **Consequence**: a stale
image reports type errors that don't exist (e.g. mypy complaining an
attribute is missing from a third-party class, because the image holds an
older version of that library than `uv.lock` pins); `prek run --stage
manual`'s `mypy-providers` hook surfaces the same false failure.

**How to apply**:

1. Before believing a `breeze run mypy` failure naming a third-party
   attribute, compare versions: `ANSWER=no breeze run "pip show <package>"`
   against `uv.lock`. A gap means the image is stale, not that the code is
   wrong.
2. `breeze ci-image build` exiting 0 is **not** evidence the image
   changed — check the image `Created` timestamp, or rerun the `pip show`
   check above; the default cache path can no-op silently.
3. Run providers' mypy on the host instead:
   `uv run --project providers/<provider> mypy providers/<provider>/src/...`
   — but first confirm the host venv actually matches the lock
   (`./.venv/bin/python -c "import importlib.metadata as m;
   print(m.version('<pkg>'))"`), or the fallback just becomes a second
   environment with a different stale version.
4. Two failures with this exact shape in a row is the stop signal — don't
   try a third `--docker-cache` permutation; switch to the host fallback
   and report the image problem separately. This is distinct from the mypy
   coverage gap noted in §2 above (that one is "the hook set never runs
   against `providers/`"; this one is "the image it *would* run against, if
   invoked directly, is stale").
5. Worth filing upstream as a local-environment defect, but it never blocks
   a PR whose own mypy is clean on the host.

### `check-provider-yaml-valid` failing with an `ibm-db` `arch_` `NameError` is a stale CI image, not your `provider.yaml`

The hook runs *inside* the Breeze CI image. When `Dockerfile.ci` changed and
the image wasn't rebuilt, it fails for reasons unrelated to `provider.yaml`
content: it prints "important files are modified … since last time image was
built" / "Likely CI image needs rebuild", the rebuild prompt is declined by the
forced `no` answer, the in-container `uv sync --no-dev` then fails building
`ibm-db` with `NameError: name 'arch_' is not defined` and ends in `Error 1
returned`. The output contains **no** provider.yaml validation message; the
`Run mypy for providers (manual)` hook fails from the same root cause. On this
arm64 hosts the image can't be rebuilt (previous entry), so the hook yields no
real result locally — record it as an environment limit.

Attribute it instead of reading the 600-line output: run the same hook on a
file you did **not** change
(`prek run check-provider-yaml-valid --files providers/amazon/provider.yaml`);
failing on the same line proves it's unrelated to your diff. Don't filter the
output with grep to decide. To land the commit: `git commit --no-verify`, and
separately run the commit-msg hook that `--no-verify` also skips
(`check-no-conventional-commit-message`, via `--hook-stage commit-msg
--commit-msg-filename <file>`). A *real* provider.yaml error (unregistered
module, wrong key set) looks different — see
[`registry-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/registry-conventions.md)
(new hooks module registration).

## 4. Attribution — don't accept a red's cause without proving it

### Airflow `test-command` prefixes — the command runs as argv, not through a shell

How a harness-invoked test script (`.claude/test-command`) is executed — `shlex.split` +
`subprocess.run`, no shell, so no `ENV=val` prefix, `&&`, `$(...)` or `~` — and how to verify
it, is in
[`harness-discipline`'s `shell-and-tool-gotchas.md`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/shell-and-tool-gotchas.md).
Only the Airflow-specific prefixes are listed here.

Prefixes a provider/breeze `test-command` usually needs, each written with
the absolute `/usr/bin/env` so no shell is involved (the full command shape:
`/usr/bin/env AIRFLOW_HOME=<scratchpad>/airflow-home uv run --frozen --project
providers/<p> python -m pytest <files> -q`; `mkdir -p` the home first):

- **`AIRFLOW_HOME=<empty dir>`** — without it, a sqlite DB already sitting under the
  default home makes the whole batch **ERROR at setup** rather than fail
  (`table callback_request already exists`, `index idx_xcom_key already exists`;
  e.g. 205 errors, 0 tests run), which the Stop hook reads as "suite never ran".
  The residue/corruption rules and the per-agent-home recipe are in the next
  sections ("Every worktree shares one sqlite test DB", "A new worktree needs a
  scoped test command") — don't restate them here.
- **`COLUMNS=200`** — the hook's environment has `COLUMNS=0`, so rich falls back to
  80 columns and wraps long lines. A test asserting a contiguous string that
  contains a long `tmp_path` then fails only under the hook (breeze's
  `test_shim_version_check.py::test_warn_if_shim_outdated_older_installed`
  wraps `needs to` / `be upgraded`) while every manual run is green. Put
  `/usr/bin/env COLUMNS=200 uv run pytest -x` in the untracked
  `dev/breeze/.claude/test-command`; don't edit the test (backport branches
  shouldn't carry it) and don't add it to `.claude/known-test-failures`. When
  "hook red, manual green", add `--junitxml=<scratchpad>/hook-junit.xml` to the
  command to capture the real failure message before concluding anything.
- **`python -m pytest`, not `pytest`** — in `providers/common/ai`,
  `uv run --project providers/common/ai pytest <path>` can fail with
  ``Failed to spawn: `pytest` `` (os error 2) while `python -m pytest` works
  (it doesn't depend on a console-script entry point). Observed only in
  common.ai; recheck before generalizing to another provider.

### Code that branches on a 3.3-only SDK symbol: simulate the old SDK before calling it done, and keep 3.3-only imports out of test-module top level

Compat jobs run the provider against Airflow 2.11 / 3.0 / 3.1 / 3.2, where
3.3-only symbols (`iter_pydantic_models`,
`SUPPORTS_OPERATOR_DESERIALIZATION_WALKER`, `NEVER_EXPIRE`,
`airflow.sdk.serde` helpers, …) don't exist. A dev environment that has them
verifies none of that. Three rules, each from a case where a maintainer's
"please handle <3.3 compatibility" came back more than once (#74396, #74695):

1. **Before declaring done on code that branches on whether such a symbol
   exists, rerun under a simulated old SDK.** Write a pytest `-p` plugin
   (scratchpad) that, in `pytest_configure`, deletes **every** symbol the
   target version lacks — the flag *and* the function together. Deleting only
   one produces a self-contradictory environment and a false failure. Confirm
   against the real old source (`git show task-sdk/<version>:<path>`) that the
   deleted symbols truly don't exist there. It is a simulation: the pushed
   Compat job stays the final verdict. Case: in #74695 a helper returned `True`
   when `iter_pydantic_models` was missing; the 2.11.1 / 3.0.6 / 3.1.8 / 3.2.2
   Compat jobs went red on 11 tests at once, because all three roles had only
   run where the symbol exists.
2. **A test that really exercises 3.3-only behavior needs
   `@pytest.mark.skipif(not AIRFLOW_V_3_3_PLUS, reason=...)`** (flag from
   `tests_common.test_utils.version_compat`; same shape as
   `operators/test_llm.py`'s `requires_typed_xcom`). Patching the module's own
   `AIRFLOW_V_3_3_PLUS` to `True` only fools the module's gate: if the code
   then lazily imports a 3.3 symbol (e.g. `TaskStateStoreUsageBudget.save()`
   importing `NEVER_EXPIRE`) inside a `try/except` in `src`, the `ImportError`
   is swallowed and the test fails quietly (`assert_called_once` sees 0
   calls) instead of erroring. Tests that only hit mocks are fine. Don't make
   the helper return a special value on old versions to get a test green.
3. **Don't import a 3.3-only module at test-file top level.** A top-level
   `from airflow.sdk.serde import deserialize, serialize` fails collection on
   the older versions, and pytest stops with `Interrupted: N errors during
   collection` — the *whole provider's* tests don't run, including unrelated
   ones. Put the import in the file's existing
   `try: from airflow.sdk.serde import SUPPORTS_OPERATOR_DESERIALIZATION_WALKER as _CORE_WALKER`
   / `except ImportError: _CORE_WALKER = False` block (ruff isort merges it
   into a parenthesized import); grep every use of the names first and confirm
   each user test is gated by a skipif. Verify with a plugin that sets
   `sys.modules["airflow.sdk.serde"] = None` in `pytest_collectstart` and run
   `--collect-only -q` on the file: the old shape must ERROR, the fixed shape
   exit 0.

How this fits the "check the floor, not just the ceiling" paragraph below
(which says *not* a bare `try`/`except`): the `try`/`except ImportError` here
only supplies the flag/symbols so the module imports at all; **the gate is the
skipif** on each test that depends on them. A `try`/`except` that is the only
thing standing between an old version and a silently-passing or silently-wrong
test is the shape that paragraph rules out. The `AIRFLOW_V_3_3_PLUS` convention
itself is in
[`code-style.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/code-style.md).

### A rebase that bumps `uv.lock` makes an installed-package comparison test red — and that's the PR's responsibility, not a false red

When a PR carries a test that compares against an **installed** third-party
package's actual surface (e.g. `TestPydanticAIExternalServicesDrift` in
`providers/common/ai`), rebasing onto a `main` that bumped `uv.lock` for that
package makes the comparison test red. Unlike the false-red shapes above,
**this is a real signal the PR is responsible for**, not environment noise —
the installed package genuinely changed, and the comparison test is doing its
job.

Before attributing, compare the two lockfiles directly rather than assuming:

```bash
git show <base>:uv.lock | grep "<package-name>"
git show HEAD:uv.lock | grep "<package-name>"
```

Once confirmed, classify every newly-appeared upstream item honestly (new
vendor, newly-reachable module, newly-deprecated one — see
[`references/review-checks.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/review-checks.md)
§10.26 for the classification rules), and give **every** new exclusion-list
entry its own guard test — don't just widen an existing assertion to swallow
the new item.

**Then check the floor, not just the ceiling**: after reclassifying, confirm
CI's "Low dep tests" job would still pass — it installs the version floor
declared in `pyproject.toml`, and a newly-declared vendor (or a module a new
guard test imports) may not exist at that floor. The local `.venv` has the
newer version installed, so this gap is invisible locally. Follow the
existing shape rather than inventing one: a version constant plus
`pytest.mark.skipif` (e.g. `ALL_DECLARED_VENDORS_AVAILABLE_FROM` in
`providers/common/ai/tests/unit/common/ai/test_provider_metadata.py`) — not a
bare `try`/`except` that silently swallows the gap. (A `try`/`except
ImportError` that only sets a flag so a test module still imports is not that
shape, as long as a skipif gates the tests — see the 3.3-only SDK symbol
section above.)

**Don't stop at making the assertion pass.** Widening it in only one
direction (e.g. dropping a strict two-way equality to a one-way subset check)
just to get past the immediate red reopens the exact defect a two-directional
check exists to catch (§10.26 again). Gate the loosened direction behind its
own version constant, and prove the tripwire still fires with a mutation
canary (§5 below, and `evidence-discipline.md` §24) before considering the fix done.

### `uv.lock` during a rebase, and when `prek` commit blames it on the RST license hook

**Rebase.** On an apache/airflow branch, a conflicted `uv.lock` can show up
staged as *deleted* (AGENTS.md says to delete and regenerate on conflict).
`git rebase --continue` would then commit that deletion into history. Restore
the base version mid-rebase with `git checkout HEAD -- uv.lock`, resolve the
other conflicts, continue, and only after the rebase re-lock **minimally** in a
**separate commit**: restore the target branch's (`main`'s) `uv.lock`, then run
plain `uv lock` with the repo-pinned uv (`uvx uv@<pin> lock`) — no `rm`, no
`--upgrade`. Between the rebase finishing and the re-lock, `uv lock --check`
fails because the new dependencies aren't in the lock yet — that is the
expected state.

**Don't follow the `rm uv.lock && uv lock` wording** that the repo's AGENTS.md
and the uv-lock-rebase-notice bot suggest for a conflicted lock: it re-resolves
the whole file and drags unrelated upgrades into the PR (#74026 round 4: 52
unrelated packages, e.g. `pydantic-ai-slim` 2.56→2.57, `pyexasol` 2→3, which in
turn forced a vendor-declaration and gate change), and the reviewer rejected it.
`rm` is only the fallback for when plain `uv lock` on top of the restored base
lock cannot resolve.

**`prek` commit blocked by "Add license for all RST files".** In commit mode,
`prek` can report that hook as failed ("files were modified by this hook")
when the real cause is something silently rewriting `uv.lock` during the run.
The `uv.lock` change is unrelated to your commit: a standalone full `prek`
run exits 0 while still rewriting `uv.lock`, and `UV_FROZEN=1` doesn't stop
it. Workaround: `git update-index --assume-unchanged uv.lock` for the
duration of the commit, then immediately `git update-index
--no-assume-unchanged uv.lock` and `git checkout -- uv.lock`. Unknown (not
investigated): which hook does the rewrite, and whether a clean `main`
behaves the same.

### Minimal re-lock: how to verify it, and keeping the venv, the base diff and nested `uv` in line with the lock

The pinned-`uv` rules (marker churn, `uvx uv@<pin>`, the decisive base-lock
test) are in
[`review-checks.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/review-checks.md)
("`uv` version must match the repo pin …") — this section only adds what
the rebase paragraph above needs.

- **Verify a minimal re-lock per package, not by eyeballing.** After
  restoring `main`'s lock and running plain `uv lock`, compare the two locks with
  `python3 -I` + `tomllib`, package by package (name + version + marker
  entries). The only allowed differences are the new packages and the new
  extra/specifier entries of your own change. Run the comparison once on a
  known-wrong lock first (positive control): it must catch a version bump and a
  missing second `pyvespa` entry. Two `pyvespa` entries (e.g. `<3.14` and
  `>=3.14`) are a Python-version split, not duplicates — don't delete one. The
  authoritative signal is `uv lock --check` exit 0. If the lock goes back to
  `main`'s `pydantic-ai-slim` version, revert the vendor declarations and the
  `ALL_DECLARED_VENDORS_AVAILABLE_FROM`-style gate to `main`'s too
  (`provider.yaml`, `get_provider_info.py`, `test_provider_metadata.py`), and
  write "tested version" claims in docs from the lock's actual value.
- **After restoring/downgrading the lock, align the `.venv` before any test
  that reads installed versions.** The `.venv` doesn't follow the lock; a drift
  test such as `test_provider_metadata.py` (reads the installed
  `pydantic-ai-slim`) then runs against the old environment and gives a false
  red or green, and the Stop hook eats the same false red. List mismatches with
  `python3 -I` + `tomllib` (lock) vs `importlib.metadata` (`.venv`), then
  `uv pip install --python <worktree>/.venv/bin/python --no-deps <pkg>==<lock
  version>` for just those packages (this touches only the ignored `.venv`,
  never `uv.lock`), and re-read `importlib.metadata` to prove they now match.
  Check `shasum uv.lock` is unchanged and `uv lock --check` exits 0 afterwards;
  treat hook reds during the gap as noise (don't write them into
  `.claude/known-test-failures`).
- **Judge "what did this PR change in `uv.lock`" against the PR's own parent,
  not `git merge-base HEAD origin/main`.** A local `origin/main` that is stale
  while the branch sits on newer upstream puts the merge-base on an old commit
  and the diff fills with thousands of lines of upstream bumps (~7,600 lines
  seen where the PR was +27/−49). Count the PR's commits
  (`git log --oneline`), then `git diff HEAD~N -- uv.lock` and compare
  name + version per package.
- **A broken base lock isn't your branch's fault.** If `uv run`/`uv sync`
  report `Failed to parse uv.lock` or `Found duplicate package <pkg>`, check
  `git diff <base> HEAD -- uv.lock` (empty ⇒ not yours) and
  `git show <base>:uv.lock | grep -c '^name = "<pkg>"'` against
  `origin/main`'s. If `origin/main` already fixed it, rebase. Otherwise,
  re-lock with the repo-pinned uv in its own commit and prove it with
  `uvx uv@<pin> lock --check` plus `uv sync --frozen --project <p> --dry-run`.
  To keep verifying meanwhile, point `.claude/test-command` at
  `<worktree>/.venv/bin/python -m pytest` (still behind `/usr/bin/env
  AIRFLOW_HOME=<empty dir>`, since the hook has no shell), use `uvx ruff` for
  lint, and if the mypy hook blocks the commit because its `uv sync --frozen`
  fails, `--no-verify` under the existing per-commit authorization rule below,
  stating it in the report. Don't edit `uv.lock` to make it parse.
- **Nested `uv run` inside pytest can pick a too-old `.venv/bin/uv`.**
  `devel-common`'s `pytest_plugin.py` runs
  `uv run update_providers_dependencies.py` at import; the inner `uv`
  resolves to `.venv/bin/uv`, and if that is below the repo's required version
  (log line 1: `Required uv version … does not match the running version`) the
  inner call exits 2 and the whole run dies before collection. The
  trailing `CalledProcessError` is only the consequence, and running that script
  alone uses the system `uv` and succeeds, so it looks transient. Fix:
  `uv sync --frozen --project providers/<p>` (touches only the ignored `.venv`,
  but removes other providers' packages — re-sync to test another provider).
  Editing `PATH` instead is an untested inference.
- **Bumping the repo's `uv` version: `dev/breeze/uv.lock` is a separate
  lock** (`uv` is a transitive dependency of `hatch` there, not listed in its
  `pyproject.toml`), easy to miss after the root files are updated. From
  `dev/breeze`: `uvx uv@<version> lock --upgrade-package 'uv==<version>'` (a
  bare `--upgrade-package uv` jumps to the latest, not the pin), then
  `uvx uv@<version> lock --check` (exit 0). Expect the diff to be only `uv`'s
  version/URL/hashes plus `revision` if the new `uv` bumps the format. Close
  out with `git grep -n -F '<old version>' -- . ':!*uv.lock'` and a
  `grep -c` on both locks (remaining lock hits may be a hash coincidence — read
  the line). Don't `grep -r` the whole monorepo.

### Every worktree shares one sqlite test DB — a `db_test` result can be someone else's noise

`AIRFLOW_HOME` defaults to `~/airflow` for every worktree, so
`sql_alchemy_conn` (and therefore the physical DB file) is shared across all
of them — a pytest run in a completely different worktree/session writes the
same file. Symptoms of this (all bogus, none a branch bug): `no such table`
errors from a DB that was never initialized in this worktree; `table ...
already exists` from two processes mid-reset at once; row-count/id-list
mismatches from another session's rows leaking in; FK constraint failures
from stale accumulated rows. The tell is a **changing failure set between
otherwise-identical runs** on your own code. Fix: give the worktree its own
private `AIRFLOW_HOME` (outside the repo, so it doesn't dirty `git status`),
and delete-and-recreate that DB before each run rather than relying on an
in-place reset flag, which can itself fail on a half-broken schema.

Concrete recipe: point `AIRFLOW_HOME` at a fresh directory (e.g. under the
scratchpad) before running, and confirm `ls $AIRFLOW_HOME` shows a
newly-created `airflow.db`. **Every concurrently-running agent needs its own**
`AIRFLOW_HOME`, not just every worktree — sharing one between parallel agents
reproduces the exact same clash. Never delete the user's `~/airflow/airflow.db`
without asking — it's their shared local dev DB, not a disposable artifact of
this worktree.

If this is wired into `.claude/test-command`, remember the "Airflow `test-command`
prefixes — the command runs as argv, not through a shell" entry above: write it as `env AIRFLOW_HOME=<dir>
uv run ...` (a single command, with `env` doing the prefixing) —
`AIRFLOW_HOME=<dir> uv run ...` without `env` fails with `command not found`
under `shlex.split` + `subprocess.run`, the same mechanism as that rule's
`ENV=val cmd` example; it only works under an actual shell.

Two further shapes of the same clash (the Stop hook counts as one more concurrent runner):

- **Parallel agents plus the Stop hook can corrupt the shared DB at init.** Beyond the symptoms
  above: a DB left half-initialised makes *every* later run fail at collection
  (`table callback_request already exists` / `Unable to re-initialize the SQLite test DB`, N
  errors, 0 tests run), it does not self-heal, and it is unrelated to the diff. Treat the hook's
  red from this as environment noise and don't edit `.claude/test-command` because of it; the
  fix is the per-agent private `AIRFLOW_HOME` above (e.g. `<scratchpad>/airflow_home_<agent>`).
- **A verifier and the Stop hook running the same batch against the same `AIRFLOW_HOME` can give
  false reds** (a failure set that differs run to run). Have the verifier copy that home
  (`/bin/cp -R <that AIRFLOW_HOME> <scratchpad>/af-home-<name>`) and use the copy; the point is
  that the verifier's home is its own, wherever the original lives. While a verifier is
  `running` (confirm with `ListAgents`), hook reds are noise: don't write them into
  `.claude/known-test-failures`. Root cause unproven — repeated greens on the isolated DB only
  support the interference explanation.

### A new worktree needs a scoped test command, a fresh `AIRFLOW_HOME` per verifier run, and a few env fix-ups

Differences from the entries above that bite on every new worktree (state them in the
delegation prompt, not just in your own head):

- **Write a scoped `.claude/test-command` at the start, and run it once.** The repo root has no
  runnable pytest entry point, so the Stop hook's default `uv run pytest -x` dies with
  `ERROR collecting` — a collection error, not a test failure, with no suite run at all. Narrow it
  to the package and directories this change touches (`uv run --project <pkg> pytest <dirs>`) and
  confirm it exits 0 rather than swapping one false signal for another. Prefer this to
  `.claude/skip-test-verification`, which turns verification off entirely. When a test is renamed,
  grep the command for the old id (`ERROR: not found:` means the suite never ran), and list only
  files this change touched so an old task's leftover paths don't bring unrelated reds in.
- **Reusing one on-disk `AIRFLOW_HOME` accumulates residue.**
  One fixed directory reused by the Stop hook, subagents and manual reruns accumulates
  state: the same suite was observed going green twice on a fresh dir yet red intermittently
  (`FOREIGN KEY constraint failed`, a different test each time) on the reused one. So have each
  verifier run use a new empty `AIRFLOW_HOME`, sequentially rather than in parallel, and before
  treating a red as evidence, rerun once against a fresh dir.
  Separately, a private home's DB can also be corrupted outright, e.g. by an aborted pytest
  (every test errors at table creation with `table X already exists`, a different table each
  time; `--with-db-init` doesn't help): delete its `airflow.db` and the `.airflow_db_initialised`
  marker (git-ignored; `/bin/rm -f`) and rerun. Never touch the shared default-home DB.
- **`ModuleNotFoundError: No module named 'airflow_shared'` at fixture setup** (structlog
  `caplog` / `cap_structlog`): a fresh worktree's `.venv` lacks the editable `.pth` for
  `shared/*/src`, so the whole batch errors rather than fails. Add those `src` directories to
  `PYTHONPATH` in the same shell call. It doesn't hit every package, so report the original
  result and the patched-env result separately.
- **Don't borrow another checkout's `node_modules` by symlink.** A mismatched dependency
  version there made dozens of UI test files fail to load (`tableFeatures is not a function`);
  that run is void. Install inside the worktree (see the pnpm entry above).
- **When `breeze run pytest` is stuck rebuilding the CI image** (over an hour from source), stop
  rather than retry the same command. A fallback is mounting the worktree into the prebuilt CI
  image from the registry and running `uv run --project <pkg> pytest` inside it. It is not
  breeze and not the CI environment, so say so in the report; and tests that need Linux skip
  wholesale on macOS, so a macOS green doesn't verify them.

## 5. Generated files: mutation canary and breeze-generated artifacts

Re-running a generator and diffing the resulting shasum only shows "the file didn't change" — that
is indistinguishable from "the generator never touched this file". The general procedure (back up,
corrupt, confirm the shasum changed, re-run, require both a generator failure and a restored
shasum) is in
[`harness-discipline`'s `evidence-discipline.md`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/evidence-discipline.md)
§24, "驗證『產生檔』的冪等性". In this repo it applies to the committed-but-generated artifacts:
provider registry modules like `get_provider_info.py`, OpenAPI specs, Task SDK/ctl datamodels,
metrics registries, supervisor schema snapshots — anywhere a "the generator produced this,
don't hand-edit it" claim needs to be verified rather than assumed.

### Backport conflicts on breeze-generated hash files: take incoming + verify with a scoped regenerate, not a global `--check-only`

A cherry-pick/backport that conflicts on breeze-generated hash files
(`dev/breeze/doc/images/output_*.txt`) shouldn't be resolved by guessing
which side is right. Take the incoming commit's value, then run `breeze
setup regenerate-command-images --command <group:command>` scoped to just
the conflicted command(s) to verify the regenerated hash matches exactly. A
global `--check-only` run will likely surface many unrelated pre-existing
hash mismatches (environment/breeze-shim-version drift) — that's noise, not
something to fix as part of resolving this conflict.

### The breeze shim's `uvx` environment cache goes stale when only `dev/breeze/src/` changes

The `breeze` shim (`uvx --from dev/breeze`) caches its ephemeral environment
in `~/.cache/uv/environments-v2/`, keyed by resolution hash. Breeze's own
version stays `0.0.1` and its `pyproject.toml` rarely changes, so an edit
under `dev/breeze/src/` never invalidates the cache — a prek hook that
shells out to breeze (e.g. `update-providers-build-files`) then silently
runs the **old** generator code, dirtying generated files (e.g. re-adding a
section a newer template commit removed). Symptom: a hook regenerates 100+
provider files with changes that contradict a recently merged generator
commit. `uv cache clean apache-airflow-breeze`, `uvx --reinstall`, and
`uvx --refresh` do **not** fix it. Fix — remove the cached env symlinks
whose archive contains `airflow_breeze`:

```bash
for link in ~/.cache/uv/environments-v2/*/*; do
  t=$(readlink "$link") || continue
  ls "$t"/lib/python*/site-packages/airflow_breeze >/dev/null 2>&1 && { command rm -f "$link"; command rm -rf "$t"; }
done
```

Verify freshness by importing a recently-added symbol via `uvx --from
./dev/breeze python -c ...` (needs `SKIP_BREEZE_SELF_UPGRADE_CHECK=1`). A
durable upstream fix would add `cache-keys = [{ file = "pyproject.toml" },
{ file = "src/**/*.py" }]` to `[tool.uv]` in `dev/breeze/pyproject.toml`.

## 6. Docs page screenshot procedure

When a PR adds or changes a docs page, attach a screenshot at PR-open time —
see `airflow-aware/SKILL.md` §8. This section is the how-to.

1. Build only the affected distribution, not the whole docs site:

   ```bash
   ANSWER=no breeze build-docs --package-filter apache-airflow-providers-<x> --one-pass-only --clean-build
   ```

   `--package-filter` takes the full distribution name (a glob is allowed);
   the positional form takes the short name (e.g. `common.ai`) — passing the
   full name positionally exits 2. The default scope already builds the Python
   docs **and** spell-checks them, so there is no separate spelling flag: to
   reproduce a CI docs-spelling failure (`Incorrect Spelling: '<word>'`) rerun
   this same command, and treat its exit code as the authoritative verdict —
   a grep for the flagged word only locates it, it doesn't prove the fix
   worked. This is a repeat mistake (plan text typed flags from memory on
   2026-07-14 and again on 2026-09-11): look the flags up in `breeze
   build-docs --help` of the worktree you are in (see the flags note in the
   last section of this chapter).

2. The built output lands under
   `generated/_build/docs/apache-airflow-providers-<dist>/stable/`. Open the
   HTML file directly with `file://` — no server needed to get real styling.
   Exception: a client-side search that fetches same-origin resources at
   runtime (e.g. Pagefind) is blocked by CORS under `file://` — verifying
   that specific behavior needs an actual `http://` server; a plain
   static-page screenshot is unaffected.

3. Take at least three screenshots:
   - The new page itself (the full page, so the reviewer sees surrounding context).
   - The index/toctree entry that links to it (proof a reader can actually find it).
   - The **after** state of any existing page whose section this PR rewrote.

   Getting a true before/after pair means building `base` branch separately
   too, which doubles the cost — ask before doing that extra build.

4. Before reusing an existing build's output, compare its mtime against the
   current `HEAD`. A stale build predating the current commit will screenshot
   old content while the file still exists and the build command still
   exits 0 — nothing about that failure mode is visible from the command's
   own output. Before trusting a screenshot, assert
   `document.styleSheets.length > 0` in the page to catch an unstyled blank
   capture.

5. **The rendered HTML is the evidence for a cross-reference.** A new `:ref:`
   resolving is only directly visible in the built page; a zero-hit warning grep
   or a bare exit code proves nothing about one specific cross-reference.

6. This machine's own ability to run `build-docs` is unrelated to whether
   its Breeze CI image can be rebuilt. `ANSWER=no breeze build-docs
   --package-filter apache-airflow-providers-<x> --one-pass-only` (with or
   without `--clean-build`) completes with exit 0 here in a few minutes — that's a separate image
   from the one that fails to rebuild on arm64 (see §3's
   `breeze-ci-image-unbuildable-arm64` entry below). Don't read "the CI
   image is unbuildable on this machine" as "skip the docs build check" —
   confirm the specific image involved before drawing that conclusion.

7. **A page containing a `.. mermaid::` diagram needs its own render check
   before a screenshot is evidence of anything.** This theme renders mermaid
   client-side via `mermaid.run()`, and diagrams starting outside the
   viewport are deferred until an `IntersectionObserver` fires — a headless
   screenshot taken before that fire either shows no `<svg>` yet or an `<svg>`
   mid-layout. Poll before capturing:

   ```js
   document.querySelectorAll('pre.mermaid').length ===
     document.querySelectorAll('pre.mermaid svg').length
   ```

   Scrolling a diagram into view to trigger that render has its own trap:
   setting `scrollTop` or calling `window.scrollTo` without an explicit
   `behavior: 'instant'` can pick up a smooth-scroll animation from the
   page's CSS, so a screenshot taken ~300-400ms later lands mid-scroll —
   the capture shows the fixed header overlapping content that should
   already have scrolled past it. Force instant scroll on all of
   `document.documentElement.scrollTop`, `document.body.scrollTop`, **and**
   `window.scrollTo({top, left: 0, behavior: 'instant'})` together, then
   re-read `window.scrollY` to confirm it actually reached the target before
   capturing. The simplest reliable capture is a full-page screenshot with no
   `clip` at all (`Page.captureScreenshot` with no `clip`/`captureBeyondViewport`)
   — a clipped capture computed from a pre-scroll bounding box, or taken
   right after programmatic scroll, has repeatedly produced a blank or
   wrongly-offset image even though the diagram itself rendered correctly.

8. **Judging whether a PR's existing screenshot is stale means comparing against what
   the screenshot captured, not against which files changed.** "The same template was
   modified since the screenshot" is only a lead. Evidence is the intersection of two
   things: the region of the page the image actually shows (read the image, or convert
   its height into screens of the page), and which section of the template or page the
   change landed in. A reviewer's "update the screenshot with recent changes" case: a
   rebase pulled in another PR that edited the same template, so it was asserted that
   the screenshot "will surely show it" — but that change only touched a section the
   screenshots never captured, and the images came out identical. Check in two layers:
   (a) whether the PR's own UI diff changed between the push the screenshot was taken at
   and now (compare the added/removed lines of the affected source per push), and (b)
   whether anything the base brought in lands inside the captured region. If the captured
   region can't be established, say "probably stale/fresh" rather than "definitely".

### Local docs, chart and prek recipes (companions to steps 1–6 above)

- **Flags — check `--help`, the steps above may name flags your breeze lacks.**
  In current `main` (checked in `developer_commands.py` and `breeze build-docs
  --help` at `01907e047f5`) there is **no** `--docs-only`, `--spellcheck-only`
  or `--python`; `--docs-only` exits with `No such option`. Select a
  provider with `--package-filter apache-airflow-providers-<x>` (or the short
  positional `common.ai`) plus `--one-pass-only`; the default scope already
  builds Python docs *and* spell-checks them (steps 1–6 above use this form).
  `--sdk-docs-only` is SDK-only. On an older release branch whose `--help`
  still lists `--docs-only` / `--spellcheck-only`, those flags are defined there (confirmed in the `v3-1-test` / `v3-2-test` source, not run).
- **A fresh worktree's first `breeze build-docs` is slow.** It first builds that
  worktree's own breeze venv (~10 min, silent), then builds the CI image from
  scratch (30+ min of apt downloads) before Sphinx starts; with a recent CI
  image the image step takes seconds to minutes. Run it in the background,
  output to a file:
  `breeze build-docs --package-filter apache-airflow-providers-<x> --answer y
  > <log> 2>&1 < /dev/null`. Without `--answer` and with a non-tty stdin, breeze
  asks whether to build the image and aborts with `Errno 22`, exit 1 — which
  looks like a docs failure but is the prompt. The background task's "exit 0"
  is the wrapper's; read the real verdict from an `echo DOCS_EXIT=$?` you add
  and from "Documentation build is successful". Spelling has no separate pass
  line (only the sphinxcontrib-spelling install line appears), so
  "no spelling report" is weak evidence. Verify rendering from the built HTML
  (`generated/_build/docs/<dist>/stable/…/*.html`, newer than the rst), not by
  grepping the rst. If it can't finish in time, say in the PR that the docs
  build is left to CI.
- **Host (no breeze) docs build on macOS can be a false report.**
  `uv run --group docs build-docs` in a provider directory without the enchant C
  library fails to load `sphinxcontrib.spelling`, reports doc-build and spelling
  errors, and still exits 0 — nothing was verified. Look for "Finished docs
  building successfully" and "Finished spell-checking successfully", not the exit
  code. Local route: `brew install enchant`, set `PYENCHANT_LIBRARY_PATH` to the
  `libenchant-2.dylib` under Homebrew's `lib` directory (`$(brew --prefix)/lib`),
  and add every `<worktree>/shared/*/src` to `PYTHONPATH` (else
  `ModuleNotFoundError: airflow_shared` from the `metrics_tables_from_registry`
  extension). Homebrew's dictionary lacks `Anthropic` and yields ~55 extra
  spelling hits, mostly unrelated to your change and never baselined against
  `main`; decide whether a hit is yours with `git show HEAD:<file>` (does the
  line already exist?). The breeze route needs no enchant, but another worktree
  building at the same time competes for the Docker daemon (a CI image build once
  stalled 70+ min).
- **Chart tests need breeze — there is no local `helm`.**
  `uv run --frozen --project chart python -m pytest chart/tests/...` raises
  `FileNotFoundError: 'helm'`. Use `breeze testing helm-tests --use-xdist
  --test-type <component>` (e.g. `airflow_core`; ~80 s, 769 passed, when the CI
  image already exists). Don't add `--skip-image-upgrade-check --answer no`:
  they were taken as pytest arguments (exit 4). For a mutation check, restore the
  template to `main`'s and rerun the same command to see the matching test go red.
- **A local `prek` older than `minimum_prek_version`** in `.pre-commit-config.yaml`
  (currently `0.4.8`) fails with `Failed to parse .pre-commit-config.yaml`
  (exit 2). Run `uvx prek@<required version> run --files <each file listed>`
  instead of touching the global install; the output must actually show
  `Passed` (not `no files to check`), and `shasum` the files before and after to
  prove no auto-fixer changed them.

## After `git worktree move`: Airflow-specific stale paths

The general symptoms and fixes (stale shebangs, stale `.pyc`, an old absolute path in
`.claude/test-command`) are in
[`git-workflow`'s `worktree-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-hygiene.md)
("After `git worktree move`"). The Airflow-specific instances:

- A pre-commit/prek `mypy-<project>` hook fails with exit 126, or with ``Failed to spawn: `mypy` ``
  (os error 2) when the hook runs `uv run ... mypy`: the shebang of `.build/mypy-venvs/<hook>/bin/mypy`
  still execs the old path's python. `head -1 .build/mypy-venvs/<hook>/bin/mypy`; if it shows the old
  path and `git check-ignore .build` confirms it is ignored, delete that hook's venv directory and
  rerun.
- Stale `.pyc` example: `dev/registry/tests/__pycache__`.
- `.claude/test-command` may carry the old absolute `AIRFLOW_HOME`.
- Provider venvs also need `PYTHONPATH=<worktree>/shared/secrets_masker/src` for tests that use the
  structlog `caplog` fixture (otherwise `No module named 'airflow_shared'` at fixture setup), and
  that path goes stale on a move too.
