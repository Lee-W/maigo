# Work Board — Upsert Discipline Reference

Loaded on demand by `skills/work-board/SKILL.md` §3 — **four easy-to-miss
upsert habits**: keeping the header's "最後刷新" date honest even on a
single-item upsert, treating the board upsert as its own independent step
outside the four-teammate pipeline, not confusing a board verdict label
with proof the review actually reached GitHub, and never rewriting an existing
board without a lock (Claude: `Edit`, never `Write`; the refresh script:
compare-and-swap).

---

## Single-item upsert still updates the header's 最後刷新 date

Writing `.maigo/board.md` for even **one** item (not a full re-scan of every
other row) still means the header line's 最後刷新 date changes to today.
Don't leave it stale out of a fear of misrepresenting the refresh scope —
that fear produces the opposite problem: a stale header nobody trusts.

Update the section bucket counts you touched at the same time. If the
header's total count already disagreed with a section title's own count
before this upsert (e.g. `🎯 38` vs `## 🎯 下一件（36）`), that's pre-existing
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

If empty and the user has not explicitly marked this report read, keep it at
`待送出`. An explicit `--reviewed` acknowledgement may move it to `已看完` locally;
it is never evidence of GitHub submission. Refresh from the report metadata and
current PR head, not only the old board status. Distinguish a maintainer's own official verdict (someone else's
`CHANGES_REQUESTED`, which genuinely is posted) from your own unposted
draft — only the latter needs this check.

---

## Never rewrite an existing board without a lock

`.maigo/board.md` is deliberately **one file shared across every session** —
it has no task identifier in its name, because a per-task board would defeat
the point of a single cross-session view. That makes it the one artifact where
two sessions genuinely do write to the same path at the same time.

A whole-file `Write` rebuilt from a snapshot you read some turns ago silently
discards everything another session wrote in between. Nothing errors; the rows
are simply gone, and `.maigo/` is gitignored so there is no version to recover.

**How to apply — two kinds of writer, same goal (a concurrent change must be
loud, never silently overwritten):**

*Claude* (the delegate commands' upsert and `/maigo:board`'s manual fallback):

- **`Edit`, never `Write`, on a board that already exists.** `Edit`'s
  `old_string` acts as an optimistic lock: if another session changed that
  line, the edit *fails* instead of overwriting. Reserve `Write` for creating
  the skeleton when the file does not exist yet.
- **Re-read immediately before writing.** Content you read earlier in the
  session is not evidence of the current file.
- **On `Edit` failure: re-read, recompute that row, retry.** Do not fall back
  to `Write` to force it through — the failure is the mechanism working.

*The refresh script* (`board_sync.py refresh --apply`) does rewrite the whole
file, so it takes a compare-and-swap instead of `Edit`'s `old_string`: it hashes
what it read, re-checks the hash before acking and again right before writing,
backs up to `.maigo/_internal/board/backup/`, then writes atomically (tmp +
rename). If the board (or a detail file it is about to change) moved underneath
it, it stops with **exit 2** and writes no board or detail file (the only thing
that may already be written is the `review.md` ack mark, because the ack happens
between the two hash checks). The fix for exit 2 is to **re-run**, not to fall
back to `Write`. Exit 3 means a write failed: before the board was written it is
rolled back from the backup; if only the ledger or snapshot failed afterwards,
nothing is rolled back and the board is already the new version.

The same applies to `.maigo/i/<slug>.md`: its fact section is rewritten
wholesale on every refresh, so re-read immediately before rewriting to avoid
clobbering a concurrent update to the hand-written `## 判斷` / `## 筆記`.

### Machine state under `.maigo/_internal/board/`

`dropped.jsonl` (the exclusion ledger) and `snapshot.json` (last refresh's board
rows and checkbox state) are owned by `scripts/board_sync.py` and nobody else:
the ledger is **append-only** (one line per event, never rewritten) and the
snapshot is written **atomically** (tempfile + replace). `backup/` holds the
copies `refresh --apply` takes before it writes. Do not `Write` or `Edit`
anything under `_internal/`. `plan` / `ack` / `drop` / `revive` / `snapshot`
never write `board.md` or `i/*.md`; they only report changes for you to apply
with `Edit`. Only `refresh --apply` writes them, under the compare-and-swap
above.

A detail file with no board row that references it means the user deleted the
row (`dd`), so the script records a drop. But a delegate command writes the
detail file *before* it `Edit`s the row in, so a plan that lands between the two
steps would misread a fresh file as a deletion. That is why orphans younger than
10 minutes are only reported as `pending_orphans` and not judged until a later
refresh. See `skills/work-board` §3a.
