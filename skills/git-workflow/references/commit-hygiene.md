# Git Workflow — Commit Hygiene

Loaded on demand by [`skills/git-workflow/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/SKILL.md) —
mechanics for picking a correct amend target, keeping JSON-field edits
diff-clean, and staging/branching discipline when landing multiple changes.
Read this file when amending a commit, editing a single JSON config field, or
deciding how to stage and branch a batch of changes.

---

## Amend target must be HEAD

`git commit --amend` only ever operates on **HEAD**. When briefing a delegate
(or yourself) to "amend change X into commit `<sha>`", the instruction must
include a HEAD check — not just the target hash — because if `<sha>` isn't
actually HEAD, following the instruction literally amends the wrong commit.

Why: a delegate was once briefed to "amend `<sha>`" while HEAD was actually a
different commit (a second cherry-pick had landed on top after the brief was
written). The delegate amended the wrong commit on the first attempt — it
followed the literal instruction, which was itself stale relative to the
actual repo state. Recovery required `reset --hard` back to the target,
re-editing, amending, and re-applying the commit that had landed on top. An
instruction that contradicts the actual repo state makes "doing what was
said" amplify the error rather than catch it.

How to apply: brief `--amend` in two steps, never just a target hash:

1. `git log --oneline -3` to confirm the target commit is actually HEAD.
2. If yes → amend directly. If no → stop and report (or give explicit
   `reset`/`rebase` steps) rather than letting the delegate invent a fix on
   the spot.

The hash/state a plan or brief was written against can go stale by execution
time — the instruction should carry its own on-the-spot verification, not
assume the world hasn't moved.

## Edit a JSON field with precise replacement, not full re-serialize

To change a single field in an existing JSON file (a version bump, a flag
flip), use **precise string replacement** (`sed`, or an editor's exact-match
replace) targeting the old value — do not `json.load()` the whole file,
mutate the value, and `json.dump()` it back out.

Why: re-serializing a full JSON document commonly reformats parts you didn't
intend to touch — arrays get expanded onto multiple lines, Unicode escapes
get rewritten to raw UTF-8 (or vice versa). A version bump that should be a
1-line diff turns into a double-digit-line diff, and the real change (the
version string) gets buried in formatting noise a reviewer has to wade
through.

How to apply: after any such edit, run `git diff --stat` and confirm the
change touches only the intended field. If the diff shows unrelated
reformatting, revert and redo it as a targeted string replacement instead.
Reach for full re-serialization only when the file is newly created, or the
task genuinely is "reformat this file."

## Staging discipline: one commit per concern, branch before it's testable

Two related defaults when landing a batch of unreleased changes:

**Stage and commit per logical concern**, not one giant commit for
everything. When a session produces multiple independent changes, split
staging by concern (`git add` each concern's files separately) and commit
each with a message focused on that concern — don't `git add -A` everything
into one commit. Per-concern commits keep history readable, let each change
be reverted or reviewed independently, and map cleanly onto separate review
threads.

Why: in one session that produced several independent fixes, the user
explicitly asked for them to be committed separately rather than swept into
one commit — the request itself is the evidence this default should exist,
not just a general best-practice preference.

Splitting by concern only holds if each concern's files actually made it into
the index — `git status --short` isn't proof of that. A leading-space ` A`
(space, then `A`) in its first column means **intent-to-add**: the path is
known to the index but its content is not, typically left behind by a stray
`git add -N` or by a delegate/tool creating a new file. Committing at that
point succeeds and silently produces an empty file — `git status` never
flags it. The authoritative check before committing is `git diff --cached
--numstat` on every path in the batch: real staged content lists as
`<added>\t<deleted>\t<path>`; an intent-to-add path is simply absent from
that output, and that absence is the signal, not an error message. Fix with
`git add <path>` again, re-check `--numstat`, then commit; confirm the total
afterwards with `git show --stat`.

**Open a branch before the first commit the user will actually test**, don't
land straight on the main/default branch. Once a batch of unreleased changes
is about to be exercised by the user (especially anything they'll run and
click through, not just read), cut a descriptively-named feature branch
first, then commit there. Only fold back into the main branch after the user
confirms the batch is good.

Why: after a session accumulated several unreleased fixes the user was about
to try out themselves, the user's own instruction was to branch first and
commit there — not straight onto the default branch — specifically because
they were about to test it before deciding whether it should land.

These are different axes — one governs *how finely* to slice commits, the
other governs *which ref* they land on — and can both apply to the same batch
of work: branch first, then commit per-concern on that branch.

How to apply: before committing a multi-concern batch, default to splitting
staging by concern; before the first commit of a batch the user hasn't tested
yet, default to `git checkout -b <descriptive-branch-name>` first. Use the
repo's own commit-message convention for each per-concern commit (see
[`commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md)).

