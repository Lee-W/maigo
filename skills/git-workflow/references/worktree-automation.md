# Git Workflow — Worktree Automation (`--worktree` flag)

Loaded on demand by `skills/git-workflow/SKILL.md` — **how the `--worktree` opt-in
flag on `/maigo:go` and `/maigo:take-issue` actually opens a nested worktree, and
where `.maigo/` artifacts written during that task belong.** Read this before
briefing an agent that will operate inside a freshly-opened worktree, or when
deciding whether a `.maigo/` write during a worktree task should land in the
worktree or the main checkout.

---

## 1. How `--worktree` wires up

`/maigo:go` and `/maigo:take-issue` each accept an optional `--worktree` flag
(opt-in, off by default). When present, **before** 🐱 樂奈 starts, the
orchestrator itself (not a delegated agent) runs:

```bash
git fetch <remote>
root="$(git worktree list --porcelain | head -1 | sed 's/^worktree //')"
git -C "$root" check-ignore -q .worktrees/probe || echo "not ignored — see pre-flight check below"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/worktree_path.py" --topic "<任務描述或 issue 標題>" --cwd "$root"
git worktree add -b <branch> <path> <remote>/<default-branch>
```

- **Fetch first, always.** Cutting a worktree from a stale local tracking ref
  risks branching off a commit the remote has already moved past. `<remote>`
  resolution: try `upstream` first, fall back to `origin` — mirrors the
  layout convention in
  [`references/worktree-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-hygiene.md).
- `scripts/worktree_path.py` is a pure function — it only computes the nested
  path (`<root>/.worktrees/<slug>`) and branch name (reusing `slugify()` from
  `scripts/artifact_path.py`, same rules as artifact identifiers). It does
  **not** run any git subprocess or create anything; the actual `git worktree
  add` is the orchestrator's own step, right after. `--cwd` must be the
  **main worktree's root directory** (`$root` above via `git worktree list
  --porcelain`, not `.`) — see `worktree-hygiene.md`'s layout section for why.

## 1a. Pre-flight check: is `.worktrees/` excluded in the target repo?

Before running `git worktree add`, check whether the target repo already
excludes `.worktrees/` from git:

```bash
git -C "$root" check-ignore -q .worktrees/probe
```

Exit `0` means it's already excluded (via the repo's own `.gitignore`,
`$(git rev-parse --git-dir)/info/exclude`, or a global `core.excludesfile` —
any of the three counts). If it exits non-zero, **stop and remind the user**
rather than proceeding silently — maigo does not write the target repo's
ignore configuration for it. Present the three options and let them choose:

1. Add `.worktrees/` to the repo's own `.gitignore` (shared with collaborators).
2. Add it to `$(git rev-parse --git-dir)/info/exclude` (local-only, not committed).
3. Add it to a global `core.excludesfile` (applies across all repos on this machine).
- Once the worktree exists, **every delegate prompt for the rest of that task**
  (🐱 樂奈 / 🩵 燈 / 🎀 愛音 / 🟡 爽世 / 🟣 立希) must carry that worktree's
  absolute path as its explicit cwd — see
  [`skills/teammate-flow/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)'s
  cwd-repetition rule for why "the previous agent already said it" isn't
  enough (five independent agent contexts, no implicit inheritance).
- At hand-off (🟣 立希 all-green, commit drafted), the orchestrator prints the
  worktree's path and branch, and says explicitly: it's left in place, and
  `/maigo:repo-audit`'s "已合併可清的 worktree（不限佈局）" section (see
  `commands/repo-audit.md`) will surface it as a cleanup candidate once its PR
  merges. **The worktree is never removed automatically here.**

## 2. `.maigo/` ownership inside a worktree task

Every worktree's `.maigo` is a symlink to **one per-repo state root**, so every `.maigo/`
artifact, wherever the command runs, lands in the same place. A worktree must not have a physical
`.maigo/` directory of its own. Storage layout, repo identity and the `link` / `migrate`
commands: [`docs/reference/state-storage.md`](https://github.com/Lee-W/maigo/blob/main/docs/reference/state-storage.md).

| What | Where it lives | Why |
|------|----------------|-----|
| All task artifacts: `pr/<id>/plan.md` / `issue/<id>/plan.md` / `topic/<slug>/plan.md`, `review/<id>/{review,rubric,draft,inline-comments,pr-comments,reply-draft}.md` (or `pr/<id>/…` for your own PR), `issue/<id>/rubric.md` | The shared state root, reached through the worktree's `.maigo` symlink | Review artifacts always belong in the repo-level `.maigo`: the Work Board and other sessions look for reviews there, never in a per-worktree copy. `artifact_path.py`'s `resolve_identifier()` still derives the identifier from cwd's current git branch (on a default branch a plan uses `--slug` / the H1 slug instead), but the *location* no longer depends on which worktree cwd is in. |
| Work Board (`.maigo/board.md` and `.maigo/i/*.md`) | The same state root; one board per repo | The board is a cross-session, cross-task single source of truth — it doesn't make sense duplicated per worktree. |

If a worktree turns out to hold a **physical** `.maigo/` directory (an older worktree created
before the state root existed), its artifacts are invisible to the board and to other worktrees.
Migrate it instead of working around it: run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state.py" migrate [--cwd DIR]` (dry-run by default,
`--apply` to perform it). To fix a review artifact that was written to a stray physical directory,
move it into the state root only after confirming the target does not already exist.

When a command running inside a worktree needs to read or write the board and the worktree's
`.maigo` is not a symlink (not yet migrated), it must first resolve the shared main checkout
root — never assume cwd is it:

```bash
git rev-parse --path-format=absolute --git-common-dir
```

The parent directory of that path is the main checkout root; all board reads
and writes go there, not to cwd.

## 3. This rule survives the cross-repo rewrite unchanged

(The "board only lives in the main checkout" wording below applies to worktrees that have not been migrated to the state-root symlink; migrated worktrees share the one board through `.maigo`.)

The "board only lives in the main checkout" rule above predates this plan's
cross-repo scope, and stays exactly as written — the cross-repo board index
(`scripts/board_index.py`, see `docs/reference/artifacts.md`) is a *different*
layer (it reads each repo's own main-checkout `board.md` across many repos);
worktree-vs-main-checkout locality within a single repo is orthogonal to it.

**One thing to watch when building `~/.config/maigo/repos.txt`**: every entry
must be a repo's **main checkout** path, never a worktree path. A
worktree has no board of its own — scanning one either hits the same board
file shared via the common `.git` dir, or hits nothing (the board file only
physically exists under the main checkout directory).
