# Strict Review — Pre-PR Sweeps

Loaded on demand by `skills/strict-review/SKILL.md`. Five self-checks the author runs
**before** a PR is opened, so the first review round catches what a reviewer would otherwise
catch later. `/maigo:go` and `/maigo:team` run them in full mode: 🎀 Anon produces the
inputs, 🟡 Soyo checks them. Repo-agnostic; repo-specific recipes live in the matching
domain skill.

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
three toolsets had no such option, and another said "shipped in 0.10.0" while the release
tag showed the class in an earlier release.

**How to check.**
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

**Why.** "The test cannot fail" and "too weak to fail" together are the second-largest
category (about 25 comments), and they are fully catchable by the author. Cases
(apache/airflow #76015): deleting the call under test left 44 tests green; a new test file
was missing from the CI test-path list, so CI never ran it. Another PR drew the comment
"This assertion can't fail" (#74626).

**How to check.**
- Run the mutation per test (or with `-v`) and record a small baseline → post-mutation
  table; the recipe and the restore discipline (backup, byte-compare, shared working tree
  rules) are in the Mutation test section of
  [`strict-review/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md).
- Any test still green under mutation gets a one-line reason: it guards something else, or
  it guards nothing and is removed or fixed.
- For CI collection, find where the repo lists its test paths and check the new file is
  covered by it.
- No new behaviour test in the diff: write "none".

## (c) Behaviour that has already been released

**Rule.** When the diff touches a public interface, a default, a serialization shape or a
documented promise, look up what the latest release tag does and says at that spot, and
write one line: what changes for users who already installed the released version.

**Why.** Compatibility with released versions drew about 10 comments, partly catchable by
the author. Case (apache/airflow #74695): tags ended at an `rc` while the final release
was already on the package index, so the "not released yet" assumption was wrong.

**How to check.**
- Find the release that contains the symbol and compare the documented behaviour there
  with the new behaviour; do not date it from commit order or memory.
- Airflow specifics (tag lookup, package-index check, stable-listed aliases) are owned by
  the release-tag check in
  [`airflow-aware/references/review-checks.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/review-checks.md);
  this sweep is the repo-agnostic version and defers to it in Airflow repos.
- Nothing public or documented changed: write "none".

## (d) Duplicated logic

**Rule.** For each new helper, constant or explanatory paragraph, search the same module
and its neighbours for an existing equivalent. If one exists, reuse it; if not reusing,
say why in the PR description.

**Why.** Design and duplicate-logic comments were about 15 in the sample, and the
duplicate half is catchable by the author with one search (the rest, such as choosing
between abstractions, is reviewer judgment). Case (apache/airflow #74695): a reviewer
pointed at two new pieces of code that were "essentially the same" and asked to keep one.

**How to check.**
- Grep for the new name's likely synonyms and for the body's distinctive calls or
  literals, in the same file, sibling modules and the shared utilities.
- For prose, grep the docs for the key phrase to find the existing paragraph.

## (e) Scope

**Rule.** Look at every new test and every changed file and ask whether it belongs to the
plan's single subject. A test that already passes on the base branch, or a change
unrelated to the subject, is moved out or justified in the PR description.

**Why.** Scope creep was a small category (about 3 comments) but cheap to avoid, and it
inflates the review unit. Case (apache/airflow #76015, comment C5): a new test already
passed on the base branch, so it guarded nothing the PR changed.

**How to check.**
- Run each new test against the base branch (a detached worktree, not a checkout in the
  shared tree); a pass there means it does not belong to this change.
- List changed files that the plan's subject does not mention.
