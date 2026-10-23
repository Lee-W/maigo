# Python tooling gotchas (stale environments, shared `.venv`, hook scripts)

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

## A script that a hook runner executes directly: `requires-python` without an upper cap, and keep the shebang

For a new script that a hook runner execs directly, write the PEP 723 inline
metadata as `# requires-python = ">=3.10"` — **no `<3.11` upper cap** — and
keep the `#!/usr/bin/env python` shebang as the first line. An upper cap pins
the script's venv to exactly one Python version, which is unnecessary for a
plain AST/text check and hurts portability; `>=3.10` ("3.10 or newer") is
what's actually meant. The shebang matters because the runner execs the entry
file directly — a file with no shebang gets run under `/bin/sh`, which chokes
on Python syntax.

## Coverage: the `--cov` target must have the same shape as `[tool.coverage.run] source`

When measuring one module's coverage from a single test, give `--cov` the same kind of
target the config's `[tool.coverage.run] source = [...]` uses. With `source = ["mypkg"]`
(a module name):

- ✅ `uv run pytest tests/test_x.py::test_y --cov=mypkg.permission --cov-branch --cov-report=term-missing`
- ❌ `--cov=src/mypkg/permission` (a path) → **silently reports 0%**, exit code still 0

**Why this matters**: a false 0% looks exactly like a real 0% — no warning, no non-zero exit
code. If you are deciding "is this code exercised at all?", you reach the opposite conclusion
and may add a test that was never needed.

How to apply:

- Read `[tool.coverage.run] source` (in `pyproject.toml` or `.coveragerc`) first and match its
  shape (module name vs. path) in `--cov`.
- When you get 0%, suspect the target before concluding "not covered": re-run with a test that
  certainly exercises the code and confirm the number moves.
- To judge branch coverage, pass both `--cov-branch` and `--cov-report=term-missing`; without
  `--cov-branch` the report cannot show `A->B` arcs.
