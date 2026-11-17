# Git Workflow — Commit assembly 細節

Loaded on demand by [`skills/git-workflow/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/SKILL.md) — 決定 polish 要 amend 進哪個 commit、或修正該落在哪條 branch 時讀。
本檔內文原樣自 SKILL.md 搬出。

### Fold polish into the unreleased introducing commit

When the underlying feature commit on a local branch has never been
released, fold review-driven polish — parameter renames, docstring updates,
perf nits, additional tests — into the introducing commit via
`git commit --amend --no-edit` (or `--amend` with an updated message; see
[`commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md))
rather than keeping it as a follow-up commit.

Why: a parameter or symbol that never existed in a release doesn't need its
rename preserved as a historical artifact — squashing means it's born with
the right name and the rename never shows up in history. If the repo
squash-merges on merge, the end PR result is identical either way, but
cleaner local history helps the author's own rebase / pre-push self-review
workflow.

How to apply:

- Default to "amend into the introducing commit" framing when drafting how
  to land polish on a local feature branch.
- Only suggest a separate commit when the polish is genuinely independent —
  different feature scope, separate user-visible change, or the introducing
  commit has already been published to a PR that reviewers are mid-review
  on.
- Don't preserve a rename as a historical artifact when the renamed symbol
  was never released to users.

### When polish hunks are tangled, amend into the tip — don't reconstruct

The rule above says to amend polish into the *relevant* introducing commit.
When the polish is per-thread localized (a rename, a docstring, one new
test), do that — amend into the specific commit each thread targets. But
when multiple review threads all reshape **the same function or loop
together**, splitting the polish across commits requires hand-reconstructing
intermediate file states for an interactive rebase — a high-error-rate
operation that doesn't survive a later force-push cleanly.

In that case, default to amending everything into the **tip** (most recent)
of the unreleased commits, rather than reconstructing a midpoint version of
the function that never existed in isolation.

How to apply: during commit-assembly planning, inspect the actual staged
diff before committing to a split-amend plan. If hunks for multiple threads
collide in the same function and the intermediate state isn't naturally
meaningful on its own, fold everything into the tip commit instead. Surface
the deviation from a split-amend plan explicitly so the plan's author (or
the user) can override.

### A fix belongs on the branch that surfaced it, not a fresh branch off main

When an in-flight branch (e.g. a CI-environment-upgrade PR) is itself what
surfaces a new lint/type/test failure, the fix belongs **on that branch**
(folded into the same PR), not on a fresh branch cut from the main/default
branch.

Why: CI runs against the in-flight branch. A fix sitting on a separate
branch does nothing for the failing CI, and the failure often only exists
*because of* that branch's own changes (e.g. an upgraded dependency
revealing a type error that didn't exist before).

How to apply: before branching off the default branch to fix something,
check whether the failure was introduced by the currently in-flight branch.
If yes, apply the fix there and consider folding it into the introducing
commit (see "Fold polish into the unreleased introducing commit" above in this file).
