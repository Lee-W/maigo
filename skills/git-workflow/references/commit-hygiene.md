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
