# Strict Review — Pre-PR Sweeps

Loaded on demand by `skills/strict-review/SKILL.md`. Five self-checks the author runs
**before** a PR is opened, so the first review round catches what a reviewer would otherwise
catch later. `/maigo:go` and `/maigo:team` run them in full mode. 🎀 Anon executes every
sweep and puts one result line per sweep in the review material (a sweep with nothing to
check is written "none", not omitted). 🟡 Soyo is read-only: she verifies by reading the
result and re-running read-only commands (`grep`, `git show`, `git ls-tree`), never by
editing files or opening worktrees. Repo-agnostic; repo-specific recipes live in the
matching domain skill.

The sweeps are an author-side duty of the `/maigo:go` and `/maigo:team` hand-off. When 🟡
Soyo reviews someone else's PR (`/maigo:review`) or runs in another mode, a missing sweep
result is not a must-fix; it is listed as Evidence pending or as a direction.

Each sweep: the rule, why, how to check. Sweeps (a) and (c) apply only when the diff
changes a public symbol or a documented promise; otherwise write "none" and move on.
Where a sweep has an existing rule, this file links to it instead of restating it.

Evidence behind the "Why" entries is a hand-classified sample of review comments on
apache/airflow PRs (category counts are approximate, about ±3 per category). The sample
is small and the comments concentrate in a few large PRs (#74695, #74694, #75369,
#76015), so treat the categories as a prioritisation hint, not as a measured rate.

---

## (a) Public-symbol consistency sweep

**Rule.** For every symbol this diff renames, removes or gives new behaviour, list it
together with its user-visible names (parameter name, config key, doc heading, error
text). Reconcile that list against docs, docstrings, changelog, examples and the PR
description draft, one entry at a time.

**Why.** Docs, changelog and description disagreeing with the code is the largest
category in the sample (about 35 comments, most of them catchable by the author). Case
(apache/airflow #74694, #74695): a changelog line said "like every other toolset's" while
several toolsets had no such option, and another said "shipped in 0.10.0" while the release
tag showed the class in an earlier release.

**How to check.** Executed by 🎀 Anon; 🟡 Soyo re-derives a sample of the doc statements
from the diff by reading.
- Enumerate the symbols and their user-visible names with
  [`change-site-enumeration`](https://github.com/Lee-W/maigo/blob/main/skills/change-site-enumeration/SKILL.md):
  implementation symbol names and user-visible names are scanned separately.
- Re-derive each doc statement from the current code, following
  [`claims-and-evidence-checks.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/claims-and-evidence-checks.md)
  section 6.
- Hand the symbol list to 🟡 Soyo in the review material; an empty list is written "none".

## (b) New tests must be able to fail

**Rule.** Every test added or rewritten to guard a behaviour comes with a per-test
mutation row: remove or invert the guarded line, name the assertion that turns red,
restore, and confirm the suite is green again. 🎀 Anon runs the mutation (Anon has Edit);
🟣 Taki does not edit files. Also confirm the repo's CI actually collects each new test
file (the repo's test-path configuration, not only a local run).

**Why.** "The test cannot fail" and "too weak to fail" together are a large category
(about 25 comments), and they are fully catchable by the author. Cases
(apache/airflow #76015): deleting the call under test left 44 tests green; a new test file
was missing from the CI test-path list, so CI never ran it. Another PR drew the comment
"This assertion can't fail" (#74626).

**How to check.** Executed by 🎀 Anon (she edits, then restores and byte-compares); 🟡 Soyo
reads the table and the repo's test-path configuration, and does not mutate anything.
- Run the mutation per test (or with `-v`) and record a small baseline → post-mutation
  table; the recipe and the restore discipline (backup, byte-compare, shared working tree
  rules) are in the "Mutation test 作為修法驗證證據" paragraph of
  [`strict-review/references/re-review-details.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/re-review-details.md).
- Any test still green under mutation gets a one-line reason: it guards something else, or
  it guards nothing and is removed or fixed.
- For CI collection, find where the repo lists its test paths and check the new file is
  covered by it.
- No new behaviour test in the diff: write "none".
- Before running anything, name the **most likely wrong implementation** each test is meant to reject (loop order
  swapped, a condition inverted or always true, a type check standing in for a value check, a missing value treated as
  a match), and say why the assertion fails under it. A test that passes only shows the current code satisfies it, not
  that it tells the right code from a plausible wrong one. The mutation run above and the per-side recipe in
  [`python-aware/references/test-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/references/test-conventions.md)
  ("Parity tests need a one-sided mutation") already cover how to run it; the points below are what they do not.
- A parametrized test: for every id, confirm the object it builds really is the scenario the id names and reaches the
  branch the id claims (a "mixed" case whose members were all built the same way takes a different branch and passes
  by coincidence).
- Every deliberate either/or in the design (strict or lenient, do or do not) needs one piece of test data that tells the
  two choices apart, including the "do not" half (a rule that excludes a field only under some condition needs a case
  where it must not be excluded; a pairwise comparison where a missing value equals only a missing value needs a pair
  with a value on one side only). List that data at planning time.
- Pin assertions to the behaviour's output (a return value, an argument passed on, a call count), not only to a type.
- Cleanup paths count: when a `finally` branches on a flag (raise if cleanup fails, or only log so the original failure
  wins), each branch needs a test in which the cleanup action really fails, and inverting the condition turns both red.

## (c) Behaviour that has already been released

**Rule.** When the diff touches a public interface, a default, a serialization shape or a
documented promise, look up what the latest release tag does and says at that spot, and
write one line: what changes for users who already installed the released version.

**Why.** Compatibility with released versions drew about 10 comments, partly catchable by
the author. Cases (apache/airflow #74695): a reviewer pointed out that the final 1.0.0 was
already on the package index, so removing an alias was a breaking change on a minor upgrade
and its changelog note landed inside the already-released 1.0.0 section; later, 1.1.0 had
shipped and the PR's edits rewrote that released section so it described things the tag did
not do.

**How to check.** Executed by 🎀 Anon, using read-only git commands; 🟡 Soyo re-runs the same
`git ls-tree` / `git show <tag>:<path>` lookup on one symbol.
- Find the release that contains the symbol and compare the documented behaviour there
  with the new behaviour; do not date it from commit order or memory.
- Airflow specifics (tag lookup, package-index check, stable-listed aliases) are owned by
  the release-tag check in
  [`airflow-aware/references/review-checks.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/review-checks.md);
  this sweep is the repo-agnostic version and defers to it in Airflow repos (that section
  links back here).
- Nothing public or documented changed: write "none".

## (d) Duplicated logic

**Rule.** For each new helper, constant or explanatory paragraph, search the same module
and its neighbours for an existing equivalent. If one exists, reuse it; if not reusing,
say why in the PR description.

**Why.** Design and duplicate-logic comments were about 15 in the sample, and the
duplicate half is catchable by the author with one search (the rest, such as choosing
between abstractions, is reviewer judgment). Case (apache/airflow #74695): a reviewer
pointed at two new pieces of code that were "essentially the same" and asked to keep one.

**How to check.** Executed by 🎀 Anon, who lists each new helper with the equivalent found
or "none"; 🟡 Soyo re-runs one or two of the greps (read-only).
- Grep for the new name's likely synonyms and for the body's distinctive calls or
  literals, in the same file, sibling modules and the shared utilities.
- For prose, grep the docs for the key phrase to find the existing paragraph.

## (e) Scope

**Rule.** Look at every new test and every changed file and ask whether it belongs to the
plan's single subject. A test that already passes on the base branch, or a change
unrelated to the subject, is moved out or justified in the PR description.

**Why.** Scope creep was a small category (about 3 comments) but cheap to avoid, and it
inflates the review unit. Case (apache/airflow #76015): a reviewer pointed out that five
new tests already passed against the base branch and covered paths the PR did not change,
and asked whether they belonged in it.

The same rule governs a requested style fix (an inline import, a name, a duplicate): when asked to fix a pattern, change
only the files this PR adds or modifies. Other files with the identical pattern, even the one it was copied from, are
left alone and mentioned in the report in one sentence. It holds inside a single file too: change only the lines this
branch added, and leave same-kind lines that already exist on the target branch. Tell them apart with
`git diff <target>...HEAD` (three dots: changes since the merge base); a line not in that diff is not yours to touch.

**How to check.** Executed by 🎀 Anon, because it needs a worktree and 🟡 Soyo is read-only.
- Run each new test against the base branch in a detached worktree (never a checkout in the
  shared tree). 🎀 Anon creates it with `git worktree add --detach <path outside the repo>
  <base>`, removes it with `git worktree remove` afterwards, and attaches the
  `git worktree list` output showing it is gone. A pass on the base means the test does not
  belong to this change.
- `<base>` is the remote-tracking ref decided by the wrap-up base rule in
  [`draft-bundle.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/references/draft-bundle.md)
  (收尾情境); do not restate it here.
- A new test file does not exist on the base, so copy the new test files into the detached
  worktree before running them, or the run fails at collection instead of showing whether the
  test passes on the base.
- 🟡 Soyo reads the per-test base-branch result and the worktree-removal proof; she does not
  open a worktree herself.
- List changed files that the plan's subject does not mention.
