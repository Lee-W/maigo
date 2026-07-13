# Git Workflow — Worktree Hygiene

Loaded on demand by `skills/git-workflow/SKILL.md` — **worktree lifecycle and
git-attribution conventions** that recur across multi-worktree setups. Read
this file when opening, cleaning up, or reasoning about the state of a git
worktree, or when git history looks surprising after a delegated task.

---

## Worktree layout: sibling of the main checkout, plain branch name

Worktrees live as **siblings of the main checkout**, under the same parent
directory as the primary clone, named `<repo>-<topic>`, on a branch named
plainly `<topic>` (no prefix, no issue number) — e.g. a main checkout at
`<workspaces-root>/<repo>-main` gets a sibling worktree at
`<workspaces-root>/<repo>-<topic>` on branch `<topic>`.

A harness's built-in "create worktree" tool may default to a nested path
(e.g. under `.claude/worktrees/`) with a prefixed/decorated branch name (e.g.
`worktree-<topic>-<issue-number>`) — that default does not match this
convention and should be corrected:

```bash
git worktree add -b <topic> <workspaces-root>/<repo>-<topic> upstream/main
```

If the harness already created the nested one, fix it after the fact rather
than discarding the commit:

```bash
git worktree move <nested-path> <workspaces-root>/<repo>-<topic>
git -C <workspaces-root>/<repo>-<topic> branch -m <old-name> <topic>
```

A new worktree needs its own per-worktree tooling setup (e.g. a repo-specific
environment bootstrap script) run once — don't assume it's inherited from the
main checkout.

## When to open a new worktree for a pre-existing issue

When reviewing or working on a feature branch and a **pre-existing** issue
surfaces (bug, nit, refactor, missing test that would still be a problem if
the current feature branch didn't exist), don't fold the fix into the current
branch. Open a new worktree from the upstream default branch with its own
branch and commit there — this keeps the fix independently reviewable,
mergeable, and back-portable, and keeps the feature branch's own review
focused.

Don't conflate "pre-existing" with "ancient" — a bug introduced last week on
the default branch is still pre-existing for an unrelated feature branch.

Two counter-cases:

- **Directly blocking**: if the pre-existing issue blocks the current branch
  (broken test infra, broken build, makes review impossible), discuss before
  splitting rather than mechanically opening a worktree.
- **Proportionality**: for a genuinely trivial pre-existing change (e.g. a
  few-line test parametrize fix), a whole worktree + branch + separate PR is
  disproportionate ceremony. Surface the actual diff size and let the user
  choose between "fold it in as a standalone commit" and "keep it split out"
  — don't mechanically default to a worktree for a tiny diff.

## Batch worktree/branch cleanup

Cleaning up multiple worktrees/branches at once is a batch, destructive
operation — treat it with two extra safeguards beyond the general "confirm
before destructive ops" rule:

1. **Show the actual command list before running anything.** A yes/no on "do
   you want to clean up merged worktrees/branches" is not the same as
   approval to run specific `git worktree remove` / `git branch -D` commands.
   List the exact commands (including which directories/branch names they
   touch) and let the user review the concrete list, not just the direction.
2. **Don't chain many worktree/branch operations in a single shell call.**
   Chaining 8-9 `git worktree remove` + `git branch -D` invocations with `&&`
   or newlines in one command, against a large repo, can accumulate enough
   wall-clock time to trip a shell tool's default timeout partway through —
   the trailing commands look "stuck" when they're actually just queued
   behind the earlier ones. Either split into several smaller calls, or pass
   an explicit longer timeout. If a batch call is interrupted, check actual
   state (`git worktree list`, `git branch`) before assuming everything
   failed or everything succeeded, and only re-run what's left.

### Determining "already merged" needs `gh`, not just git ancestry

`git branch --merged upstream/main` is unreliable for deciding whether a
branch is safe to delete when the repo uses **squash-and-merge**: squashing
produces a brand-new commit on the target branch, so the original feature
branch's commits never become ancestors of it — `--merged` will report the
branch as "not merged" even when its PR landed weeks ago.

Correct approach: list merged PRs by author (`gh search prs --repo <repo>
--author <user> --merged --json number,title,closedAt`), then compare each
candidate branch's commit subjects (`git log upstream/main..<branch>
--oneline`) against a PR's commit list (`gh pr view <n> --json commits`) to
confirm which branch corresponds to which merged PR.

### `gh` CLI blocked by organization SSO enforcement

A `gh` command against a repo under an organization with SAML SSO
enforcement can fail outright with a "Resource protected by organization SAML
enforcement" error — this is not a transient network issue, retrying does
nothing; the token needs one-time browser authorization against that org
first. When the task is just "check whether a PR merged", prefer querying the
canonical upstream repo directly rather than a fork under an SSO-enforced org
that isn't actually needed for that query.

## Don't over-attribute unexpected git state to a rogue agent

On a user's own WIP branch, commits / `fixup!` commits / staging / force-pushes
that appear unexpectedly are more often the **user working in a parallel
terminal** than a rogue agent — author name alone isn't evidence, since agent
commits are typically authored under the same identity as the user (repo git
config). Over-claiming "an agent went rogue" erodes trust and costs
round-trips to walk back.

How to apply: when delegating a pure file-edit task, give the delegate an
explicit "no git writes" instruction so the working tree stays clean for the
user to stage/commit themselves — the orchestrator doesn't auto-commit and
doesn't raise git alarms on its own. If git state looks surprising, verify
attribution quietly (reflog timestamps, what's actually staged) and report
the factual state plainly, asking what happened rather than asserting an
agent went rogue.

## Verify a delegated agent's git state before committing

Don't trust a delegated agent's self-report ("tests green / done") at face
value before committing on top of its work. Verify independently: `git
reflog` for unexpected rebase/commit/amend events, `git log` for changed
SHAs, `git status` for stray generated/drift files. When an agent claims a
failure is "pre-existing" or "unrelated to my change", confirm it yourself
(stash the change and re-run, or run against the base) rather than accepting
the claim as-is — a delegate that was explicitly told not to commit/rebase
can still do so, tangle unrelated changes together, and misreport a bug it
introduced itself as pre-existing.

## Verify the landed commit subject, not just the tool's printed output

After every `git commit`, immediately confirm with `git log --oneline -1` (or
`-3`) that the landed subject line actually matches what was passed — don't
trust the shell tool's echoed command string as proof of what happened. A
commit can silently land with the wrong subject (e.g. folded into an
unrelated `fixup!` target) with no error surfaced. If the subject is wrong
and the commit is still local/unpushed, `git commit --amend` is safe to fix
it — but check before assuming a git write did what the command string said.

## "Fix the commit message" on a tmp/mislabeled branch means squash, not reword

When a branch carries `tmp` commits or commits with a mislabeled/leftover
message (e.g. a message copied from unrelated prior work), and the user asks
to "fix the commit message," the intent is usually to **squash the entire
branch** (including any uncommitted working-tree changes) into a single
commit with a correct message — not to `reword` just the tip. This kind of
branch's commit boundaries are throwaway/staging artifacts with no
preservation value; leaving them as separately-reworded commits keeps noise
in the history for no benefit.

How to apply: `git reset --soft $(git merge-base main HEAD)`, stage the
relevant files, and land one commit with a message that follows the repo's
own convention (see [`commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md)).
