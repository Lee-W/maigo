# Python tooling gotchas (stale environments, shared `.venv`)

Loaded on demand by `skills/python-aware/SKILL.md` — environment traps that make a
test run look red, green, or skipped for reasons unrelated to the code under review.
Read this file before running tests on a branch that changes a dependency floor or the
lockfile, and before delegating test runs to a subagent that shares a worktree's `.venv`.

---

## A change that raises a dependency floor makes an unsynced venv produce a false red — and defeats the usual base-commit attribution check

When a PR changes a `pyproject.toml` version floor or `uv.lock`, **neither
the local `.venv` nor any prebuilt container image picks it up automatically**. Running
that package's tests without syncing first produces `ImportError: cannot
import name '<NewSymbol>'`-style collection errors — that's the environment
missing the version the PR requires, not a code defect.

**Why this false red is unusually dangerous**: the usual attribution check —
"rerun on the base commit; if it's broken there too, it's pre-existing, not
this PR's fault" — gives the *right procedure* but the *wrong conclusion*
here. The base commit is broken too (it also needs the new floor, since the
floor bump usually comes from a lower layer of the same stack), so the
result gets attributed to "pre-existing, ignore" — but the true story is
"the PR's required version was never installed," and **the entire test run
carries zero information, including the tests that "passed."**

Judgment: **before running tests, check whether the PR (or a layer beneath
it in the same stack) touched a version floor or the lock file.** If so,
sync the environment first.

```bash
uv sync --project <PROJECT>           # install per the PR's lock
# probe with the PR's own newly-introduced symbol, not just a version string
uv run --project <PROJECT> python -c \
  "from <pkg>.<mod> import <NewSymbol>; import <pkg>; print(<pkg>.__version__)"
```

Only proceed to tests once the probe prints the expected version and
imports cleanly; if it doesn't, stop and report where it's stuck rather than
running tests against a half-synced environment. Don't reach for a prebuilt
container image as a shortcut here either — its packages are equally stale.
`uv run --project <PROJECT> pytest` is sufficient once synced.

## Don't let a subagent `uv sync` a shared worktree `.venv` — only `uv run --frozen`

Scope: a subagent working in a uv-workspace monorepo worktree whose `.venv` is shared. (A
plain `uv sync --project ...` is fine in your own or an isolated environment,
where pruning is acceptable.) A subagent running `uv sync --frozen --project <pkg>` there prunes
packages outside that package's dependency set from the shared `.venv` (a large number were
observed removed), including optional extras. Tests then flip from pass to **skip**, not
red, so nothing alerts you. State it in the delegation prompt: `uv sync` is forbidden, use only
`uv run --frozen --project <pkg> ...`; after the run, check that the skipped count didn't jump.
