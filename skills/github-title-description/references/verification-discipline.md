# GitHub Title & Description — Verification Discipline

Loaded on demand by `skills/github-title-description/SKILL.md` — read this when drafting
a status/progress snapshot, interface summary, or any PR description section that makes
claims about PR state, API signatures, or CLI flags.

---

## Verify every factual claim against live source

When writing a PR description (or a status/progress document) that states:

- a PR's merge status,
- an API kwarg name or signature,
- a CLI flag or command name,

verify each claim against the **current source** before writing. Do not copy from a
reference document or rely on memory — reference docs go stale silently.

### Why this matters

A "trusted" reference document can be out of date in ways that are easy to miss:

- A PR transitions from OPEN to MERGED overnight.
- A kwarg is renamed (`forward=True` → `direction=Window.Direction.*`).
- An entire CLI interface is redesigned (e.g. `airflow dags backfill` with
  `--partition-date-*` hypothetical flags becomes `airflow backfill create` reusing
  `--from-date/--to-date` with auto-detect).

Reproducing stale facts in a PR description passes the error downstream to reviewers,
who must then correct it item by item.

### Verification recipe

| Claim type | How to verify |
|------------|---------------|
| PR merge status | `gh pr view <n> -R <repo> --json state,mergedAt` |
| API / function signature (merged PR) | Read the source file at HEAD: `git show HEAD:<path>` or open the file |
| API / function signature (open PR) | `gh pr diff <n> -R <repo>` to get current patch |
| CLI flag / command name | `breeze run airflow <command> --help` (or read the source: `airflow-core/src/airflow/cli/`) |
| Rebase branch: what changed in this PR | `git diff HEAD~1 HEAD` — not against an older base ref that the rebase may have superseded |

### When "read source / run command" is feasible, use it

The same discipline applies to any factual claim in code review comments, status reports,
or planning documents: if the answer is verifiable by reading a file or running a
command, do that rather than inferring from grep output or a cached document.

This is the same principle as the `strict-review` item "符合既有慣例" — point at a
specific `path:line`, not a general impression.

---

## Re-sync the description after a design pivot

A PR description doesn't update itself when new commits land. If review swaps out the
core mechanism, or removes a parameter the description already named, the description
keeps describing the old design — and the reviewer reads the description, not the diff.

Seen: a PR originally exposed a scalar parameter; after review it moved to a
templatable dict and dropped the scalar, but the description's "What" section still
argued for the scalar parameter's necessity. The reviewer's reaction wasn't "this
paragraph is stale" — it was to question the PR's motivation entirely, and to note
they hadn't read the diff file-by-file because there were too many files to check
against a description that didn't match. A stale description costs more than wording:
it costs the reviewer's trust in the *why*.

**Trigger** (any one of these → put the description on this round's wrap-up list):

- Removing or renaming a parameter/function/flag the description already named.
- Swapping the core mechanism the description describes, even if the external effect
  is similar.
- Adopting a reviewer's suggestion that changes the implementation approach.

Check the PR title against the same trigger in the same pass; if the title is off too,
raise it separately with the user rather than assuming it should change alongside the
description.

## Local hooks don't inspect what Bash sends to GitHub

A local `PostToolUse` hook that reformats/checks file writes only intercepts
Write/Edit against local files. Content a `gh issue create` / `gh pr create` /
`gh pr edit` command sends via Bash is not inspected by any such hook.

In a repo with an enforced naming convention (e.g. apache/airflow's Dag title-case
rule), verify the title/body yourself — `grep` for the disallowed spelling — before
posting through `gh`. Don't rely on a local hook to catch it; it can't see Bash's
payload.

Seen: an issue title initially used the all-caps spelling and had to be corrected
afterward with `gh issue edit`.
