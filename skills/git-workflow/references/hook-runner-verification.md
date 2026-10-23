# Git Workflow — Hook Runner Verification

Loaded on demand by [`skills/git-workflow/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/SKILL.md) —
behavior of git hook runners (`pre-commit`, `prek`) that produces a clean-looking
run which checked nothing, checked the wrong content, or failed for tooling
reasons unrelated to your code. Read this file before trusting a hook runner's
"Passed" / `exit 0` as evidence about a change, when a hook is blocked or
skipped for no visible reason, or before building a new hook. The shapes are
language-neutral; the examples use `prek`, and `pre-commit` behaves alike.

---

## Reproduce a hook failure from the repo root

A hook runner's working directory decides which config file loads and how
relative `entry:` paths resolve. A green run from a subdirectory proves
nothing about CI, which runs from the root. Reproduce a hook or CI failure
from the **repo root**; a `` Running hooks for `<dist>`: `` line in the output
confirms which config actually ran. The only acceptable exception is
deliberately picking a directory to dodge unrelated noise (for example a
sub-tree that avoids an unrelated link-checker network failure) — never to
make the target hook pass. A repo that has a sanctioned exception states it in
its own repo-aware skill.

## Unstaged changes are stashed away, then restored

`prek run <hook>` stashes any unstaged changes to a patch file in
`~/.cache/prek/patches/` before executing, then restores them afterward — the
hook only ever sees **staged + committed** content. This is silent (prek just
prints `Unstaged changes detected, stashing...` / `Restored working tree
changes from ...`), so a PASS with unstaged edits in flight means "your
staged/committed state is clean," not "your current edit is clean."

This applies to `--from-ref <base>`, to `--all-files`, **and to `--files
<paths>`** — naming the exact paths does not exempt you from staging. Before
trusting any hook-runner green as evidence about a just-made edit, `git add` it
first, or confirm `git diff --stat` (unstaged) is empty. Alternative:
invoke the underlying tool directly (`uv run ruff format <file>`), which sees
the real on-disk tree with no stashing.

`--from-ref` can also silently compute an empty diff range and report
`(no files to check) Skipped` for a hook even though your change *is*
staged/committed — read `Skipped` as "did not run," never as "passed."

## Before building a new hook: surface the genericity/fragility trade-off first

Before adding a new hook, answer two questions **up front** and surface them to
the user for sign-off — don't wait until the hook is fully implemented (with
tests, registered in `.pre-commit-config.yaml`) before the user gets a chance to
reconsider:

1. Do sibling checks already exist for a similar concern? A CI gate scoped to
   only one module when its siblings have no equivalent check is an
   inconsistent precedent worth calling out.
2. Will the check false-positive on a small, unrelated change (a doc
   reformat, a cross-reference restyling)? A brittle detection heuristic
   costs more in false-positive triage than it saves.

Beyond that up-front check, prefer **dynamic discovery over hardcoded
references** — for example walk a migration chain through its own directory or
API rather than hardcoding specific revision IDs, so a new entry added later is
automatically in scope without a script edit. And stop to simplify when a
hook's design starts accreting per-version matrices, baseline files, or
regenerate-baseline flags — a design that doubles in complexity in one
session usually has a simpler alternative (for example collapsing to a single
linear walk with no baseline) that gives the same coverage.

## `git add -N` breaks the hook runner itself

A file staged with `git add -N` (intent-to-add) has an all-zero blob hash.
prek's pre-hook worktree cleanup runs `git rm --cached --` over the index,
which exits 128 on such an entry — the hook never runs and prek reports
**exit 2** (`Failed to clean work tree`). This is a tooling failure, not a
finding about your code, but it is easy to misread as "the hook caught
something." Never leave a file in `-N` state when the hook runner will run —
either fully `git add <path>` it, or leave it untracked and read it directly
instead of trying to make `git diff` show it.

## `git rebase --continue` runs no hooks at all

`git rebase --continue`'s resulting commit does **not** trigger pre-commit /
prek — its output is only `Recorded resolution ...` and `[detached HEAD
<sha>] <subject>`, with no hook lines whatsoever. (`git commit --amend` in
the same worktree does run the full stage.) The tell is simply **whether the
hook output lines are present** — their absence means the commit was never
checked, even if an earlier `amend` in the same session was green; that
green doesn't carry forward across a rebase, since the commit is re-applied
onto a new base with unreviewed conflict resolutions and upstream code.
Follow-up verification: `prek run --from-ref upstream/<target_branch> --stage
pre-commit` (subject to the stashing trap above and the word-splitting trap in
[`harness-discipline`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/shell-and-tool-gotchas.md)).

See also
[`commit-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/commit-hygiene.md)
on reconciling the file count after `rebase --continue` / `cherry-pick`.

## A misconfigured `files:` regex can leave a hook permanently inert

A hook declared with `files: ^.*/docs/.*/connections.*\.rst$` requires an extra
directory level between `docs/` and `connections` that the real path
(`<pkg>/docs/connections/*.rst`) doesn't have. Every real file matches **zero**
times; the hook has never actually run against any of them. Running it reports
`(no files to check) Skipped` and **exit 0** — indistinguishable from passing.
When a hook's regex is suspect, verify by running the underlying check script
directly rather than through the runner, and confirm the Passed/Skipped
distribution, not just the exit code — the same diagnostic used for an
unexpanded `--files` argument applies here too.

## A root-owned or half-deleted prek toolchain cache breaks every Python hook

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
