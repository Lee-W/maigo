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
