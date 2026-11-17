# Git Workflow — Diff 基準線

Loaded on demand by [`skills/git-workflow/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/SKILL.md) — 要陳述 diff 大小、「刪掉什麼」、或列舉「這個 diff 新增了哪些行」時讀。
本檔內文原樣自 SKILL.md 搬出。

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
see "Fold polish into the unreleased introducing commit" in `commit-assembly-details.md`).

How to apply: before stating diff sizes or "what gets removed", run
`git rev-list --count upstream/main..HEAD` and check whether the code being
"deleted" actually exists on the merge target
(`git show upstream/main:<file> | grep <symbol>`). If the branch carries
unmerged feature commits, the honest comparison is "reworked commit vs.
current commit" (an amend), not "vs. the merge target". Verify empirically
against `git show`/`git diff` output — don't assert sizing from memory of
the working tree.

### Enumerate "new lines" from a merge-base baseline, not a two-dot diff

When the judgment is "which lines did *this* diff add" — naming
enumeration, "is this symbol new in this PR", scanning for a private/secret
token that must not leak — the baseline must be `git merge-base <base> HEAD`
or the three-dot form `git diff <base>...HEAD`. Do not use the two-dot form
`git diff <base>`.

Why: a two-dot diff compares two commits directly. If the local `<base>` ref
has advanced past the point this branch actually forked from (someone else
pushed to it, or it's a shared/moving ref like `main` in a long-lived
worktree), the two-dot diff mixes in **every commit that landed on `<base>`
since the fork point** — changes nobody on this branch wrote. Enumerating
"new" defs, symbols, or added lines against that diff produces false
positives that look identical to real ones: no error, a plausible-looking
line number, a name that reads like it could be new.

How to apply: `git merge-base <base> HEAD` first, then diff from that SHA
(`git diff <merge-base-sha>...HEAD` or equivalently the three-dot form
against `<base>` directly) before treating any line as "added by this
branch." This applies wherever "diff 新增行" is the judgment basis — see the
naming-enumeration and change-site-enumeration uses of this pattern in
[`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)
and
[`change-site-enumeration`](https://github.com/Lee-W/maigo/blob/main/skills/change-site-enumeration/SKILL.md).

Case: a review's naming-enumeration pass ran a two-dot diff against a local
`main` that had moved ahead; the diff pulled in an unrelated commit that
had touched `sandbox/modal.py`, and two of that commit's pre-existing names
got flagged as naming violations introduced by the branch under review —
neither line was written by that branch.
