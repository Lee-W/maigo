# Git Workflow — Worktree hygiene 慣例索引

Loaded on demand by [`skills/git-workflow/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/SKILL.md) — 開／清 worktree，或委派任務後 git 狀態看起來奇怪時讀。
本檔內文原樣自 SKILL.md 搬出。

## Worktree hygiene (references)

Fourteen conventions for worktree lifecycle and git-attribution — worktree
layout naming, when to open a separate worktree for a pre-existing issue,
deferring colliding work, batch cleanup safety, squash-merge-aware "already
merged" checks, and not over-attributing surprising git state
(commits/rebases/wrong commit subject) to a rogue agent when it's more likely
the user working in parallel or an unverified delegate report. Details and
recipes in `references/worktree-hygiene.md`:

- **Worktree layout** — worktrees live nested under the main worktree's own
  `.worktrees/<topic>` (branch `<topic>`), matching the same path template a
  personal worktree manager (e.g. worktrunk) already uses for the repo. Don't
  open one with the harness's built-in `EnterWorktree` (it creates a locked
  `.claude/worktrees/<name>` on branch `worktree-<name>`); use
  `git worktree add`. Command and fix-up recipe in
  `references/worktree-hygiene.md`.
- **Start a task in its own worktree from the outset, not midway** — a
  mid-task switch costs more than staying (untracked files don't follow a
  branch switch, running agents get interrupted); correct on the *next* task.
- **Work already finished in the shared tree, user wants it committed from a
  worktree** — move it, don't redo it: save `git diff HEAD` as a patch (not
  `--cached`: a failed commit hook resets the index, leaving it empty) and
  record `shasum -a 256` of each file; `worktree_path.py` for the path, then
  `git worktree add -b <topic> <path> <remote>/main`; in the worktree
  `git apply --check`, apply, and commit only when the hashes match file for
  file; then in the original tree `git restore` those files, switch back, and
  delete the temporary branch. Untracked new files never appear in
  `git diff HEAD` and need copying separately (inferred from git's behaviour,
  not exercised in the session that added this entry).
- **`ListAgents` before touching the git index** on a shared checkout — a
  peer session can be on the same checkout/branch with zero mutual awareness,
  and `git status` alone won't reveal it.
- **Pre-existing fix → new worktree off upstream/main**, not folded into the
  current feature branch (proportionality counter-case for trivial diffs).
- **Colliding work gets deferred** — when approved work overlaps an
  in-flight branch's files, do the non-colliding subset now and defer the
  rest, rather than forcing everything through and creating merge conflicts.
- **Batch cleanup**: show the exact command list before running; don't chain
  many worktree/branch ops in one shell call (timeout risk).
- **Squash-merge "already merged" check** needs `gh search prs`, not
  `git branch --merged` (squash breaks ancestry).
- **Don't over-attribute unexpected git state to a rogue agent** — verify
  quietly (reflog, staged files) before alarming; on a delegated task, verify
  git state (reflog/log/status) before committing on top of it.
- **Verify the landed commit subject** with `git log --oneline -1` after every
  commit — don't trust the tool's echoed command string.
- **"Fix the commit message" on a tmp/mislabeled branch** means squash the
  whole branch into one commit, not reword just the tip.

Read `references/worktree-hygiene.md` when opening/cleaning up worktrees or
when git history looks surprising after a delegated task.
