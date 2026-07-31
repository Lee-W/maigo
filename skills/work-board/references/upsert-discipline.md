# Work Board — Upsert Discipline Reference

Loaded on demand by `skills/work-board/SKILL.md` §3 — **three easy-to-miss
upsert habits**: keeping the header's "最後刷新" date honest even on a
single-item upsert, treating the board upsert as its own independent step
outside the four-teammate pipeline, and not confusing a board verdict label
with proof the review actually reached GitHub.

---

## Single-item upsert still updates the header's 最後刷新 date

Writing `.maigo/board.md` for even **one** item (not a full re-scan of every
other row) still means the header line's 最後刷新 date changes to today.
Don't leave it stale out of a fear of misrepresenting the refresh scope —
that fear produces the opposite problem: a stale header nobody trusts.

Update the section bucket counts you touched at the same time. If the
header's total count already disagreed with a section title's own count
before this upsert (e.g. `🎯 38` vs `## 🎯 你的球（36）`), that's pre-existing
drift outside the scope of a single-item upsert — don't "fix" it as a side
effect; only touch the bucket you actually changed.

## Board upsert is not part of the four-teammate pipeline — check it independently

`/maigo:review`'s (and similarly `/maigo:triage-issue`'s,
`/maigo:take-issue`'s) board upsert step is **not** one of Raana / Tomori /
Soyo / Taki's four stages, so it's easy to finish a full pipeline run, emit
a complete report, and still have forgotten to write `.maigo/board.md`.

**How to apply:** after every report emitted (not just at the end of a
batch), independently confirm `.maigo/board.md` has been upserted for that
item before moving to the next one — don't treat "pipeline finished" as
proof the board write happened.

## A board verdict is not proof the review reached GitHub

A verdict label on the work board (`REQUEST_CHANGES` / `NEEDS_CHANGES` /
`APPROVE`) only means the review was **decided locally** — it does not mean
it was posted. Local review analysis frequently sits finished in a report
file without ever being submitted to the PR.

**How to apply:** before treating a board verdict as delivered — or judging
whose ball an item is — verify with:

```bash
gh api repos/<owner>/<repo>/pulls/<n>/reviews --jq '.[] | select(.user.login=="<you>")'
```

If empty, the ball is still yours to *post*; note it as "待
review（本地分析從未貼上 GitHub）" rather than treating the local verdict as
done. Distinguish a maintainer's own official verdict (someone else's
`CHANGES_REQUESTED`, which genuinely is posted) from your own unposted
draft — only the latter needs this check.
