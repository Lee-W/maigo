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

Default to one commit per logical concern, and branch before the first
commit the user will actually test — don't land straight on main. See
[`references/commit-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/commit-hygiene.md#staging-discipline-one-commit-per-concern-branch-before-its-testable).

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

This matters most in multi-worktree setups, where several worktrees off the
same repo exist at once and it's easy to accidentally run a command against
the wrong one after a `cd`.

## Commit assembly (amend vs. new commit vs. which branch)

`--amend` only ever operates on HEAD — briefing an amend target needs a HEAD
check baked in, not just a hash. See
[`references/commit-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/commit-hygiene.md#amend-target-must-be-head).

### Fold polish / tangled hunks / fix on the surfacing branch

- 尚未 release 的 introducing commit：review 帶來的 polish（rename、docstring、perf nit、補測試）預設 `--amend` 進該 commit，不另開 follow-up；只有真正獨立、或 commit 已在 PR 被 review 中才另開。
- 多條 review thread 同時重塑同一個函式／迴圈時，amend 進**最新的 tip**，不要手工重建從未存在過的中間態。偏離 split-amend 計畫時要明講。
- 由 in-flight branch 自己引出的 lint／type／test 失敗，修在**那條 branch**，不是從 main 另切新 branch。

[`references/commit-assembly-details.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/commit-assembly-details.md)（理由與 How to apply 全文，決定落點時讀）

### Referencing private-layer files: path only, never content

Public-repo commit messages, PR bodies, and file contents may cite a
private-layer file by its **path** (e.g. `~/.claude/rules/model-dispatch.md`)
but must not copy or excerpt its **content** — including quoting its
judgment/rule text verbatim. When the semantics need conveying, summarize in
one sentence instead of reproducing the source.

## Sizing a diff

Editing a single JSON field (a version bump) should stay a 1-line diff — use
precise string replacement, not a full `json.load`/`json.dump` re-serialize.
See
[`references/commit-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/commit-hygiene.md#edit-a-json-field-with-precise-replacement-not-full-re-serialize).

### Diff baselines

- 量化改動規模（「刪掉什麼」「diff 多大」）前先確認真正的 merge-target 基準：`git diff upstream/main..HEAD`、`git show upstream/main:<file>`，不要拿 branch tip 當基準。
- 列舉「這個 diff 新增了哪些行」（命名列舉、洩漏掃描）一律用 `git merge-base <base> HEAD` 或三點式 `git diff <base>...HEAD`，**不用兩點式**——本地 base 前進後兩點式會混進別人的 commit，產生看起來正常的假陽性。

[`references/diff-baselines.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/diff-baselines.md)（理由、驗證步驟與案例，陳述 diff 規模或列舉新增行前讀）

## Pushing and opening a PR

**A widget selection is not authorization to open a PR.** Never run `gh pr create`
(including `gh pr create --web`, which only opens a pre-filled browser tab) unless
the user explicitly asks for it in the current turn. Picking a multi-choice option
like "Commit and open PR" from an AskUserQuestion-style widget is ambiguous for the
PR-creation half specifically — confirm once more (plain text is fine) immediately
before calling `gh pr create`. After committing and pushing a branch, default to
stopping there: report the branch/compare URL and ask if a PR should be opened.

**Outward git/GitHub operations are the user's to run, not just PR creation.**
- **`git commit` is authorized; pushing is not.** Once verification is green, commit directly on the branch (never `SKIP=`, never `git add -A`) and report the hash and `--stat` — don't stop at "here's the command, paste it yourself".
- Everything outward stays drafted-and-stopped — never auto-run `git push` / `--force-with-lease` / `gh pr create` / `gh issue create` unless the user explicitly asks this turn.
- A "Recommended" pick inside a batch `AskUserQuestion` is not authorization to open an issue — show the draft, wait for "post this".
- Fixing an already-pushed branch: commit/amend locally and stop; mention `--force-with-lease` but neither run it nor frame it as the recommended next step. Case studies: `references/outward-ops-authority.md`.
- Commits go on a feature branch, not `main`; if they already landed there, rescue them as in `references/outward-ops-authority.md` "Commit on a feature branch".
- Rebasing a branch that contains merge commits, or onto an advanced base: see `references/commit-hygiene.md` "Rebase correctness".

## Worktree hygiene (references)

worktree 慣例（layout 放 `.worktrees/<topic>`、不用 harness 內建 `EnterWorktree`、任務一開始就在自己的 worktree、`ListAgents` 先於動 git index、已完成的工作移進 worktree 的搬法、批次清理先列指令、squash-merge 的「已合併」檢查用 `gh search prs`、不要把意外 git 狀態先歸咎於 rogue agent、commit 後用 `git log --oneline -1` 驗 subject）：
[`references/worktree-hygiene-index.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-hygiene-index.md)（慣例摘要）
；完整配方在 [`references/worktree-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-hygiene.md)，開／清 worktree 或委派後 git 歷史看起來奇怪時讀。

### Worktree automation (`--worktree` flag)

How `/maigo:go` / `/maigo:take-issue`'s opt-in `--worktree` flag actually opens
a nested worktree, and where `.maigo/` artifacts written during that task
belong (per-task artifacts vs. the Work Board, which only ever lives in the
main checkout). Details in
[`references/worktree-automation.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-automation.md).

## Shared worktree state volatility (references)

A shared worktree's branch, commits, or push/PR state can change from
something other than the current session — in both directions (external
revert/rebase/deletion *and* external forward progress) — so re-verify live
before restating a status claim, reusing a cached base ref, or running a
destructive reset. Recovery recipes, base-ref staleness, and CI/changelog
proxy traps in
[`references/shared-worktree-state.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/shared-worktree-state.md).
The same file covers a mid-rebase Stop-hook red that is only an intermediate
commit, and where `isolation: "worktree"` places a worktree when the caller is
already in one.

## Hook runner false greens (references)

When a `pre-commit` / `prek` run reports `exit 0` but may have checked nothing —
unstaged changes stashed away, `git add -N`, `git rebase --continue` running no
hooks, a hook's `files:` regex that never matches, a corrupted prek toolchain
cache, reproducing from the wrong directory, or building a new hook — read
[`references/hook-runner-verification.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/hook-runner-verification.md).

## What this skill does NOT cover

- Drafting the commit message text itself — see
  [`commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md).
- Deciding *whether* to commit at all, or when in a flow the commit happens
  (e.g. after Soyo + Taki pass) — that's the calling command's own policy.
- Drafting the PR title / description content itself — separate skill
  ([`github-title-description`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/SKILL.md)).
  This skill only governs *when* it's okay to actually run `gh pr create`
  (see "Pushing and opening a PR" above).