## Repo `CLAUDE.md`/`AGENTS.md` attribution rules win over harness defaults

A harness's session layer commonly carries a default instruction to append a
co-author trailer (e.g. `Co-Authored-By: <agent> <noreply@...>`) to every
commit message. When the target repo's own `CLAUDE.md` / `AGENTS.md`
explicitly forbids this — e.g. apache/airflow: "NEVER add Co-Authored-By
with yourself as co-author of the commit. Agents cannot be authors, humans
can be, Agents are assistants." — the repo's rule wins: drop the trailer,
and don't re-litigate or report on it every time.

Why: these commits go into the project's permanent history, under its own
maintainers' own contribution conventions — a harness-layer default has no
standing there. The conflict recurs on every session against that repo;
re-deciding and re-reporting it each time is pure overhead once the repo's
position is known.

How to apply:

- Before writing a commit message, check whether the target repo's
  `CLAUDE.md`/`AGENTS.md` has an attribution clause. If it forbids agent
  co-authorship, comply silently — no trailer, no comment about it.
- PR **description** disclosure is a separate axis: a repo can still require
  its own AI-disclosure format there (a checkbox plus a `Generated-by:`
  line) even while forbidding a commit-message co-author trailer — give the
  repo what it asks for in each place.
- Repos with no such clause **do not** fall back to the harness's own trailer
  default: maigo's own default for the co-author trailer is unconditional —
  never add one, clause or no clause, harness default or not (see
  [`commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md)'s
  `## Trailers` section). "Follow the harness's own attribution default when a
  repo is silent" applies only to attribution conventions *other than* the
  trailer — e.g. a PR description's disclosure format.

The point that matters is which source of truth wins — repo docs over a
harness or session-level default — not the location either one lives in.

## Splitting one working tree into multiple PRs needs a standalone test run per side

When splitting one batch of changes into two (or more) PRs, an empty
file-list intersection between the diffs is not evidence of independence —
it only proves the two diffs won't conflict on the same tree. The question
that actually matters is whether each half, applied standalone to the base
branch, passes its own tests, and that's unrelated to file overlap: one
half's code can read a field the other half only just added to a schema, a
test fixture can reference something the other half introduced, an import
can point at a module that doesn't exist without the other half.

**Verify both directions, from a clean base**:

1. Save the second half as a patch (`git diff HEAD -- <second-half-paths> >
   <patch-path>`) and note its checksum.
2. Stage and commit the first half in the original worktree, per concern —
   not `git add -A`.
3. From a **fresh worktree cut off the remote default branch** (not off the
   first half's branch), `git apply` the second half's patch and run its own
   tests there — this is the actual independence evidence.
4. **Run the reverse too**: back in the original worktree, revert the second
   half (`git checkout --` is safe here — its content already lives in the
   patch and in the new worktree's commit) and re-run the first half's own
   tests.

Why step 4 isn't optional: the pre-split verification ran with both halves
present on the tree at once, which cannot prove either half independently.
Only once both directions pass can each PR be called independently
reviewable — "the files don't overlap" was never that proof.

One more thing to check rather than assume when cutting the fresh worktree:
its remote tracking ref may have moved since an earlier worktree in the same
session last fetched it, so the two branches' bases can differ. Confirm with
`git merge-base --is-ancestor <old-base> <remote>/main` and report it — don't
assume the bases match.

## After `rebase --continue` / `cherry-pick`: a shrinking file count means the message is now stale

After `git rebase --continue` or `cherry-pick` finishes, **reconcile `git
show --stat`'s file count against the original commit's before trusting the
result**. A smaller count means upstream already carried out part of that
change itself, and git silently dropped the now-already-applied hunks —
there is no warning, only a file/line count that no longer matches.

Why: a rebase of a commit describing four kinds of edits (a connection-form
placeholder, a hook docstring, `get_provider_info.py`, and a test) landed as
a single-file diff (test only) because upstream had already merged a PR
that made the other three edits. The commit message still described all
four — a message describing changes absent from the diff misleads both the
reviewer reading the PR and anyone reading `git log` afterward.

How to apply, in order:

1. `git show --stat HEAD` and compare the file count to the pre-rebase
   commit.
2. If it shrank, `git show HEAD` and read the actual remaining diff to
   determine what content is genuinely left.
3. If the message no longer matches the diff, `--amend` it — rewrite the
   subject for the remaining scope's user impact, and note in the body why
   only this much survived (name the upstream PR that already absorbed the
   rest, if known).

The same check applies mid-conflict-resolution, not just after `--continue`:
a hunk in a non-conflicting region that "is already correct" is often
upstream having done it first, not your hunk having applied cleanly.

## Rebase conflict resolution can replace an earlier commit's changelog note

A conflict resolution can **replace** instead of **append**. When several commits each add a
`.. note::` to the same provider changelog section, a hand-resolved rebase conflict easily writes
the later commit's note as a replacement of the earlier one: the earlier note vanishes, the diff
reads like a rewording, and tests and prek stay green — no signal at all. Case (apache/airflow
#72149): one commit added a note that a deferred timeout now raises `OpenAIBatchTimeout`; the next
commit's conflict resolution swapped it for a "deferred timeout cancels the batch" note. A reviewer
caught it a round later, and the dropped text was the most compatibility-breaking part
(`OpenAIBatchTimeout` is not a subclass of `OpenAIBatchJobException`).

How to apply: after any rebase with conflicts, run `git show <c> -- <changelog>` for each commit
that touched the changelog and confirm each diff is pure additions (`+`), not a previous commit's
`+` lines turned into `-`. Also check placement: if that version has already been cut as an rc,
the note belongs above the version heading (precedent: `providers/keycloak/docs/changelog.rst`).

## A conflict-free cherry-pick onto a branch that changed the same logic still needs a test run

When moving a follow-up commit onto a branch that later changed the same logic, `git merge-tree`
exiting 0 only proves the **text** doesn't conflict, not that the semantics are compatible. Case:
a test fixture title from commit C2 stopped being accepted once W1 added a `$` anchor to the
matching pattern; `merge-tree` was clean and the cherry-picked test went red. Run the full test
suite after the move before saying it can be merged; until then the most you may claim is "no
textual conflict".

## Prove a rebase lost nothing with a delta-of-deltas

To claim after a rebase that "no hunk was lost or altered", the only strong evidence is comparing
the two deltas (old base → old tip vs. new base → new tip):

```sh
OLD_BASE=$(git merge-base <old tip> <new base>)
git diff $OLD_BASE <old tip> -- <dirs this branch touched> > before.diff
git diff <new base> <new tip> -- <same dirs>              > after.diff
diff <(grep -vE "^(index |@@)" before.diff) <(grep -vE "^(index |@@)" after.diff)
```

Expected: only context lines around the insertion points differ (where conflict resolution changed
what our hunk attaches to). Lines we added or removed must be byte-identical.

Three traps:

1. **Don't compute the base with `~N`.** `<old tip>~13` walks first-parent into unrelated upstream
   history and unrelated files appear in the diff. Always use `git merge-base <old tip> <new
   base>`.
2. **"Old tip" is the tip right before the rebase**, not the tip at the start of your session.
   Using the session-start SHA makes the "differences" the commits added since — a wasted round.
3. **Limit to the directories the branch actually touched.** The rebase target usually carries
   many upstream commits that would drown the signal.

Not evidence: "tests are green" (a dropped hunk may be uncovered); "same test count" (first check
whether the upstream commits touched test files at all — `git show --stat <new base>` only shows
the last one, read the whole range); "`git status` is clean / rebase succeeded" (conflict markers
that were committed leave status clean too — grep for leftover markers over **the same scope you
claim**, not a narrower one). Related: a dropped hunk makes the commit message stale (see the
section above); this section is how to prove whether any hunk was dropped.

## Stacking on someone else's unmerged PR: state commit ownership in the options up front

Before stacking a branch on another contributor's unmerged PR (e.g. to use an API it adds), put
the consequence into the options you give the user: their branch and PR will **carry the other
PR's commits** until it merges, and any rebase by its author must be followed. List the
alternative: split out the part that doesn't depend on it and base that directly on `main`, and
stack the dependent part after the other PR merges. Don't just report "stacked on #N's head" after
the fact. Case (2026-09-30): Snowflake Cortex work was stacked on apache/airflow #73532; the user
asked "why aren't the first two commits mine?" and it was split — auth + model hook based on
`main`, the managed-agent part waiting for #73532 to merge.
