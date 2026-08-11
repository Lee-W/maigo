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

## Cross-provider/cross-feature batches: one branch and worktree per item

A batch of changes spanning multiple independent items — multiple provider
packages (even when unified by one theme, e.g. a docs-correctness pass across
`openai`/`anthropic`/`common.ai`), or several independent sub-features under
one umbrella topic — should land as **one branch, one sibling worktree, one
commit per item**, not a single combined branch.

Why: providers (and independent sub-features generally) release and get
reviewed on their own timeline; bundling them into one branch couples
otherwise-independent review and merge decisions.

How to apply:

- It's fine to implement centrally in one worktree first — parallel agents
  editing different providers/items don't collide — then split the result:
  `git diff --cached -- providers/<name>` exported per item, `git apply
  --index` into each item's own new worktree for its own commit. There's no
  requirement to implement centrally first, either — going straight to one
  `git worktree add <path> -b <branch> upstream/main` per item and delegating
  each independently is equally valid.
- Before basing a new split-out worktree on the current in-flight branch,
  check whether the infrastructure it needs already exists on the default
  branch (`git diff main..<in-flight-branch> -- <relevant-paths>`). If the
  dependency is already on the default branch, base the new worktree there
  instead of on the unmerged branch — basing on in-flight work drags unrelated
  review noise into the new PR.
- Name each split-out worktree/branch per the sibling-layout convention above.
  The combined worktree used for central implementation is an intermediate
  artifact — remove it once the split verifies clean.

## Colliding work: defer the overlapping subset

When starting a batch of approved work, first check for in-flight branches;
if some items overlap the same files as an active branch, default to **doing
the non-colliding subset now and deferring the colliding subset**, rather
than landing everything straight on the default branch to "get it all done
in one pass."

Why: forcing all items through at once when several collide with an active
branch's files creates merge conflicts in every touched file once that
branch lands — a worse outcome than a short delay. Users asked to choose
consistently pick "do the non-colliding items now, defer the rest" over
either "do everything now and resolve conflicts myself" or "fold it into the
existing branch."

How to apply:

- Before starting, run `git diff --name-only main <active-branch>` to
  compare the **file sets**, not just branch names, for overlap.
- Defer colliding items until the active branch merges into the default
  branch; proceed with non-colliding items normally.
- Report the split explicitly to the user (what's happening now, what's
  deferred, why) — don't silently skip items.
- Check whether a deferred refactor/deprecation may already have been picked
  up incidentally by the active branch — re-doing it would be wasted work.
- **If work truly must happen in parallel with the in-flight branch (can't be
  deferred), open a separate `git worktree` — don't run both flows against
  the same working tree.** Sharing a tree risks switching to the other
  branch unnoticed and clobbering the other flow's uncommitted staged
  changes.

This is the same judgment as "when to open a new worktree for a pre-existing
issue" above — look at what's actually changed before deciding scope, rather
than defaulting to doing the whole approved list unconditionally.

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

## Shared `.git` across sibling worktrees: stash is a single global stack

