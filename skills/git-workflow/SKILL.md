---
name: git-workflow
description: This skill should be used when assembling git commits — deciding what to stage, how to scope a bash/agent command's working directory, whether to amend an unreleased commit or stack a new one, and how to size a diff against the correct baseline. Applies to the commit-assembly step of /maigo:go, /maigo:quick, /maigo:team, and /maigo:address-comments, and to the orchestrator generally.
---

<!-- mkdocs-include-start -->

# Git Workflow

**Consumers**: commit-assembly step of `/maigo:go`, `/maigo:quick`, `/maigo:team`, `/maigo:address-comments`; the orchestrator generally whenever it runs git commands or briefs an agent that will.

## Why this skill exists

Committing a scoped change and running git commands correctly across
worktrees are mechanical steps that are easy to get subtly wrong: staging
too broadly, mutating shell state with `cd`, fixing a CI failure on the
wrong branch, or reasoning about diff size against the wrong baseline. None
of these mistakes fail loudly at the time — they surface later as unrelated
noise in a PR, a confusing force-push, or a wrong claim in a summary. This
skill collects the conventions that keep git operations scoped to exactly
what was intended.

## Scoping and staging

### Stage explicit files, never `git add -A`

When committing a scoped change, stage the specific files by path. Do not
use `git add -A` / `git add .` — the working tree often carries regenerated
or drift files (lockfiles, generated dependency manifests, build caches)
that a blanket `add` will sweep into the commit as unrelated noise.

How to apply: run `git status` first and read it. Stage only the intended
paths: `git add <file1> <file2>`. Be especially careful after a rebase, a
package-manager sync/install step, or after a delegated subagent ran — those
can leave unexpected generated changes in the working tree.

**Treat drift as drift, not just "don't stage it" — revert it.** A
package-manager install/codegen step (backend or frontend) can silently
rewrite a lockfile's security-relevant sections (e.g. deleting a version
`overrides:`/pin block) or scaffold a placeholder config file, in addition
to ordinary dependency-drift noise. After any such step, run
`git diff HEAD --stat` and scan for lockfiles, workspace-config files, and
other generated artifacts; `git checkout HEAD -- <file>` (or delete a
scaffold file) anything not intentional. Leaving it unstaged still risks a
later blanket `add` or a teammate sweeping it in — and a dropped security
pin is a real regression, not just noise.

### Don't `cd`; use absolute paths

Never `cd` into worktrees or other directories when running git/bash
commands or briefing another agent. Always:

- Use **absolute paths** for file arguments.
- Use **`git -C <worktree-path>`** for git commands targeting a different
  worktree.
- Use tool-specific working-directory flags when available (e.g.
  `pytest --rootdir`, a package manager's `--project`/`--cwd` flag).
- When briefing another agent that will run commands: state the working
  directory as **context** ("Working dir: /abs/path/to/worktree") but don't
  hand it a `cd <path> && <cmd>` instruction — the agent should use absolute
  paths or `git -C` directly.

Why: `cd` mutates shell state, complicates tool composition, and most
harnesses already handle per-tool working directory cleanly via absolute
paths or `-C`-style flags.

**Exception**: if a human explicitly asks to `cd` somewhere, do it.
Otherwise default to no-`cd`.

This matters most in multi-worktree setups, where several sibling worktrees
exist off the same upstream and it's easy to accidentally run a command
against the wrong one after a `cd`.

## Commit assembly (amend vs. new commit vs. which branch)

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
commit (see "Fold polish into the unreleased introducing commit" above).

## Sizing a diff

### Diff against the real merge-target baseline, not the branch tip

When quantifying a change's footprint — "what gets deleted", "is this a big
diff", "much smaller than what" — establish the real baseline **first**:
`git diff upstream/main..HEAD` (or the repo's actual merge target) and
`git show upstream/main:<file>`. Don't reason against the current branch tip
as if it were the merge target.

Why: it's easy to describe a change as "net-delete N lines of `symbol`"
without checking whether `symbol` exists on the merge target at all — if the
symbol was introduced by the branch's own unmerged feature commit, the
"deletion" is actually reworking in-flight work, which completely changes
the framing (an amend of the feature commit, not a deletion stacked on top —
see "Fold polish into the unreleased introducing commit" above).

How to apply: before stating diff sizes or "what gets removed", run
`git rev-list --count upstream/main..HEAD` and check whether the code being
"deleted" actually exists on the merge target
(`git show upstream/main:<file> | grep <symbol>`). If the branch carries
unmerged feature commits, the honest comparison is "reworked commit vs.
current commit" (an amend), not "vs. the merge target". Verify empirically
against `git show`/`git diff` output — don't assert sizing from memory of
the working tree.

## What this skill does NOT cover

- Drafting the commit message text itself — see
  [`commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md).
- Deciding *whether* to commit at all, or when in a flow the commit happens
  (e.g. after Soyo + Taki pass) — that's the calling command's own policy.
- Pushing / PR creation — separate step, separate skill
  ([`github-title-description`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/SKILL.md)).
