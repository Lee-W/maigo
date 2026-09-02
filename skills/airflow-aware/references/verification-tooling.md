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
run that checked nothing, or checked the wrong content.

### Unstaged changes are stashed away, then restored

`prek run <hook>` stashes any unstaged changes to a patch file in
`~/.cache/prek/patches/` before executing, then restores them afterward — the
hook only ever sees **staged + committed** content. This is silent (prek just
prints `Unstaged changes detected, stashing...` / `Restored working tree
changes from ...`), so a PASS with unstaged edits in flight means "your
staged/committed state is clean," not "your current edit is clean."

This applies to `--from-ref <base>`, to `--all-files`, **and to `--files
<paths>`** — naming the exact paths does not exempt you from staging. Before
trusting any prek green as evidence about a just-made edit, `git add` it
first, or confirm `git diff --stat` (unstaged) is empty. Alternative:
invoke the underlying tool directly (`uv run --project <dist> ruff format
<file>`), which sees the real on-disk tree with no stashing.

`--from-ref` can also silently compute an empty diff range and report
`(no files to check) Skipped` for a hook even though your change *is*
staged/committed — read `Skipped` as "did not run," never as "passed."

### zsh word-splitting turns `--files $VAR` into one giant nonexistent filename

`prek run --files $FILES` (files stored in a variable first) gives a false
green under **zsh**: zsh does not word-split an unquoted variable expansion
(bash does), so prek receives the whole space-joined string as a *single*
filename. prek silently skips nonexistent filenames — every hook prints
`(no files to check) Skipped`, and the overall exit code is **0**. Looking
only at exit code hides this; **check the Passed/Skipped distribution per
hook**, not just the overall code.

Correct form (command substitution *does* word-split in zsh):

```zsh
prek run --stage pre-commit --files $(git diff --cached --name-only | tr '\n' ' ')
```

Two adjacent traps in the same family:

- `--from-ref` and `--files` **cannot be combined** — prek 0.4.6 errors
  outright rather than picking one. Pick one flag per invocation.
- **Manually listing files and missing one is also a false green, with zero
  signal.** Output stays all-`Passed`, exit 0 — nothing indicates a file was
  left out (a missed `docs/changelog.rst` skipped its dedicated
  format/duplicate-entry hook entirely in one incident, only caught by
  re-counting against the commit). Derive the file list from `git diff
  --name-only <base> <head>`, count it, and report "N files listed / N files
  in the commit" so a mismatch is visible.

### `git add -N` breaks the hook runner itself

A file staged with `git add -N` (intent-to-add) has an all-zero blob hash.
prek's pre-hook worktree cleanup runs `git rm --cached --` over the index,
which exits 128 on such an entry — the hook never runs and prek reports
**exit 2** (`Failed to clean work tree`). This is a tooling failure, not a
finding about your code, but it is easy to misread as "the hook caught
something." Never leave a file in `-N` state when prek will run — either
fully `git add <path>` it, or leave it untracked and read it directly instead
of trying to make `git diff` show it.

### The `identity` hook can report a false "files were modified" failure

`identity` (labeled "Print checked files") never modifies anything — it's
just where prek's "was this file touched before the hook ran" bookkeeping
gets reported when a *different* hook doesn't claim the change first. If a
commit is blocked with `Print checked files ... files were modified by this
hook`, but `git status --short` shows the working tree matches the index
exactly, that's a false signal. Confirm before dismissing it: run the full
pre-commit stage on just those files (`prek run --files "path/a.py"
"path/b.py"`, quoting each path individually to dodge the zsh trap above);
exit 0 and zero modifications means the false signal is real. Escape hatch:
`git commit --no-verify`, then separately run the commit-msg hook against
the already-written message so it isn't silently skipped.

### `git rebase --continue` runs no hooks at all

`git rebase --continue`'s resulting commit does **not** trigger pre-commit /
prek — its output is only `Recorded resolution ...` and `[detached HEAD
<sha>] <subject>`, with no hook lines whatsoever. (`git commit --amend` in
the same worktree does run the full stage.) The tell is simply **whether the
hook output lines are present** — their absence means the commit was never
checked, even if an earlier `amend` in the same session was green; that
green doesn't carry forward across a rebase, since the commit is re-applied
onto a new base with unreviewed conflict resolutions and upstream code.
Follow-up verification: `prek run --from-ref upstream/<target_branch> --stage
pre-commit` (subject to the stashing and word-splitting traps above).

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

### A misconfigured `files:` regex can leave a hook permanently inert

`providers/.pre-commit-config.yaml`'s `check-connection-doc-labels` hook has
`files: ^.*/docs/.*/connections.*\.rst$` — which requires an extra directory
level between `docs/` and `connections` that the real path
(`providers/<name>/docs/connections/*.rst`) doesn't have. All 100 real
connection docs across all providers match **zero** times; the hook has
never actually run against any of them. Running it reports `(no files to
check) Skipped` and **exit 0** — indistinguishable from passing. When a
hook's regex is suspect, verify by running the underlying check script
directly rather than through prek, and confirm the Passed/Skipped
distribution, not just the exit code — the same diagnostic used for the zsh
word-splitting trap above applies here too.

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

### A root-owned or half-deleted prek toolchain cache breaks every Python hook

When every Python-based prek hook fails with `... No such file or directory`
pointing at `~/.cache/prek/tools/python/<version>/bin/python`, the cached
interpreter is corrupt (partially deleted). If those leftovers are
root-owned (from a past `sudo prek` run), a non-sudo `rm`/`chmod` gets
Permission denied — the fix needs `sudo rm -rf
~/.cache/prek/tools/python/<version>`; prek re-downloads it on next run.
`SKIP=<hook>` only skips one hook, but all Python hooks share the same
toolchain, so `--no-verify` (after validating ruff/tests directly) is the
practical escape until the cache is fixed. A related but distinct failure —
a single hook failing the same way while the toolchain itself is fine — is a
vanished compiled-wrapper file under `~/.cache/prek/cache/python/`; that one
needs no `sudo`, since it's a cache directory rather than the root-owned
toolchain directory.

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
that would silence a real future regression too).

## 4. Attribution — don't accept a red's cause without proving it

### A scoped test run being red doesn't mean your diff caused it

Before narrowing a scoped test command further (or accepting a red result as
a regression from your change), require **0 lines** of `git diff
<base>...HEAD -- <path of the red tests>` (and the corresponding source
path) before calling those failures pre-existing/unrelated. Narrowing scope
until a run goes green is the same move as loosening an assertion — the
scope has to be justified by what the diff actually touched, not by what
happens to pass.

When the branch changes a data file rather than Python (a JSON schema,
`provider.yaml`, a config template), there is no mirroring test file to
scope to — invert the approach: find the test that *loads* that data file
and narrow to it with `-k`. Then **prove the gate is live** before trusting
a fast green on it: inject a deliberate break into the data file, confirm
the scoped command fails, restore from a byte-exact backup, confirm green
again.

### `.claude/test-command` (or any harness-invoked test script) runs as argv, not through a shell

A command configured to run as a fixed test entry point is typically
`exec`'d directly (`shlex.split` + `subprocess.run`, no shell) — an
`ENV=val cmd` prefix fails with `command not found` (note an unexpanded
`$HOME` in the error is the diagnostic), and there's no `&&`, no `$(...)`,
no `~` expansion. Put any setup logic into a sibling shell script instead
and make the configured command a one-liner that invokes it
(`/bin/sh /abs/path/to/run-tests.sh`). Verify by testing the way the harness
actually runs it, not via an interactive shell — a shell-eval green proves
nothing about argv-exec.

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