All sibling `<repo>-<topic>` worktrees share the main checkout's `.git`, so
`refs/stash` is **one global stack** — two agents stashing/popping
concurrently in different worktrees can pop and drop each other's WIP. When
a parallel task needs a "does this fail without the fix" check, use a
temporary edit + restore (`git diff > patch; git checkout --; ...; git apply
patch`) instead of `git stash`. The read-only verification discipline for
*review* tasks specifically lives in
[`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)'s
"共用 working tree 上的審查紀律" section — this note is the underlying
mechanism (why stash is unsafe at all), and applies beyond review too.

This isn't limited to `refs/stash`: any shared-object-store operation can be
affected by another session — a sibling worktree's branch has been observed
rebased twice by something other than the current session, visible only via
`git reflog` (unrequested `rebase (start): checkout main` events with no
stash involved). After any commit in a shared-checkout worktree, confirm the
branch still contains exactly the expected commits (`git log --oneline
upstream/main..HEAD` or equivalent) — don't assume a stable commit hash
across the session, and don't assume a reflog-visible rewrite is
self-inflicted just because no stash was involved.

## Reverify branch and status before any write action

A shared workspace (multiple parallel sessions/terminals against the same
checkout) can have its current branch, commits, or even a push+merge change
underneath a session without that session seeing it happen. Don't assume
the git-status snapshot from the start of the conversation — or the last
time it was checked — still holds. Before any commit, mass file edit, or an
assumption that "my earlier changes are still there," re-run `git branch
--show-current` and `git status`.

**Not even a worktree you just created is private.** A newly-created
worktree/branch has been observed to already exist on `origin` (matching
SHA, without the current session ever running `git push`) minutes after
creation, with an unrequested rebase stuck mid-conflict — no push hook or
reflog entry explained the source. Before a key operation, in addition to
`git branch --show-current` + `git status`, also check:

```bash
ls "$(git rev-parse --git-path rebase-merge)" "$(git rev-parse --git-path MERGE_HEAD)" 2>/dev/null   # in-progress rebase/merge?
git ls-remote --heads origin <branch>                                                                # does origin already have this branch?
```

If origin already has the branch, any further amend/reset rewrites an
already-published ref — ask the user first (see
[`references/outward-ops-authority.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/outward-ops-authority.md)
for who runs the eventual push). If a rebase/merge shows up that this
session didn't start, don't `--abort` it unilaterally — report it first.

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

## Don't write to a worktree while a dispatched verifier is running there

The read-only discipline in
[`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)'s
"共用 working tree 上的審查紀律" covers what a *reviewer* must not do to a
shared tree. The symmetric rule applies to the orchestrator itself: after
dispatching a verification/review agent (Taki/Soyo-equivalent) against a
worktree, don't also `Edit`/`Write`/`commit --amend` that same worktree
yourself while the delegate is still running — even a one-line, seemingly
safe fix. A delegate reading the tree mid-edit can observe a transient,
non-final state (a change appearing then reverting) and can't tell whether
that was a real regression or just caught the orchestrator's own edit window;
its final report may then carry an unresolved "can't 100% rule out
contamination" caveat even when the edit itself was correct.

Apply one of two orderings instead: finish your own edit and let it settle
(commit) *before* dispatching the verifier, or wait for the currently-running
verifier to finish before editing the worktree it's using. Don't interleave.

## Sweep sibling worktrees for stray contamination after parallel dispatch

When dispatching several delegated agents in parallel, each assigned its own
sibling `<repo>-<topic>` worktree (e.g. implementing parallel tracks of the
same issue), a delegate can write to the **wrong** absolute path — a stray
`cd`, a copy-pasted path from a different track's prompt — and land its early
edits in a completely unrelated worktree instead of the one it was told to
use. That worktree's own commits stay untouched, but its working tree picks
up an uncommitted, unrelated diff that looks like someone else's WIP.

This isn't caught by verifying the target worktree alone — it's clean there
by the time the delegate finishes, because the delegate typically
self-corrects and finishes the real work in the right place. The evidence
only surfaces by checking the *other* worktrees in play:

```bash
for d in <other-sibling-worktrees>; do
  git -C "$d" status --porcelain
done
```

A worktree that should be untouched showing unstaged modifications is the
signal. Confirm before discarding: diff the stray files against the
delegate's actual (correct) output — if byte-identical, it's this class of
mistake, not independent unrelated work in progress; check `git log --oneline
-5` in the contaminated worktree to confirm its own commit history is
untouched. Since these are only unstaged working-tree changes, `git checkout
--`/`git restore` on just the stray files is safe — it doesn't touch that
branch's real commits. Don't assume which delegate caused it from directory
naming alone; a delegate can genuinely have never touched the wrong path
itself (always-absolute-path tool calls), in which case a separate parallel
session is the more likely source — verify via file mtimes relative to each
delegate's actual working window before attributing blame.

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
