# Git Workflow — Worktree Automation (`--worktree` flag)

Loaded on demand by `skills/git-workflow/SKILL.md` — **how the `--worktree` opt-in
flag on `/maigo:go` and `/maigo:take-issue` actually opens a sibling worktree, and
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
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/worktree_path.py" --repo <name> --topic "<任務描述或 issue 標題>"
git worktree add -b <branch> <path> <remote>/<default-branch>
```

- **Fetch first, always.** Cutting a worktree from a stale local tracking ref
  risks branching off a commit the remote has already moved past. `<remote>`
  resolution: try `upstream` first, fall back to `origin` — mirrors the
  sibling-layout convention in
  [`references/worktree-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-hygiene.md).
- `scripts/worktree_path.py` is a pure function — it only computes the sibling
  path and branch name (reusing `slugify()` from `scripts/artifact_path.py`,
  same rules as artifact identifiers). It does **not** run any git subprocess
  or create anything; the actual `git worktree add` is the orchestrator's own
  step, right after.
- Once the worktree exists, **every delegate prompt for the rest of that task**
  (🐱 樂奈 / 🩵 燈 / 🎀 愛音 / 🟡 爽世 / 🟣 立希) must carry that worktree's
  absolute path as its explicit cwd — see
  [`skills/teammate-flow/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)'s
  cwd-repetition rule for why "the previous agent already said it" isn't
  enough (five independent agent contexts, no implicit inheritance).
- At hand-off (🟣 立希 all-green, commit drafted), the orchestrator prints the
  worktree's path and branch, and says explicitly: it's left in place, and
  `/maigo:repo-audit`'s new "已合併可清的 sibling worktree" section (see
  `commands/repo-audit.md`) will surface it as a cleanup candidate once its PR
  merges. **The worktree is never removed automatically here.**

## 2. `.maigo/` ownership inside a worktree task

Two different things live under `.maigo/`, and they have **opposite**
locality rules:

| What | Where it lives | Why |
|------|----------------|-----|
| Single-task temporary artifacts (`plan-<id>.md`, `review-rubric-<id>.md`, `review-<id>.md`, `triage-rubric-<id>.md`, `pr-comments-<id>.md`) | The **worktree's own** `.maigo/` | `artifact_path.py`'s `resolve_identifier()` derives the identifier from cwd's current git branch. cwd inside the worktree naturally resolves to the worktree's own branch slug — no code change needed, it just falls out of the existing four-tier identifier chain. |
| Work Board (`.maigo/board.md` and `.maigo/i/*.md`) | **Always the main checkout**, never a worktree | The board is a cross-session, cross-task single source of truth — it doesn't make sense duplicated per worktree. |

When a command running inside a worktree needs to read or write the board, it
must first resolve the shared main checkout root — never assume cwd is it:

```bash
git rev-parse --path-format=absolute --git-common-dir
```

The parent directory of that path is the main checkout root; all board reads
and writes go there, not to cwd.

## 3. This rule survives the cross-repo rewrite unchanged

The "board only lives in the main checkout" rule above predates this plan's
cross-repo scope, and stays exactly as written — the cross-repo board index
(`scripts/board_index.py`, see `docs/reference/artifacts.md`) is a *different*
layer (it reads each repo's own main-checkout `board.md` across many repos);
worktree-vs-main-checkout locality within a single repo is orthogonal to it.

**One thing to watch when building `~/.config/maigo/repos.txt`**: every entry
must be a repo's **main checkout** path, never a sibling worktree path. A
worktree has no board of its own — scanning one either hits the same board
file shared via the common `.git` dir, or hits nothing (the board file only
physically exists under the main checkout directory).
